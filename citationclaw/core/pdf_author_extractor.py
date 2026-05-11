"""Extract authors and affiliations from PDF content using lightweight LLM."""
import json
from typing import List, Optional

from citationclaw.config.prompt_loader import PromptLoader
from citationclaw.core.http_utils import make_async_client


class PDFAuthorExtractor:
    """Extract authors + affiliations from PDF full content via lightweight LLM."""

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/") + "/" if base_url else ""
        self._model = model
        self._prompt_loader = PromptLoader()

    async def extract(self, blocks: list) -> List[dict]:
        """Send PDF text blocks to lightweight LLM, return author list.

        Returns: [{"name": "...", "affiliation": "...", "email": "..."}]
        """
        if not self._api_key or not blocks:
            return []

        # Build text from blocks
        lines = []
        for i, b in enumerate(blocks):
            text = b.get("text", "").strip() if isinstance(b, dict) else str(b).strip()
            if text:
                lines.append(f"[{i}] {text}")
        if not lines:
            return []

        first_page_text = "\n".join(lines)
        prompt = self._prompt_loader.render("pdf_author_extract",
                                            first_page_text=first_page_text)

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                http_client=make_async_client(timeout=60.0),
            )
            response = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            text = response.choices[0].message.content.strip()
            return self._parse_response(text)
        except Exception:
            return []

    @staticmethod
    def _parse_response(text: str) -> List[dict]:
        """Parse LLM JSON response into author list."""
        # Try to find JSON array in the response
        import re
        # Remove markdown code fences if present
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [
                    {
                        "name": a.get("name", "").strip(),
                        "affiliation": a.get("affiliation", "").strip(),
                        "email": a.get("email", "").strip(),
                    }
                    for a in data if a.get("name", "").strip()
                ]
        except json.JSONDecodeError:
            pass
        return []
