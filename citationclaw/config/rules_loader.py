import yaml
from pathlib import Path
from typing import Optional

_DEFAULT_DIR = Path(__file__).parent / "rules"


class RulesLoader:
    """Load YAML rule configurations from config/rules/ directory."""

    def __init__(self, rules_dir: Optional[Path] = None):
        self._dir = rules_dir or _DEFAULT_DIR

    def get(self, name: str) -> dict:
        path = self._dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Rule file not found: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
