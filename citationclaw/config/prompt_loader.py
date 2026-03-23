from pathlib import Path
from typing import Optional

_DEFAULT_DIR = Path(__file__).parent / "prompts"


class PromptLoader:
    """Load and render prompt templates from config/prompts/ directory."""

    def __init__(self, prompt_dir: Optional[Path] = None):
        self._dir = prompt_dir or _DEFAULT_DIR

    def get(self, name: str) -> str:
        path = self._dir / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")
        return path.read_text(encoding="utf-8")

    def render(self, template_name: str, **kwargs) -> str:
        template = self.get(template_name)
        return template.format(**kwargs)
