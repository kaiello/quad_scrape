from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class ExtractedDoc:
    doc_id: str          # uuid4
    source_path: str
    pages: List[str]     # one string per page; if not a PDF, single page
    images: List[Dict[str, Any]]   # sha1, page, bbox, saved_path, ocr_text (if any)


@dataclass
class Sentence:
    doc_id: str
    sent_id: str         # sha1(doc_id|page|char_start|char_end)[:16]
    page: Optional[int]
    text: str
    char_start: int
    char_end: int


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str        # sha1(doc_id|first_sent_id|last_sent_id)[:16]
    text: str
    sentence_ids: List[str]
    page_start: Optional[int]
    page_end: Optional[int]

