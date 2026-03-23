import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.config.provider_manager import ProviderManager

def test_list_presets():
    pm = ProviderManager()
    presets = pm.list_presets()
    assert "openai" in presets
    assert "deepseek" in presets
    assert "ollama" in presets

def test_get_preset_info():
    pm = ProviderManager()
    info = pm.get_preset("deepseek")
    assert info["base_url"] == "https://api.deepseek.com/v1"
    assert info["default_model"] == "deepseek-chat"

def test_build_client_config():
    pm = ProviderManager()
    cfg = pm.build_config(provider="deepseek", api_key="sk-test", model=None)
    assert cfg["api_key"] == "sk-test"
    assert cfg["base_url"] == "https://api.deepseek.com/v1"
    assert cfg["model"] == "deepseek-chat"  # fallback to default

def test_build_client_config_custom_model():
    pm = ProviderManager()
    cfg = pm.build_config(provider="deepseek", api_key="sk-test", model="deepseek-reasoner")
    assert cfg["model"] == "deepseek-reasoner"  # user override

def test_custom_provider():
    pm = ProviderManager()
    cfg = pm.build_config(
        provider="custom",
        api_key="sk-test",
        model="my-model",
        base_url="https://my-api.com/v1"
    )
    assert cfg["base_url"] == "https://my-api.com/v1"
    assert cfg["model"] == "my-model"
