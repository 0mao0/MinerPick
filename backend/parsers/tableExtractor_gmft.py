import os
from typing import List, Dict, Any
from gmft.auto import AutoTableFormatter
from gmft.detectors.base import CroppedTable
from gmft.pdf_bindings import PyPDFium2Document

class GMFTTableExtractor:
    """
    Hybrid table extractor using gmft for precise formatting and cell detection,
    guided by MinerU's layout coordinates.
    """
    
    def __init__(self):
        self.formatter = AutoTableFormatter()

    def _normalize_bbox(self, rect, width: float, height: float) -> List[int]:
        if not rect:
            return [0, 0, 0, 0]
        x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
        return [
            int(x0 / width * 1000),
            int(y0 / height * 1000),
            int(x1 / width * 1000),
            int(y1 / height * 1000),
        ]

    def get_cell_bboxes(self, ft, table_bbox, page_width, page_height, page_idx):
        """
        Extract cell-level bboxes from a FormattedTable object.
        Uses ft.cells if available (GMFT > 0.3), otherwise falls back to row/col intersection.
        """
        cells = []
        
        # 1. Try using ft.cells (most accurate as it reflects GMFT's internal structure)
        if hasattr(ft, 'cells') and ft.cells:
            for cell in ft.cells:
                # cell.bbox is usually [x0, y0, x1, y1] relative to the table image
                # We need to add the table's offset (table_bbox)
                
                # Check if cell has bbox
                if not hasattr(cell, 'bbox'):
                    continue
                    
                c_bbox = cell.bbox
                abs_box = [
                    table_bbox[0] + c_bbox[0],
                    table_bbox[1] + c_bbox[1],
                    table_bbox[0] + c_bbox[2],
                    table_bbox[1] + c_bbox[3]
                ]
                
                cells.append({
                    "r": cell.row_index if hasattr(cell, 'row_index') else getattr(cell, 'row', 0),
                    "c": cell.col_index if hasattr(cell, 'col_index') else getattr(cell, 'col', 0),
                    "is_header": getattr(cell, 'is_header', False), # Some versions might not have this
                    "page_idx": page_idx,
                    "bbox": self._normalize_bbox(abs_box, page_width, page_height)
                })
            
            # If we successfully extracted cells, return them
            if cells:
                return cells

        # 2. Fallback: Intersect rows and cols from TATR predictions
        if not hasattr(ft, 'predictions') or not hasattr(ft.predictions, 'tatr'):
            return []
        
        tatr = ft.predictions.tatr
        boxes = tatr.get('boxes', [])
        labels = tatr.get('labels', [])
        
        rows = []
        cols = []
        headers = []
        
        for box, label in zip(boxes, labels):
            abs_box = [
                table_bbox[0] + box[0],
                table_bbox[1] + box[1],
                table_bbox[0] + box[2],
                table_bbox[1] + box[3]
            ]
            
            if label == 2: # Row
                rows.append(abs_box)
            elif label == 3: # Header Row
                rows.append(abs_box)
                headers.append(abs_box)
            elif label == 1: # Column
                cols.append(abs_box)
        
        if not rows or not cols:
            return []

        def deduplicate(boxes, coord_idx):
            if not boxes: return []
            boxes.sort(key=lambda b: b[coord_idx])
            unique = [boxes[0]]
            for i in range(1, len(boxes)):
                # If overlap is high or distance is small, merge
                if abs(boxes[i][coord_idx] - unique[-1][coord_idx]) < 8:
                    # Update existing box to be the union
                    unique[-1] = [
                        min(unique[-1][0], boxes[i][0]),
                        min(unique[-1][1], boxes[i][1]),
                        max(unique[-1][2], boxes[i][2]),
                        max(unique[-1][3], boxes[i][3])
                    ]
                else:
                    unique.append(boxes[i])
            return unique

        rows = deduplicate(rows, 1) # y0
        cols = deduplicate(cols, 0) # x0
        
        cells = []
        for r_idx, r_box in enumerate(rows):
            # Check if this row is a header
            is_header = False
            for h_box in headers:
                # Check vertical overlap
                overlap = min(r_box[3], h_box[3]) - max(r_box[1], h_box[1])
                if overlap > (r_box[3] - r_box[1]) * 0.7:
                    is_header = True
                    break

            for c_idx, c_box in enumerate(cols):
                cell_bbox_pts = [
                    c_box[0],
                    r_box[1],
                    c_box[2],
                    r_box[3]
                ]
                cells.append({
                    "r": r_idx,
                    "c": c_idx,
                    "is_header": is_header,
                    "page_idx": page_idx,
                    "bbox": self._normalize_bbox(cell_bbox_pts, page_width, page_height)
                })
                
        return cells

    def extract_tables_from_pdf(self, pdf_path: str, mineru_content_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Perform hybrid extraction using gmft on regions identified by MinerU (or PyMuPDF).
        """
        # print(f"[GMFT] Starting guided extraction on {pdf_path}")
        
        final_content_tables = {}
        
        try:
            doc = PyPDFium2Document(pdf_path)
            
            for page_idx, page in enumerate(doc):
                # Get page dimensions from pypdfium2 (returns points, same as fitz)
                # gmft PyPDFium2Page has width/height attributes
                width, height = page.width, page.height
                
                # Find MinerU tables for this page
                page_mineru_tables = [
                    item for item in mineru_content_list 
                    if item.get("page_idx") == page_idx and item.get("type") == "table"
                ]
                
                if not page_mineru_tables:
                    continue
                
                for m_table in page_mineru_tables:
                    m_id = str(m_table.get("id"))
                    m_bbox = m_table.get("bbox")
                    if not m_bbox:
                        continue
                    
                    # Scale MinerU bbox (1000x1000) to points
                    pts_bbox = [
                        m_bbox[0] * width / 1000,
                        m_bbox[1] * height / 1000,
                        m_bbox[2] * width / 1000,
                        m_bbox[3] * height / 1000
                    ]
                    
                    try:
                        cropped_table = CroppedTable(page, pts_bbox)
                        ft = self.formatter.format(cropped_table)
                        df = ft.df()
                        
                        cell_bboxes = self.get_cell_bboxes(ft, pts_bbox, width, height, page_idx)
                        
                        final_content_tables[m_id] = {
                            "page_idx": page_idx,
                            "bbox": m_bbox, # Keep MinerU's normalized bbox
                            "cells": cell_bboxes,
                            "md": df.to_markdown(index=False),
                            "html": df.to_html(index=False)
                        }
                        # print(f"  [GMFT] Successfully extracted table {m_id} on page {page_idx}")
                    except Exception as fe:
                        # print(f"  [GMFT] Error formatting table {m_id} on page {page_idx}: {fe}")
                        pass
            
            doc.close()
        except Exception as e:
            # print(f"[GMFT] Extraction failed: {e}")
            pass
            
        return final_content_tables
