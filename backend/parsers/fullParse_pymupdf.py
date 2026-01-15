from typing import Dict, Any
from .base import BaseParser

class PyMuPDFParser(BaseParser):
    @property
    def name(self) -> str:
        return "PyMuPDF"

    def __init__(self):
        ...

    async def parse(self, pdf_path: str, task_result_dir: str, **kwargs) -> Dict[str, Any]:
        """
        PyMuPDF-based parsing logic (Placeholder for future expansion).
        Currently returns empty results as it's grayed out in frontend.
        """
        # print(f"[{self.name}] Parser is currently a placeholder and does not perform extraction.")
        
        return {
            "md_url": None,
            "content_list_url": None,
            "content_tables_url": None,
        }
