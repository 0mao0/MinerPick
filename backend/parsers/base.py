import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List
import os
import json

class BaseParser(ABC):
    @abstractmethod
    async def parse(self, pdf_path: str, task_result_dir: str, **kwargs) -> Dict[str, Any]:
        """
        解析 PDF 并返回结果。
        
        :param pdf_path: PDF 文件的路径
        :param task_result_dir: 任务结果存储目录
        :return: 包含 md_url, middle_json_url, content_list_url 等的字典
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """解析器名称"""
        pass

    def _split_markdown_blocks(self, md_text: str) -> List[str]:
        src = (md_text or "").replace("\r\n", "\n").strip()
        if not src:
            return []
        table_re = re.compile(r"<table[\s\S]*?</table>", re.IGNORECASE)

        blocks: List[str] = []
        last_end = 0
        for m in table_re.finditer(src):
            before = src[last_end : m.start()]
            if before.strip():
                blocks.extend([b.strip() for b in re.split(r"\n{2,}", before) if b and b.strip()])

            table_block = m.group(0)
            if table_block and table_block.strip():
                blocks.append(table_block.strip())
            last_end = m.end()

        tail = src[last_end:]
        if tail.strip():
            blocks.extend([b.strip() for b in re.split(r"\n{2,}", tail) if b and b.strip()])

        return blocks

    def _is_markdown_table_block(self, block: str) -> bool:
        if not block:
            return False
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 2:
            return False
        if "|" not in lines[0]:
            return False
        if re.search(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$", lines[1]):
            return True
        return False

    def _is_html_table_block(self, block: str) -> bool:
        if not block:
            return False
        s = block.strip().lower()
        return "<table" in s and "</table>" in s

    def _strip_markdown_text(self, block: str) -> str:
        text = (block or "").strip()
        if not text:
            return ""
        text = re.sub(r"^#{1,6}\s+", "", text)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"`{1,3}([^`]+)`{1,3}", r"\1", text)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()



def _coerce_json_value(data: Any) -> Any:
    if not isinstance(data, str):
        return data
    try:
        parsed = json.loads(data)
    except Exception:
        return data
    if isinstance(parsed, str):
        try:
            return json.loads(parsed)
        except Exception:
            return parsed
    return parsed


def normalize_content_list(data: Any) -> Any:
    data = _coerce_json_value(data)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict) and item.get("type") != "discarded"]
    if isinstance(data, dict):
        content_list = data.get("content_list")
        if isinstance(content_list, list):
            data = dict(data)
            data["content_list"] = [item for item in content_list if isinstance(item, dict) and item.get("type") != "discarded"]
        return data
    return data


def write_text_file(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")


def write_json_file(path: str, data: Any) -> Any:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = _coerce_json_value(data)
    if os.path.basename(path) == "content_list.json":
        data = normalize_content_list(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data
