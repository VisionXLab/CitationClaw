import yaml
from pathlib import Path
from typing import Optional

_DEFAULT_FILE = Path(__file__).parent / "providers.yaml"


class ProviderManager:
    def __init__(self, config_file: Optional[Path] = None):
        path = config_file or _DEFAULT_FILE
        with open(path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f)
        self._presets = self._data.get("presets", {})

    def list_presets(self) -> list:
        return list(self._presets.keys())

    def get_preset(self, name: str) -> dict:
        if name not in self._presets:
            raise KeyError(f"Unknown provider: {name}")
        return self._presets[name]

    def build_config(self, provider: str, api_key: str,
                     model: Optional[str] = None,
                     base_url: Optional[str] = None) -> dict:
        preset = self._presets.get(provider, {})
        return {
            "api_key": api_key,
            "base_url": base_url or preset.get("base_url", ""),
            "model": model or preset.get("default_model", ""),
        }
