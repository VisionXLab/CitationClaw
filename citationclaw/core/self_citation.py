"""Rule-based self-citation detection with LLM fallback.

Uses structured author data from APIs instead of LLM-searched text.
Most cases resolved by name matching alone.
"""
from typing import List, Optional
import re


def _normalize_name(name: str) -> str:
    """Normalize author name for comparison."""
    name = name.lower().strip()
    name = re.sub(r'[^\w\s]', '', name)
    # Remove single-letter initials like "X." or "X "
    parts = [p for p in name.split() if len(p) > 1]
    return " ".join(sorted(parts))


def _extract_surname(name: str) -> str:
    """Extract likely surname (last word for Western, first for Chinese)."""
    parts = name.strip().split()
    if not parts:
        return ""
    # Check if name looks Chinese (contains CJK characters)
    if any('\u4e00' <= c <= '\u9fff' for c in name):
        # Chinese surname is the first character (even if no spaces)
        return name.strip()[0]
    return parts[-1].lower()  # Western surname is last


class SelfCitationDetector:
    """Detect self-citations using structured author lists."""

    def check(self, target_authors: List[dict], citing_authors: List[dict]) -> dict:
        """
        Rule-based self-citation check.

        Args:
            target_authors: List of {"name": str, "affiliation": str, ...}
            citing_authors: List of {"name": str, "affiliation": str, ...}

        Returns:
            {"is_self_citation": bool, "method": "exact"|"fuzzy"|"none",
             "matched_pair": Optional[tuple]}
        """
        # Step 1: Exact normalized name match
        exact = self._exact_match(target_authors, citing_authors)
        if exact:
            return {"is_self_citation": True, "method": "exact", "matched_pair": exact}

        # Step 2: Fuzzy match (surname + affiliation)
        fuzzy = self._fuzzy_match(target_authors, citing_authors)
        if fuzzy:
            return {"is_self_citation": True, "method": "fuzzy", "matched_pair": fuzzy}

        return {"is_self_citation": False, "method": "none", "matched_pair": None}

    def _exact_match(self, target: List[dict], citing: List[dict]) -> Optional[tuple]:
        """Check if any normalized name appears in both lists."""
        target_names = {_normalize_name(a.get("name", "")) for a in target}
        for c in citing:
            cn = _normalize_name(c.get("name", ""))
            if cn and cn in target_names:
                return (cn, cn)
        return None

    def _fuzzy_match(self, target: List[dict], citing: List[dict]) -> Optional[tuple]:
        """Surname match + same affiliation → likely same person."""
        for t in target:
            t_surname = _extract_surname(t.get("name", ""))
            t_affil = t.get("affiliation", "").lower()
            if not t_surname:
                continue
            for c in citing:
                c_surname = _extract_surname(c.get("name", ""))
                c_affil = c.get("affiliation", "").lower()
                if t_surname == c_surname and t_affil and c_affil:
                    # Same surname + overlapping affiliation
                    if t_affil in c_affil or c_affil in t_affil:
                        return (t.get("name", ""), c.get("name", ""))
        return None
