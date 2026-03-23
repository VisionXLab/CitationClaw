"""PDF citation context parser using PyMuPDF (fitz).

Extracts paragraphs containing citations to the target paper.
"""
import re
from pathlib import Path
from typing import Optional, List

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

SECTION_PATTERNS = [
    (r'(?:^|\n)\s*\d*\.?\s*(Introduction)', "Introduction"),
    (r'(?:^|\n)\s*\d*\.?\s*(Related\s+Work)', "Related Work"),
    (r'(?:^|\n)\s*\d*\.?\s*(Background)', "Background"),
    (r'(?:^|\n)\s*\d*\.?\s*(Method(?:ology|s)?)', "Method"),
    (r'(?:^|\n)\s*\d*\.?\s*(Experiment(?:s|al)?)', "Experiments"),
    (r'(?:^|\n)\s*\d*\.?\s*(Results?)', "Results"),
    (r'(?:^|\n)\s*\d*\.?\s*(Discussion)', "Discussion"),
    (r'(?:^|\n)\s*\d*\.?\s*(Conclusion(?:s)?)', "Conclusion"),
    (r'(?:^|\n)\s*\d*\.?\s*(Abstract)', "Abstract"),
]


class PDFCitationParser:
    """Parse PDF and find paragraphs citing the target paper."""

    def extract_citation_contexts(self, pdf_path: Path, target_title: str,
                                   target_authors: List[str]) -> List[dict]:
        """Parse PDF and find paragraphs citing the target paper."""
        if fitz is None:
            return []
        if not pdf_path.exists():
            return []
        doc = fitz.open(str(pdf_path))
        full_text = "\n".join(page.get_text() for page in doc)
        doc.close()

        ref_id = self._find_reference_id(full_text, target_title, target_authors)
        contexts = self._extract_contexts(full_text, ref_id, target_title)

        return [{
            "section": self._detect_section(ctx),
            "text": ctx.strip(),
            "source": "pdf",
        } for ctx in contexts]

    def _find_reference_id(self, text: str, target_title: str,
                            target_authors: List[str]) -> Optional[str]:
        """Find the reference number [N] for the target paper."""
        # Look for references section
        ref_section_match = re.search(
            r'(?:References|Bibliography|REFERENCES)\s*\n(.*)',
            text, re.DOTALL
        )
        if not ref_section_match:
            return None

        ref_text = ref_section_match.group(1)

        # Search for target title in references
        title_words = target_title.lower().split()[:5]  # First 5 words
        title_pattern = r'\s+'.join(re.escape(w) for w in title_words)

        for line in ref_text.split('\n'):
            if re.search(title_pattern, line, re.IGNORECASE):
                # Extract reference number
                ref_match = re.match(r'\s*\[(\d+)\]', line)
                if ref_match:
                    return f"[{ref_match.group(1)}]"

        # Try author-based matching
        for author in target_authors:
            surname = author.split()[-1] if author.split() else ""
            if not surname:
                continue
            for line in ref_text.split('\n'):
                if surname.lower() in line.lower() and any(
                    w.lower() in line.lower() for w in title_words[:3]
                ):
                    ref_match = re.match(r'\s*\[(\d+)\]', line)
                    if ref_match:
                        return f"[{ref_match.group(1)}]"

        return None

    def _extract_contexts(self, text: str, ref_id: Optional[str],
                           target_title: str) -> List[str]:
        """Extract paragraphs containing citations to the target."""
        contexts = []

        # Remove references section for context extraction
        ref_start = re.search(r'(?:References|Bibliography|REFERENCES)\s*\n', text)
        body_text = text[:ref_start.start()] if ref_start else text

        paragraphs = re.split(r'\n\s*\n', body_text)

        for para in paragraphs:
            para = para.strip()
            if not para or len(para) < 30:
                continue

            found = False
            # Match by reference ID
            if ref_id and ref_id in para:
                found = True
            # Match by title mention
            title_words = target_title.split()[:4]
            if len(title_words) >= 3:
                if all(w.lower() in para.lower() for w in title_words):
                    found = True

            if found:
                contexts.append(para)

        return contexts

    def _detect_section(self, text: str) -> str:
        """Detect which section a text snippet belongs to."""
        for pattern, section_name in SECTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return section_name
        return "Unknown"
