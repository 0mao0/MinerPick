import os
import json
import httpx
import re
from typing import Dict, Any, List, Optional
from fastapi import HTTPException
from .base import BaseParser, write_json_file, write_text_file, _coerce_json_value
from .tableExtractor_gmft import GMFTTableExtractor

class MinerUParser(BaseParser):
    """
    MinerU Parser Implementation.
    
    Logic Flow:
    1. **MinerU Remote API**: Generates `content.md` and `content_list.json` (layout analysis).
       - `content.md`: The markdown representation of the PDF.
       - `content_list.json`: A list of layout elements (text blocks, tables, images) with bounding boxes.
    
    2. **GMFT Table Extraction**: 
       - Uses `content_list.json` to identify table regions (bboxes) found by MinerU.
       - GMFT (guided by these bboxes) extracts detailed table information (cells, structure, cross-page tables) from the original PDF.
       - Generates `content_tables.json` containing enriched table data (including cell bboxes).
    
    3. **Result Compilation**:
       - Merges the enriched table data back into the markdown flow where possible.
       - Returns URLs for `content.md`, `content_list.json`, and `content_tables.json`.
       
    Frontend Usage:
    - Non-table content: Uses `content_list.json` for highlighting.
    - Table content: Uses `content_tables.json` for detailed cell-level highlighting.
    """
    def __init__(self, api_url: str, api_key: str = None):
        self.api_url = api_url.rstrip("/")
        if self.api_url.endswith("/docs"):
            self.api_url = self.api_url[:-5].rstrip("/")
        self.api_key = api_key
        self.table_extractor = GMFTTableExtractor()

    @property
    def name(self) -> str:
        return "MinerU"

    def _is_toc_entry(self, text: str) -> bool:
        """Check if the text looks like a Table of Contents entry."""
        if not text:
            return False
        # TOC entries often have many dots or end with a page number preceded by dots/spaces
        import re
        if re.search(r'\.{4,}', text):
            return True
        if re.search(r'\s+\d+$', text) and len(text) > 10:
            return True
        return False

    def _best_anchor_in_window(self, target_text: str, candidates: List[Dict], start_idx: int, window_size: int, is_heading: bool = False, min_page_idx: int = -1) -> Optional[int]:
        """Find the best matching candidate index within a window."""
        if not target_text:
            return None
        
        # Debug flag
        is_debug_text = False
        
        target_norm = self._normalize_match_text(target_text)
        if not target_norm:
            return None

        best_idx = None
        best_score = 0
        
        end_idx = min(len(candidates), start_idx + window_size)
        
        # If it's a heading, we want to avoid matching TOC entries if possible
        toc_matches = []

        for i in range(start_idx, end_idx):
            cand = candidates[i]
            cand_text = cand.get("text", "")
            cand_norm = self._normalize_match_text(cand_text)
            
            if not cand_norm:
                continue
            
            # Skip if page is backwards (allow same page)
            cand_page = cand.get("page_idx", -1)
            if min_page_idx >= 0 and cand_page >= 0 and cand_page < min_page_idx:
                continue

            # Use Jaccard-like similarity for better fuzzy matching
            score = self._calculate_text_similarity(target_norm, cand_norm)
            
            # if is_debug_text and score > 0.3:
            #      print(f"  [DEBUG-MATCH] Candidate: '{cand_text}' (norm: '{cand_norm}') Score: {score:.2f} Page: {cand_page}")

            if score > 0.6:
                if is_heading and self._is_toc_entry(cand_text):
                    toc_matches.append((i, score))
                    continue
                
                if score > best_score:
                    best_score = score
                    best_idx = i
                    
                if score > 0.95: # Early exit for very strong match
                    break
        
        # If no non-TOC match found for a heading, but we found TOC matches, 
        # only use them if the score is extremely high (rarely the case for real headings)
        if best_idx is None and toc_matches:
            # Sort by score descending
            toc_matches.sort(key=lambda x: x[1], reverse=True)
            if toc_matches[0][1] > 0.9:
                return toc_matches[0][0]
                
        return best_idx

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Text similarity with character-level and word-level consideration."""
        if not text1 or not text2:
            return 0.0
        
        # Normalize
        t1 = self._normalize_match_text(text1)
        t2 = self._normalize_match_text(text2)
        
        if not t1 or not t2:
            return 0.0
        
        if t1 == t2:
            return 1.2 # Perfect match bonus
            
        # 1. Character-level Jaccard
        s1 = set(t1)
        s2 = set(t2)
        intersection = s1.intersection(s2)
        union = s1.union(s2)
        if not union: return 0.0
        jaccard = len(intersection) / len(union)
        
        # 2. Length similarity penalty
        len_ratio = min(len(t1), len(t2)) / max(len(t1), len(t2))
        
        # 3. Order consideration (simple)
        # If one is a substring of the other, it's a strong indicator
        substring_bonus = 1.0
        if t1 in t2 or t2 in t1:
            substring_bonus = 1.2
        
        # Combine
        score = jaccard * len_ratio * substring_bonus
        
        # For long strings, be more lenient if they share a lot of words
        if len(t1) > 10 or len(t2) > 10:
            # Word-level Jaccard (simple approach: split by 2-char chunks for Chinese)
            def get_chunks(s): return set([s[i:i+2] for i in range(len(s)-1)])
            c1 = get_chunks(t1)
            c2 = get_chunks(t2)
            if c1 and c2:
                word_jaccard = len(c1 & c2) / len(c1 | c2)
                score = max(score, word_jaccard * 1.1)

        # For very short strings, be more lenient if it's a substring
        if (len(t1) <= 4 or len(t2) <= 4) and (t1 in t2 or t2 in t1):
            score = max(score, 0.7)
            
        return score

    def _build_md_first_content_list(
        self,
        md_text: str,
        raw_content_list: List[Dict[str, Any]],
        content_tables: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], str]:
        blocks = self._split_markdown_blocks(md_text)

        tables = []
        candidates = []
        for it in raw_content_list or []:
            if not isinstance(it, dict):
                continue
            if it.get("type") == "discarded":
                continue
            if it.get("type") == "table":
                tables.append(it)
                continue
            txt = it.get("text")
            if not isinstance(txt, str) or not txt.strip():
                continue
            cand = dict(it)
            cand["_norm"] = self._normalize_match_text(txt)
            candidates.append(cand)

        def _sort_key(x: Dict[str, Any]):
            page_idx = x.get("page_idx")
            y0 = 0
            bbox = x.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 2:
                try:
                    y0 = float(bbox[1])
                except Exception:
                    pass
            return (page_idx if isinstance(page_idx, int) else 10**9, y0)

        candidates.sort(key=_sort_key)
        
        # Prepare table definitions from both sources
        table_defs = []
        
        # 1. First, use enriched tables from GMFT (content_tables)
        # Sort content_tables keys by page and y0 to ensure they are in reading order
        table_items = []
        if isinstance(content_tables, dict):
            for table_id, t in content_tables.items():
                if not isinstance(t, dict): continue
                table_items.append((table_id, t))
        
        table_items.sort(key=lambda x: _sort_key(x[1]))

        used_mineru_ids = set()
        for table_id, t in table_items:
            table_defs.append(
                {
                    "id": table_id,
                    "page_idx": t.get("page_idx"),
                    "bbox": t.get("bbox"),
                    "table_body": t.get("md") or t.get("html") or t.get("text"),
                    "cells": t.get("cells", []), # Pass cells through
                    "is_enriched": True
                }
            )
            if table_id.isdigit() or table_id.startswith("m_table_"):
                used_mineru_ids.add(table_id)

        # 2. Add tables from raw_content_list that weren't enriched
        raw_tables_to_add = []
        for t in tables:
            m_id = str(t.get("id"))
            if m_id in used_mineru_ids:
                continue
            raw_tables_to_add.append(t)
        
        raw_tables_to_add.sort(key=_sort_key)
        for t in raw_tables_to_add:
            table_defs.append(
                {
                    "id": str(t.get("id")),
                    "page_idx": t.get("page_idx"),
                    "bbox": t.get("bbox"),
                    "table_body": t.get("table_body") or t.get("html") or t.get("text"),
                    "is_enriched": False
                }
            )

        # Sort all table defs by page and position
        table_defs.sort(key=_sort_key)

        cand_ptr = 0
        table_ptr = 0
        out: List[Dict[str, Any]] = []

        # Track used table_defs to avoid double matching
        used_table_indices = set()
        last_matched_page_idx = 0

        new_blocks = []
        for md_index, block in enumerate(blocks):
            is_md_table = self._is_markdown_table_block(block)
            is_html_table = self._is_html_table_block(block)
            
            if is_md_table or is_html_table:
                # ... (table matching logic, no changes needed for text matching) ...
                # But we should update last_matched_page_idx if table matches
                # I'll handle that inside the table block if I can, or just let text matching handle it.
                # Actually, table matching updates table_ptr but not explicitly last_matched_page_idx for text.
                # Let's keep it simple and focus on text for now.
                
                best_match_idx = -1
                best_score = 0.0
                
                # Try to find the best matching table in a window around table_ptr
                # Tables often follow text order, so we can use current page as a guide
                current_cand_page = candidates[cand_ptr].get("page_idx", 0) if cand_ptr < len(candidates) else 0
                
                search_start = max(0, table_ptr - 1)
                search_end = min(len(table_defs), table_ptr + 5)
                
                for i in range(search_start, search_end):
                    if i in used_table_indices:
                        continue
                    
                    t_def = table_defs[i]
                    score = self._calculate_text_similarity(block, t_def.get("table_body") or "")
                    
                    # Distance penalty: prefer tables on the current or nearby page
                    table_page = t_def.get("page_idx", 0)
                    page_diff = abs(table_page - current_cand_page)
                    if page_diff > 2:
                        score *= 0.7
                    elif page_diff == 0:
                        score *= 1.2 # Strong bonus for same page
                    
                    if score > best_score:
                        best_score = score
                        best_match_idx = i
                
                # Fallback: if no decent match in window, search all unused tables
                if best_score < 0.2:
                    for i in range(len(table_defs)):
                        if i in used_table_indices: continue
                        t_def = table_defs[i]
                        score = self._calculate_text_similarity(block, t_def.get("table_body") or "")
                        table_page = t_def.get("page_idx", 0)
                        
                        # Use last_matched_page_idx as a guide too
                        if last_matched_page_idx > 0 and table_page < last_matched_page_idx:
                             score *= 0.1 # Heavily penalize backward tables

                        page_diff = abs(table_page - current_cand_page)
                        if page_diff > 4: score *= 0.5
                        
                        if score > best_score:
                            best_score = score
                            best_match_idx = i
                
                # Final fallback: if still no match, just take the next available table
                if best_match_idx == -1:
                    for i in range(len(table_defs)):
                        if i not in used_table_indices:
                            # Check if it's reasonable
                            t_page = table_defs[i].get("page_idx", 0)
                            if t_page >= last_matched_page_idx:
                                best_match_idx = i
                                best_score = 0.05 # Low score but matched
                                break

                if best_match_idx != -1:
                    t = table_defs[best_match_idx]
                    used_table_indices.add(best_match_idx)
                    
                    # Update last_matched_page_idx
                    if isinstance(t.get("page_idx"), int):
                        last_matched_page_idx = t.get("page_idx")

                    # --- Check for cross-page continuation ---
                    current_table_ids = [t.get("id")]
                    combined_cells = list(t.get("cells", []))
                    
                    next_idx = best_match_idx + 1
                    while next_idx < len(table_defs):
                        nt = table_defs[next_idx]
                        if next_idx in used_table_indices: 
                            next_idx += 1
                            continue
                            
                        t_cells = t.get("cells", [])
                        nt_cells = nt.get("cells", [])
                        
                        t_cols = len(set(c.get("c") for c in t_cells)) if t_cells else 0
                        nt_cols = len(set(c.get("c") for c in nt_cells)) if nt_cells else 0
                        
                        # Continuation if: consecutive page AND same number of columns
                        if nt.get("page_idx") == t.get("page_idx") + 1 and t_cols == nt_cols and t_cols > 0:
                            current_table_ids.append(nt.get("id"))
                            used_table_indices.add(next_idx)
                            
                            max_row = max(c.get("r", 0) for c in combined_cells) if combined_cells else -1
                            nt_header_rows = sorted(list(set(c.get("r") for c in nt_cells if c.get("is_header"))))
                            
                            row_offset = max_row + 1
                            for nc in nt_cells:
                                if nc.get("r") in nt_header_rows:
                                    continue
                                num_headers_before = sum(1 for hr in nt_header_rows if hr < nc.get("r"))
                                adjusted_r = nc.get("r") - num_headers_before
                                combined_cells.append({
                                    **nc,
                                    "r": adjusted_r + row_offset
                                })
                            
                            # print(f"[{self.name}] Merged continuation Table ID {nt.get('id')} into {t.get('id')} (Skipped {len(nt_header_rows)} header rows)")
                            t = nt 
                            next_idx += 1
                            # Update page idx for continuation
                            if isinstance(nt.get("page_idx"), int):
                                last_matched_page_idx = nt.get("page_idx")
                        else:
                            break
                    
                    table_ptr = next_idx
                    
                    # Update content_tables with combined cells if merged
                    if len(current_table_ids) > 1:
                        primary_id = current_table_ids[0]
                        if primary_id in content_tables:
                            content_tables[primary_id]["cells"] = combined_cells

                    # Advance cand_ptr if table is far ahead
                    table_page = table_defs[best_match_idx].get("page_idx")
                    if isinstance(table_page, int) and table_page > current_cand_page:
                        while cand_ptr < len(candidates) and candidates[cand_ptr].get("page_idx", 0) < table_page:
                            cand_ptr += 1

                    # print(f"[{self.name}] Matched MD Block {md_index} to Table ID {current_table_ids[0]} (Score: {best_score:.2f}, Page: {table_defs[best_match_idx].get('page_idx')}, Parts: {len(current_table_ids)})")
                    
                    # Use GMFT generated markdown for consistency with cells
                    gmft_md = table_defs[best_match_idx].get("table_body")
                    
                    item = {
                        "type": "table",
                        "md_index": md_index,
                        "id": current_table_ids[0],
                        "page_idx": table_defs[best_match_idx].get("page_idx"),
                        "bbox": table_defs[best_match_idx].get("bbox"),
                        "table_body": gmft_md or block,
                    }
                    new_blocks.append(gmft_md or block)
                else:
                    # print(f"[{self.name}] Found extra table block at {md_index} but no more table_defs.")
                    item = {"type": "table", "md_index": md_index, "text": block}
                    new_blocks.append(block)
                out.append(item)
                continue

            new_blocks.append(block)
            text_level = None
            m = re.match(r"^(#{1,6})\s+(.+)$", (block or "").strip())
            if m:
                text_level = len(m.group(1))
                plain = m.group(2).strip()
            else:
                plain = self._strip_markdown_text(block)

            # Search with a small look-back to handle slight OCR/layout reordering
            # Reduced lookback from 100 to 30 to prevent matching far-back pages
            anchor_idx = self._best_anchor_in_window(plain, candidates, max(0, cand_ptr - 30), 350, is_heading=(text_level is not None), min_page_idx=last_matched_page_idx)
            
            if anchor_idx is None:
                # Reduced fallback window from 2000 to 1000
                anchor_idx = self._best_anchor_in_window(plain, candidates, max(0, cand_ptr - 50), 1000, is_heading=(text_level is not None), min_page_idx=last_matched_page_idx)

            item = {"type": "text", "text": plain, "md_index": md_index}
            if text_level:
                item["text_level"] = text_level
            if anchor_idx is not None:
                anchor = candidates[anchor_idx]
                
                # --- Greedy Merge Logic ---
                merged_bbox = list(anchor.get("bbox")) if anchor.get("bbox") else None
                merged_text = anchor.get("_norm", "")
                page_idx = anchor.get("page_idx")
                
                if isinstance(page_idx, int):
                    item["page_idx"] = page_idx
                    last_matched_page_idx = page_idx
                
                # Try to absorb subsequent candidates to fix split paragraph highlighting
                next_ptr = anchor_idx + 1
                matched_count = 0
                plain_norm = self._normalize_match_text(plain)
                
                # Only try merging if the block is longer than the matched anchor
                if len(plain_norm) > len(merged_text) + 5:
                    while next_ptr < len(candidates) and next_ptr < anchor_idx + 20: # Limit lookahead
                        cand = candidates[next_ptr]
                        
                        # Stop if page changes significantly (allow next page for cross-page paragraphs)
                        cand_page = cand.get("page_idx")
                        if cand_page != page_idx and cand_page != page_idx + 1:
                            break
                        
                        cand_text = cand.get("_norm", "")
                        if not cand_text:
                            next_ptr += 1
                            continue
                            
                        # Check if adding this candidate improves similarity to the block text
                        combined = merged_text + cand_text
                        
                        sim_curr = self._calculate_text_similarity(plain_norm, merged_text)
                        sim_new = self._calculate_text_similarity(plain_norm, combined)
                        
                        # Heuristic: If similarity improves, or if the candidate is clearly part of the text
                        # (e.g. combined is a substring of plain_norm)
                        is_substring = combined in plain_norm
                        
                        if sim_new >= sim_curr or is_substring or sim_new > 0.7:
                            # Merge bbox
                            c_bbox = cand.get("bbox")
                            if c_bbox and merged_bbox:
                                # If cross-page, we can't really merge bboxes easily for display unless we handle multi-rects.
                                # For now, if same page, merge. If diff page, ignore bbox update but consume text.
                                if cand_page == page_idx:
                                    merged_bbox = [
                                        min(merged_bbox[0], c_bbox[0]),
                                        min(merged_bbox[1], c_bbox[1]),
                                        max(merged_bbox[2], c_bbox[2]),
                                        max(merged_bbox[3], c_bbox[3])
                                    ]
                            merged_text = combined
                            matched_count += 1
                            next_ptr += 1
                        else:
                            # If we encounter something that doesn't match, stop merging
                            break
                
                if merged_bbox:
                    item["bbox"] = merged_bbox
                
                # Advance cand_ptr to the end of the merged sequence
                # Use max to ensure we don't go backwards if something weird happened
                cand_ptr = max(cand_ptr, next_ptr if matched_count > 0 else anchor_idx + 1)
            else:
                # No match found, just advance slightly to avoid getting stuck? 
                # No, cand_ptr stays, effectively skipping this block for matching purposes
                pass

            out.append(item)

        return out, "\n\n".join(new_blocks)

    def _calculate_iou(self, bbox1, bbox2):
        """
        Calculate Intersection over Union (IoU) for two bboxes.
        bbox: [x0, y0, x1, y1]
        """
        if not bbox1 or not bbox2:
            return 0.0
            
        x0_1, y0_1, x1_1, y1_1 = bbox1
        x0_2, y0_2, x1_2, y1_2 = bbox2
        
        x_left = max(x0_1, x0_2)
        y_top = max(y0_1, y0_2)
        x_right = min(x1_1, x1_2)
        y_bottom = min(y1_1, y1_2)
        
        if x_right < x_left or y_bottom < y_top:
            return 0.0
            
        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        area1 = (x1_1 - x0_1) * (y1_1 - y0_1)
        area2 = (x1_2 - x0_2) * (y1_2 - y0_2)
        
        union_area = area1 + area2 - intersection_area
        if union_area <= 0:
            return 0.0
            
        return intersection_area / union_area

    async def parse(self, pdf_path: str, task_result_dir: str, **kwargs) -> Dict[str, Any]:
        api_url = kwargs.get("api_url_override") or self.api_url
        api_key = kwargs.get("api_key_override") or self.api_key
        
        filename = os.path.basename(pdf_path)
        
        try:
            # print(f"[{self.name}] Sending to API: {api_url}/file_parse")
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                
            async with httpx.AsyncClient(verify=False, timeout=300.0) as client:
                with open(pdf_path, "rb") as f:
                    files = {'files': (filename, f, 'application/pdf')}
                    data = {
                        "return_middle_json": "false",
                        "return_content_list": "true",
                        "return_md": "true"
                    }
                    response = await client.post(
                        f"{api_url}/file_parse",
                        files=files,
                        data=data,
                        headers=headers
                    )
            
            if response.status_code != 200:
                error_detail = f"MinerU API error: {response.status_code}"
                try:
                    error_json = response.json()
                    error_detail += f" - {json.dumps(error_json)}"
                except:
                    error_detail += f" - {response.text}"
                print(f"[{self.name}] Error: {error_detail}")
                raise HTTPException(status_code=500, detail=error_detail)

            result_data = response.json()
            results = result_data.get("results", {})
            if not results:
                raise HTTPException(status_code=500, detail="No results returned from MinerU")
            
            first_filename = list(results.keys())[0]
            content = results[first_filename]
            # print(f"[{self.name}] API Response content keys: {list(content.keys())}")

            md_content = content.get("md_content", "") or ""
            raw_content_list = _coerce_json_value(content.get("content_list", [])) or []
            if isinstance(raw_content_list, dict):
                raw_content_list = raw_content_list.get("content_list", []) or []
            
            # Ensure tables in raw_content_list have IDs
            table_counter = 0
            for item in raw_content_list:
                if item.get("type") == "table":
                    if item.get("id") is None:
                        item["id"] = f"m_table_{table_counter}"
                        table_counter += 1

            raw_content_tables = _coerce_json_value(content.get("content_tables")) or {}
            if not isinstance(raw_content_tables, dict):
                raw_content_tables = {}

            # Enrich tables using GMFT guided by MinerU
            final_content_tables = {}
            try:
                # print(f"[{self.name}] Enriching tables with GMFT guided by MinerU...")
                final_content_tables = self.table_extractor.extract_tables_from_pdf(pdf_path, raw_content_list)
            except Exception as e:
                print(f"[{self.name}] Error enriching tables with GMFT: {e}")
                import traceback
                traceback.print_exc()
                # If GMFT fails, try to use raw tables if available
                if raw_content_tables:
                    final_content_tables = raw_content_tables

            # If no matches found but we have raw tables, use them
            if not final_content_tables and raw_content_tables:
                final_content_tables = raw_content_tables

            # 4. Generate content_list.json (reconstruct structure)
            # We use _build_md_first_content_list to generate the mapping (content_list.json)
            # BUT we discard the new_md_content because we want to preserve MinerU's original markdown
            # as requested by the user.
            md_first_list, _ = self._build_md_first_content_list(md_content, raw_content_list, final_content_tables)

            # 5. Write results
            # content.md: Use original MinerU output
            write_text_file(os.path.join(task_result_dir, "content.md"), md_content)
            # content_list.json: Use the mapped list (links MD blocks to Table IDs)
            write_json_file(os.path.join(task_result_dir, "content_list.json"), md_first_list)
            # content_tables.json: Use GMFT extracted detailed cell info
            write_json_file(os.path.join(task_result_dir, "content_tables.json"), final_content_tables)
            
            return {
                "md_url": f"content.md",
                "content_list_url": f"content_list.json",
                "content_tables_url": f"content_tables.json",
            }

        except HTTPException as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"{self.name} Error: {str(e)}")
