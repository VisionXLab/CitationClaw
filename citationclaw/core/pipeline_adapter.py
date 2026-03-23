"""Bridge between new structured-API outputs and legacy export format."""
import json
from typing import Optional, List
from citationclaw.core.scholar_search_agent import ScholarSearchAgent


class PipelineAdapter:
    """Convert between new pipeline data and legacy record format."""

    def flatten_phase1_line(self, line_data: dict) -> list:
        """Flatten one Phase 1 JSONL line (page-based) into individual papers."""
        papers = []
        for page_id, page_content in line_data.items():
            paper_dict = page_content.get("paper_dict", {})
            for paper_id, paper_info in paper_dict.items():
                papers.append({
                    "page_id": page_id,
                    "paper_id": paper_id,
                    "paper_title": paper_info.get("paper_title", ""),
                    "paper_link": paper_info.get("paper_link", ""),
                    "paper_year": paper_info.get("paper_year"),
                    "citation": paper_info.get("citation", "0"),
                    "authors_raw": paper_info.get("authors", {}),
                })
        return papers

    def flatten_phase1_file(self, file_path) -> list:
        """Read Phase 1 JSONL file and flatten all pages into paper list."""
        all_papers = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                all_papers.extend(self.flatten_phase1_line(data))
        return all_papers

    def to_legacy_record(
        self,
        paper: dict,
        metadata: Optional[dict],
        self_citation: dict,
        renowned_scholars: list,
        citing_paper: str,
        record_index: int,
    ) -> dict:
        """Convert new pipeline data into legacy {index: record} format.

        This produces the exact format Phase 3 Export expects:
          {"1": {"Paper_Title": ..., "Searched Author-Affiliation": ..., ...}}
        """
        authors = (metadata or {}).get("authors", [])
        sources = (metadata or {}).get("sources", [])

        # Fallback: if API returned no authors, build from Google Scholar data
        if not authors and paper.get("authors_raw"):
            import re as _re
            for key in paper["authors_raw"]:
                # key format: "author_0_W Liang" → extract "W Liang"
                match = _re.match(r'author_\d+_(.*)', key)
                name = match.group(1) if match else key
                if name:
                    authors.append({"name": name, "affiliation": "", "country": ""})
            if not sources:
                sources = ["scholar"]

        # Build author-affiliation string (name\naffiliation pairs)
        affil_lines = []
        for a in authors:
            affil_lines.append(a.get("name", ""))
            affil_lines.append(a.get("affiliation", "") or "未知机构")
        searched_affiliation = "\n".join(affil_lines)

        # First author info (normalize country to Chinese)
        first_author = authors[0] if authors else {}
        first_inst = first_author.get("affiliation", "")
        first_country = ScholarSearchAgent._normalize_country(
            first_author.get("country", "")
        )

        # Build author info summary
        author_info_parts = []
        for a in authors:
            parts = [a.get("name", "")]
            if a.get("affiliation"):
                parts.append(f"机构: {a['affiliation']}")
            if a.get("country"):
                parts.append(f"国家: {a['country']}")
            if a.get("h_index"):
                parts.append(f"h-index: {a['h_index']}")
            author_info_parts.append(", ".join(parts))
        searched_info = "\n".join(author_info_parts)

        # Build renowned scholar fields
        renowned_text = ""
        formatted_scholars = []
        for s in renowned_scholars:
            honors_str = ", ".join(s.get("honors", []))
            renowned_text += f"{s.get('name', '')} ({s.get('tier', '')}: {honors_str})\n"
            formatted_scholars.append({
                "name": s.get("name", ""),
                "institution": s.get("affiliation", ""),
                "country": s.get("country", ""),
                "position": s.get("position", "") or s.get("tier", ""),
                "titles": honors_str,
            })

        # Authors with profile (preserve original GS format)
        authors_with_profile = json.dumps(
            paper.get("authors_raw", {}), ensure_ascii=False
        )

        record = {
            "PageID": paper.get("page_id", ""),
            "PaperID": paper.get("paper_id", ""),
            "Paper_Title": paper.get("paper_title", ""),
            "Paper_Year": paper.get("paper_year"),
            "Paper_Link": paper.get("paper_link", ""),
            "Citations": paper.get("citation", "0"),
            "Authors_with_Profile": authors_with_profile,
            "Searched Author-Affiliation": searched_affiliation,
            "First_Author_Institution": first_inst,
            "First_Author_Country": first_country,
            "Citing_Paper": citing_paper,
            "Is_Self_Citation": self_citation.get("is_self_citation", False),
            "Searched Author Information": searched_info,
            "Author Verification": "",
            "Renowned Scholar": renowned_text.strip(),
            "Formated Renowned Scholar": formatted_scholars,
            "Data_Sources": ",".join(sources),
            "pdf_url": (metadata or {}).get("pdf_url", ""),
            "doi": (metadata or {}).get("doi", ""),
        }
        return {str(record_index): record}
