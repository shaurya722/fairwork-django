"""Generic document processing for multiple file types.

Supports:
- PDF files (via PyPDF2)
- Text files (.txt, .md)
- Word documents (.docx) - if python-docx is installed
- HTML files

Chunks documents and prepares them for vector indexing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    import docx
except ImportError:
    docx = None


class DocumentProcessingError(Exception):
    """Raised when document processing fails."""
    pass


def detect_file_type(filename: str) -> str:
    """Detect file type from extension."""
    ext = Path(filename).suffix.lower()
    if ext == '.pdf':
        return 'pdf'
    elif ext in ('.txt', '.md', '.markdown'):
        return 'text'
    elif ext in ('.docx', '.doc'):
        return 'docx'
    elif ext in ('.html', '.htm'):
        return 'html'
    else:
        return 'unknown'


def read_pdf(file_path: str | Path) -> list[dict[str, Any]]:
    """Read PDF and return list of pages with text content."""
    if PdfReader is None:
        raise DocumentProcessingError(
            "PyPDF2 is not installed. Run: pip install PyPDF2"
        )
    
    try:
        reader = PdfReader(str(file_path))
        pages = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({
                    'page_num': page_num,
                    'text': text.strip()
                })
        return pages
    except Exception as exc:
        raise DocumentProcessingError(f"Failed to read PDF: {exc}") from exc


def read_text_file(file_path: str | Path) -> list[dict[str, Any]]:
    """Read plain text file and return as single 'page'."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        return [{'page_num': 1, 'text': text.strip()}]
    except Exception as exc:
        raise DocumentProcessingError(f"Failed to read text file: {exc}") from exc


def read_docx(file_path: str | Path) -> list[dict[str, Any]]:
    """Read Word document and return paragraphs as 'pages'."""
    if docx is None:
        raise DocumentProcessingError(
            "python-docx is not installed. Run: pip install python-docx"
        )
    
    try:
        doc = docx.Document(str(file_path))
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)
        
        # Group paragraphs into logical pages (every 50 paragraphs)
        pages = []
        page_size = 50
        for i in range(0, len(paragraphs), page_size):
            page_text = '\n\n'.join(paragraphs[i:i+page_size])
            pages.append({
                'page_num': (i // page_size) + 1,
                'text': page_text
            })
        return pages
    except Exception as exc:
        raise DocumentProcessingError(f"Failed to read DOCX: {exc}") from exc


def read_html(file_path: str | Path) -> list[dict[str, Any]]:
    """Read HTML file and extract text content."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Simple HTML tag removal (for basic HTML)
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return [{'page_num': 1, 'text': text}]
    except Exception as exc:
        raise DocumentProcessingError(f"Failed to read HTML: {exc}") from exc


def read_document(file_path: str | Path) -> list[dict[str, Any]]:
    """Read any supported document type and return pages."""
    file_type = detect_file_type(str(file_path))
    
    if file_type == 'pdf':
        return read_pdf(file_path)
    elif file_type == 'text':
        return read_text_file(file_path)
    elif file_type == 'docx':
        return read_docx(file_path)
    elif file_type == 'html':
        return read_html(file_path)
    else:
        raise DocumentProcessingError(
            f"Unsupported file type: {Path(file_path).suffix}. "
            f"Supported: .pdf, .txt, .md, .docx, .html"
        )


def chunk_text(text: str, chunk_chars: int = 3600, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_chars length.
    
    Args:
        text: Text to chunk
        chunk_chars: Target size per chunk in characters
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_chars:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_chars
        
        # Try to break at a sentence boundary
        if end < len(text):
            # Look for sentence endings within the last 20% of the chunk
            search_start = end - int(chunk_chars * 0.2)
            search_text = text[search_start:end + 100]
            
            # Find last sentence boundary
            for delimiter in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
                pos = search_text.rfind(delimiter)
                if pos != -1:
                    end = search_start + pos + len(delimiter)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start forward, with overlap
        start = end - overlap if end < len(text) else end
    
    return chunks


def chunk_document(
    file_path: str | Path,
    chunk_chars: int = 3600,
    document_type: str = 'other',
    title: str = ''
) -> list[dict[str, Any]]:
    """Process a document and return embeddable chunks.
    
    Args:
        file_path: Path to the document file
        chunk_chars: Approximate character size per chunk
        document_type: Type of document (for metadata)
        title: Document title (for metadata)
    
    Returns:
        List of chunk dicts with: {chunk_index, content, page_start, page_end, 
        section, token_estimate}
    """
    pages = read_document(file_path)
    
    if not pages:
        raise DocumentProcessingError(f"No text extracted from {file_path}")
    
    chunks = []
    global_index = 0
    
    # Process each page
    for page in pages:
        page_num = page['page_num']
        page_text = page['text']
        
        # Detect section headers (lines that are all caps or start with numbers)
        lines = page_text.split('\n')
        section = ''
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line and (line.isupper() or re.match(r'^\d+\.?\s+[A-Z]', line)):
                section = line[:100]
                break
        
        if not section:
            section = f"Page {page_num}"
        
        # Chunk the page text
        page_chunks = chunk_text(page_text, chunk_chars)
        
        for text_chunk in page_chunks:
            content = f"[{document_type.upper()}] {title}\n\n{text_chunk}".strip()
            
            chunks.append({
                'chunk_index': global_index,
                'content': content,
                'page_start': page_num,
                'page_end': page_num,
                'section': section,
                'token_estimate': max(1, len(content) // 4),
            })
            global_index += 1
    
    if not chunks:
        raise DocumentProcessingError(
            "Parsed 0 chunks - the document may be empty or unsupported."
        )
    
    return chunks


def make_vector_id(document_id: int, chunk_index: int, namespace: str = '') -> str:
    """Generate a stable Pinecone vector ID for a document chunk."""
    if namespace:
        ns_slug = re.sub(r'[^a-z0-9]+', '-', namespace.lower())[:40].strip('-')
        return f"{ns_slug}-doc{document_id}-{chunk_index}"
    return f"doc{document_id}-{chunk_index}"


def get_page_count(file_path: str | Path) -> int:
    """Get the number of pages in a document."""
    file_type = detect_file_type(str(file_path))
    
    if file_type == 'pdf':
        if PdfReader is None:
            return 0
        try:
            return len(PdfReader(str(file_path)).pages)
        except:
            return 0
    else:
        # For non-PDF files, return 1 (single "page")
        return 1


__all__ = [
    'DocumentProcessingError',
    'detect_file_type',
    'read_document',
    'chunk_document',
    'make_vector_id',
    'get_page_count',
]
