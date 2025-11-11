from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class ExtractedDoc:
    """Represents an extracted document.

    Attributes:
        doc_id: The unique ID of the document.
        source_path: The path to the source file.
        pages: A list of strings, where each string is the text of a page.
        images: A list of dictionaries, where each dictionary represents an
            image in the document.
    """
    doc_id: str          # uuid4
    source_path: str
    pages: List[str]     # one string per page; if not a PDF, single page
    images: List[Dict[str, Any]]   # sha1, page, bbox, saved_path, ocr_text (if any)


@dataclass
class Sentence:
    """Represents a single sentence.

    Attributes:
        doc_id: The ID of the document the sentence is in.
        sent_id: The unique ID of the sentence.
        page: The page number the sentence is on.
        text: The text of the sentence.
        char_start: The start character offset of the sentence.
        char_end: The end character offset of the sentence.
    """
    doc_id: str
    sent_id: str         # sha1(doc_id|page|char_start|char_end)[:16]
    page: Optional[int]
    text: str
    char_start: int
    char_end: int


@dataclass
class Chunk:
    """Represents a chunk of text.

    Attributes:
        doc_id: The ID of the document the chunk is in.
        chunk_id: The unique ID of the chunk.
        text: The text of the chunk.
        sentence_ids: A list of sentence IDs in the chunk.
        page_start: The starting page number of the chunk.
        page_end: The ending page number of the chunk.
    """
    doc_id: str
    chunk_id: str        # sha1(doc_id|first_sent_id|last_sent_id)[:16]
    text: str
    sentence_ids: List[str]
    page_start: Optional[int]
    page_end: Optional[int]

