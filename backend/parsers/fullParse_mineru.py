import os
import json
import httpx
import re
from collections import Counter
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

    def _has_cjk(self, text: str) -> bool:
        if not text:
            return False
        for ch in text:
            code = ord(ch)
            if 0x4E00 <= code <= 0x9FFF:
                return True
        return False

    def _compact_text(self, text: str) -> str:
        s = (text or "").strip().lower()
        if not s:
            return ""
        s = re.sub(r"\s+", "", s)
        out = []
        for ch in s:
            if ch.isalnum():
                out.append(ch)
                continue
            code = ord(ch)
            if 0x4E00 <= code <= 0x9FFF:
                out.append(ch)
        return "".join(out)

    def _shingles(self, compact: str, has_cjk: bool) -> set[str]:
        if not compact:
            return set()
        if has_cjk:
            if len(compact) == 1:
                return {compact}
            return {compact[i : i + 2] for i in range(len(compact) - 1)}
        if len(compact) <= 3:
            return {compact}
        return {compact[i : i + 3] for i in range(len(compact) - 2)}

    def _prep_text(self, text: str) -> Dict[str, Any]:
        compact = self._compact_text(text)
        has_cjk = self._has_cjk(compact)
        return {
            "compact": compact,
            "has_cjk": has_cjk,
            "shingles": self._shingles(compact, has_cjk),
            "length": len(compact),
        }

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        p1 = self._prep_text(text1)
        p2 = self._prep_text(text2)
        a = p1["compact"]
        b = p2["compact"]
        if not a or not b:
            return 0.0
        if a == b:
            return 1.2

        s1 = p1["shingles"]
        s2 = p2["shingles"]
        if not s1 or not s2:
            return 0.0

        inter = len(s1 & s2)
        union = len(s1 | s2)
        jaccard = inter / union if union else 0.0
        len_ratio = min(len(a), len(b)) / max(len(a), len(b)) if max(len(a), len(b)) else 0.0
        score = jaccard * (0.5 + 0.5 * len_ratio)

        if (len(a) >= 8 and len(b) >= 8) and (a in b or b in a):
            score = max(score, 0.9)
        elif (len(a) <= 4 or len(b) <= 4) and (a in b or b in a):
            score = max(score, 0.7)

        return score

    def _merge_bboxes(self, bboxes: List[List[int]]) -> Optional[List[int]]:
        bxs = [b for b in (bboxes or []) if isinstance(b, list) and len(b) == 4]
        if not bxs:
            return None
        x0 = min(b[0] for b in bxs)
        y0 = min(b[1] for b in bxs)
        x1 = max(b[2] for b in bxs)
        y1 = max(b[3] for b in bxs)
        return [x0, y0, x1, y1]

    def _choose_dominant_page_and_bbox(self, cands: List[Dict[str, Any]]) -> tuple[Optional[int], Optional[List[int]]]:
        if not cands:
            return None, None
        weights: Counter[int] = Counter()
        for c in cands:
            p = c.get("page_idx")
            if isinstance(p, int) and p >= 0:
                weights[p] += int(c.get("_text_len") or 0) + 1
        if not weights:
            return None, None
        page_idx = weights.most_common(1)[0][0]
        bbox = self._merge_bboxes([c.get("bbox") for c in cands if c.get("page_idx") == page_idx])
        return page_idx, bbox

    def _best_span_match(
        self,
        md_prep: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        window_start: int,
        window_end: int,
        max_span: int,
    ) -> Optional[Dict[str, Any]]:
        if not md_prep or not md_prep.get("compact"):
            return None
        if window_start >= window_end:
            return None

        target_compact = md_prep["compact"]
        target_shingles = md_prep["shingles"]
        if not target_shingles:
            return None

        best: Optional[Dict[str, Any]] = None
        for s in range(window_start, window_end):
            span_compact = ""
            span_shingles: set[str] = set()
            span_cands: List[Dict[str, Any]] = []
            for e in range(s, min(window_end, s + max_span)):
                cand = candidates[e]
                span_cands.append(cand)
                span_compact += cand.get("_compact", "")
                span_shingles |= cand.get("_shingles", set())
                if not span_compact or not span_shingles:
                    continue

                inter = len(target_shingles & span_shingles)
                union = len(target_shingles | span_shingles)
                jaccard = inter / union if union else 0.0
                len_ratio = min(len(target_compact), len(span_compact)) / max(len(target_compact), len(span_compact))
                score = jaccard * (0.5 + 0.5 * len_ratio)

                if (len(target_compact) >= 8 and len(span_compact) >= 8) and (target_compact in span_compact or span_compact in target_compact):
                    score = max(score, 0.9)

                span_len_penalty = 0.03 * (e - s)
                score = score - span_len_penalty

                if best is None or score > best["score"]:
                    page_idx, bbox = self._choose_dominant_page_and_bbox(span_cands)
                    best = {
                        "start": s,
                        "end": e,
                        "score": score,
                        "page_idx": page_idx,
                        "bbox": bbox,
                        "cands": list(span_cands),
                    }

        return best

    def _build_md_first_content_list(
        self,
        md_text: str,
        raw_content_list: List[Dict[str, Any]],
        content_tables: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[Dict[str, Any]], str]:
        """
        Re-engineered strategy (Two-Pass Anchor-Based Alignment):
        1. Pre-process candidates and blocks.
        2. Pass 1: Identify 'Anchors' - unambiguous high-confidence matches.
        3. Pass 2: Fill gaps between anchors using constrained search windows.
        """
        blocks = self._split_markdown_blocks(md_text)
        
        # --- Pre-processing ---
        
        # 1. Prepare Text Candidates (PDF blocks)
        text_candidates = []
        for i, item in enumerate(raw_content_list):
            if item.get("type") == "table":
                continue
            text = item.get("text", "")
            if text.strip():
                prep = self._prep_text(text)
                if prep.get("compact"):
                    text_candidates.append(
                        {
                            "original_idx": i,
                            "item": item,
                            "text": text,
                            "_compact": prep["compact"],
                            "_shingles": prep["shingles"],
                            "_text_len": prep["length"],
                            "page_idx": item.get("page_idx"),
                            "bbox": item.get("bbox"),
                        }
                    )
        
        # 2. Prepare Table Candidates
        table_candidates = []
        for i, item in enumerate(raw_content_list):
            if item.get("type") == "table":
                # Ensure ID
                if not item.get("id"):
                     # Should have been assigned
                     pass
                table_candidates.append({
                    "original_idx": i,
                    "item": item,
                    "page_idx": item.get("page_idx"),
                    "id": item.get("id")
                })

        # 3. Prepare Block Info
        block_infos = []
        for idx, block in enumerate(blocks):
            info = {
                "md_index": idx,
                "is_table": self._is_markdown_table_block(block) or self._is_html_table_block(block),
                "text": block,
                "matched_cand": None, # Will store reference to candidate
                "matched_type": None # "text" or "table"
            }
            if not info["is_table"]:
                 # Extract plain text for matching
                m = re.match(r"^(#{1,6})\s+(.+)$", (block or "").strip())
                if m:
                    info["plain_text"] = m.group(2).strip()
                    info["text_level"] = len(m.group(1))
                else:
                    info["plain_text"] = self._strip_markdown_text(block)
                info["_prep"] = self._prep_text(info["plain_text"])
            
            block_infos.append(info)

        last_anchor_page = 0
        cand_ptr = 0
        t_ptr = 0

        for b_info in block_infos:
            if b_info["is_table"]:
                best_t_score = 0.0
                best_t_idx = -1
                b_text = (b_info.get("text") or "").strip()
                for i in range(t_ptr, len(table_candidates)):
                    t_cand = table_candidates[i]
                    t_id = t_cand["id"]
                    t_data = (content_tables or {}).get(t_id, {})
                    t_md = t_data.get("md", "")
                    t_html = t_data.get("html", "")
                    for t_content in (t_md, t_html):
                        if not t_content:
                            continue
                        score = self._calculate_text_similarity(b_text, t_content)
                        if score > best_t_score:
                            best_t_score = score
                            best_t_idx = i
                    if best_t_score >= 0.95:
                        break

                if best_t_idx == -1 or best_t_score < 0.55:
                    search_limit = min(len(table_candidates), t_ptr + 5)
                    for i in range(t_ptr, search_limit):
                        t_cand = table_candidates[i]
                        if t_cand["page_idx"] >= last_anchor_page - 1:
                            best_t_idx = i
                            break

                if best_t_idx != -1:
                    b_info["matched_cand"] = table_candidates[best_t_idx]
                    b_info["matched_type"] = "table"
                    b_info["is_anchor"] = True
                    t_ptr = best_t_idx + 1
                    last_anchor_page = max(last_anchor_page, table_candidates[best_t_idx]["page_idx"])
                elif t_ptr < len(table_candidates):
                    b_info["matched_cand"] = table_candidates[t_ptr]
                    b_info["matched_type"] = "table"
                    b_info["is_anchor"] = True
                    last_anchor_page = max(last_anchor_page, table_candidates[t_ptr]["page_idx"])
                    t_ptr += 1
                continue

            md_prep = b_info.get("_prep") or {}
            if not md_prep.get("compact"):
                continue

            target_len = md_prep.get("length") or 0
            if target_len >= 80:
                max_span = 8
            elif target_len >= 30:
                max_span = 6
            elif target_len >= 12:
                max_span = 4
            else:
                max_span = 1

            window_start = max(0, cand_ptr - 5)
            window_end = min(len(text_candidates), cand_ptr + 120)

            best = self._best_span_match(md_prep, text_candidates, window_start, window_end, max_span)
            if best and best.get("bbox") and best.get("page_idx") is not None and best.get("score", 0.0) >= 0.22:
                b_info["matched_cand"] = best
                b_info["matched_type"] = "text_span"
                cand_ptr = best["end"] + 1
                last_anchor_page = max(last_anchor_page, int(best["page_idx"]))
            else:
                if cand_ptr < len(text_candidates):
                    fallback_cand = text_candidates[cand_ptr]
                    if fallback_cand.get("bbox") is not None and fallback_cand.get("page_idx") is not None:
                        b_info["matched_cand"] = {
                            "start": cand_ptr,
                            "end": cand_ptr,
                            "score": 0.0,
                            "page_idx": fallback_cand.get("page_idx"),
                            "bbox": fallback_cand.get("bbox"),
                            "cands": [fallback_cand],
                        }
                        b_info["matched_type"] = "text_span"
                        cand_ptr += 1

        # --- Final Construction ---
        out_list = []
        for b_info in block_infos:
            item = {
                "md_index": b_info["md_index"],
                "type": "text"
            }
            if b_info["is_table"]:
                item["type"] = "table"
                
            if b_info.get("matched_cand"):
                cand = b_info["matched_cand"]
                if b_info["matched_type"] == "table":
                    item["id"] = cand.get("id")
                    item["bbox"] = cand.get("item", {}).get("bbox")
                    item["page_idx"] = cand.get("page_idx")
                elif b_info["matched_type"] == "text_span":
                    item["bbox"] = cand.get("bbox")
                    item["page_idx"] = cand.get("page_idx")
                    cands = cand.get("cands") or []
                    if cands:
                        item["source_raw_indices"] = [c.get("original_idx") for c in cands if c.get("original_idx") is not None]
                else:
                    item["bbox"] = cand.get("bbox")
                    item["page_idx"] = cand.get("page_idx")
                
                if item.get("text_level"):
                     item["text_level"] = b_info.get("text_level")
                
                # If text, we might want to copy text? Frontend doesn't strictly need it if bbox is there
                item["text"] = b_info.get("plain_text", "")
            
            out_list.append(item)
            
        return out_list, md_text

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
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                
            async with httpx.AsyncClient(verify=False, timeout=300.0, trust_env=False) as client:
                with open(pdf_path, "rb") as f:
                    files = {'files': (filename, f, 'application/pdf')}
                    data = {
                        "return_middle_json": "false",
                        "return_content_list": "true",
                        "return_md": "true"
                    }
                    try:
                        response = await client.post(
                            f"{api_url}/file_parse",
                            files=files,
                            data=data,
                            headers=headers
                        )
                    except httpx.ReadError as e:
                        print(f"[{self.name}] Connection/Read error: {e}")
                        raise HTTPException(status_code=502, detail=f"Failed to read response from MinerU API. This usually means the server closed the connection prematurely or a timeout occurred. Details: {str(e)}")
                    except httpx.ConnectError as e:
                        print(f"[{self.name}] Connection error: {e}")
                        raise HTTPException(status_code=502, detail=f"Failed to connect to MinerU API at {api_url}. Please check if the URL is correct and accessible. Details: {str(e)}")
            
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
            # raw_content_list.json: Save original MinerU content list for comparison
            write_json_file(os.path.join(task_result_dir, "raw_content_list.json"), raw_content_list)
            # content_tables.json: Use GMFT extracted detailed cell info
            write_json_file(os.path.join(task_result_dir, "content_tables.json"), final_content_tables)
            
            return {
                "md_url": f"content.md",
                "content_list_url": f"content_list.json",
                "raw_content_list_url": f"raw_content_list.json",
                "content_tables_url": f"content_tables.json",
            }

        except HTTPException as e:
            raise e
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"{self.name} Error: {str(e)}")
