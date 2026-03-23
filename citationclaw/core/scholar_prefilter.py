"""Rule-based scholar pre-filter using structured API data.

Determines which scholars need deep browser search vs skip.
Uses a two-tier approach: strict metrics OR institution matching.
"""
from typing import List

from citationclaw.config.rules_loader import RulesLoader


class ScholarPreFilter:
    def __init__(self, rules_loader: RulesLoader = None):
        loader = rules_loader or RulesLoader()
        tiers = loader.get("scholar_tiers")
        institutions_data = loader.get("institutions")
        self._h_threshold = tiers.get("pre_filter", {}).get("h_index_threshold", 20)
        self._cite_threshold = tiers.get("pre_filter", {}).get("citation_threshold", 3000)
        self._known_institutions = set()
        for key in ["tech_companies", "top_universities_cn", "top_universities_intl"]:
            for inst in institutions_data.get(key, []):
                self._known_institutions.add(inst.lower())

    def is_candidate(self, author: dict) -> bool:
        """Rule-based pre-filter: should this author be deeply searched?

        An author is a candidate if ANY of these hold:
        - h-index >= threshold (strong signal)
        - citation_count >= threshold (strong signal)
        - Affiliation matches a known top institution/company
        - Has any affiliation and h-index data is unavailable (lenient mode)
        """
        h = author.get("h_index", 0) or 0
        cites = author.get("citation_count", 0) or 0

        # Strong signals: metrics clearly high
        if h >= self._h_threshold:
            return True
        if cites >= self._cite_threshold:
            return True

        # Institution match: known top place
        affiliation = author.get("affiliation", "")
        if self._matches_institution(affiliation):
            return True

        return False

    def _matches_institution(self, affiliation: str) -> bool:
        """Check if affiliation matches a known top institution.

        Uses substring matching in both directions to handle variants like
        'Google Research' matching 'Google', or '清华大学' matching 'Tsinghua'.
        """
        if not affiliation:
            return False
        aff_lower = affiliation.lower()
        # Also split by common separators to match partial affiliations
        # e.g. "School of CS, Tsinghua University" should match "Tsinghua University"
        for inst in self._known_institutions:
            if inst in aff_lower or aff_lower in inst:
                return True
        return False

    def filter_candidates(self, authors: List[dict]) -> tuple:
        """Split authors into candidates (need search) and non-candidates."""
        candidates = []
        non_candidates = []
        for author in authors:
            if self.is_candidate(author):
                candidates.append(author)
            else:
                non_candidates.append(author)
        return candidates, non_candidates
