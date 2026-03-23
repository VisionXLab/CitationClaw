import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from citationclaw.config.prompt_loader import PromptLoader

def test_load_existing_prompt():
    loader = PromptLoader()
    text = loader.get("self_citation")
    assert "{target_authors}" in text
    assert "{citing_authors}" in text

def test_load_with_variables():
    loader = PromptLoader()
    text = loader.render("self_citation", target_authors="Alice", citing_authors="Bob")
    assert "Alice" in text
    assert "Bob" in text
    assert "{target_authors}" not in text

def test_load_nonexistent_raises():
    loader = PromptLoader()
    with pytest.raises(FileNotFoundError):
        loader.get("nonexistent_prompt")

def test_custom_prompt_dir(tmp_path):
    (tmp_path / "test_prompt.txt").write_text("Hello {name}")
    loader = PromptLoader(prompt_dir=tmp_path)
    assert loader.render("test_prompt", name="World") == "Hello World"
