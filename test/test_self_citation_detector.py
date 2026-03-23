import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from citationclaw.core.self_citation import SelfCitationDetector


def test_exact_match():
    detector = SelfCitationDetector()
    target = [{"name": "Alice Smith", "affiliation": "MIT"}]
    citing = [{"name": "Alice Smith", "affiliation": "MIT"}, {"name": "Bob Jones", "affiliation": "Stanford"}]
    result = detector.check(target, citing)
    assert result["is_self_citation"] is True
    assert result["method"] == "exact"


def test_no_match():
    detector = SelfCitationDetector()
    target = [{"name": "Alice Smith", "affiliation": "MIT"}]
    citing = [{"name": "Bob Jones", "affiliation": "Stanford"}]
    result = detector.check(target, citing)
    assert result["is_self_citation"] is False


def test_fuzzy_match_surname_affiliation():
    detector = SelfCitationDetector()
    target = [{"name": "Xiao-Ming Wang", "affiliation": "Tsinghua University"}]
    citing = [{"name": "X. Wang", "affiliation": "Tsinghua University"}]
    result = detector.check(target, citing)
    assert result["is_self_citation"] is True
    assert result["method"] == "fuzzy"


def test_chinese_name():
    detector = SelfCitationDetector()
    target = [{"name": "王晓明", "affiliation": "清华大学"}]
    citing = [{"name": "王小红", "affiliation": "清华大学"}]
    # Same surname 王 + same affiliation, but different person
    # This is a limitation - fuzzy match may over-match for common Chinese surnames
    result = detector.check(target, citing)
    # Both have surname 王 and same affiliation - will match as fuzzy
    assert result["is_self_citation"] is True  # known limitation


def test_different_surname_same_affiliation():
    detector = SelfCitationDetector()
    target = [{"name": "Alice Smith", "affiliation": "MIT"}]
    citing = [{"name": "Bob Jones", "affiliation": "MIT"}]
    result = detector.check(target, citing)
    assert result["is_self_citation"] is False


def test_empty_lists():
    detector = SelfCitationDetector()
    result = detector.check([], [])
    assert result["is_self_citation"] is False
