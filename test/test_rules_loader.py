import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from citationclaw.config.rules_loader import RulesLoader

def test_load_scholar_tiers():
    rules = RulesLoader()
    tiers = rules.get("scholar_tiers")
    assert "tiers" in tiers
    assert any(t["name"] == "Academician" for t in tiers["tiers"])

def test_load_data_sources():
    rules = RulesLoader()
    sources = rules.get("data_sources")
    assert "metadata_sources" in sources

def test_tier_keywords():
    rules = RulesLoader()
    tiers = rules.get("scholar_tiers")
    fellow_tier = next(t for t in tiers["tiers"] if t["name"] == "Fellow")
    assert "IEEE Fellow" in str(fellow_tier["criteria"])
