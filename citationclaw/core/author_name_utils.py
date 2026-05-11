import re
import unicodedata


SPECIAL_CHAR_MAP = str.maketrans(
    {
        "Ł": "L",
        "ł": "l",
        "Đ": "D",
        "đ": "d",
        "Ø": "O",
        "ø": "o",
    }
)


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", (text or "").translate(SPECIAL_CHAR_MAP))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _clean_token(text: str) -> str:
    text = strip_accents(text or "")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def split_name_parts(name: str) -> tuple[str, list[str]]:
    cleaned = strip_accents(name or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(",")
    if not cleaned:
        return "", []

    if "," in cleaned:
        family, given = [part.strip() for part in cleaned.split(",", 1)]
        given_parts = [part for part in re.split(r"\s+", given) if part]
        return family, given_parts

    parts = [part for part in re.split(r"\s+", cleaned) if part]
    if len(parts) == 1:
        return parts[0], []
    return parts[-1], parts[:-1]


def format_wos_name(name: str) -> str:
    family, given_parts = split_name_parts(name)
    if not family:
        return ""
    family = re.sub(r"\s+", " ", family).strip()
    given = " ".join(given_parts).strip()
    return f"{family}, {given}".strip().strip(",")


def display_to_full_name(name: str) -> str:
    family, given_parts = split_name_parts(name)
    if not family:
        return ""
    if not given_parts:
        return family
    return " ".join([*given_parts, family]).strip()


def name_keys(name: str) -> set[str]:
    full_name = display_to_full_name(name)
    normalized_full = _clean_token(full_name)
    if not normalized_full:
        return set()

    parts = normalized_full.split()
    family = parts[-1]
    given = parts[:-1]

    keys = {
        normalized_full,
        family,
        _clean_token(format_wos_name(name)),
    }

    if given:
        keys.add(f"{given[0]} {family}")
        keys.add(f"{family} {given[0]}")
        keys.add(f"{given[0][0]} {family}")
        keys.add(f"{family} {given[0][0]}")
        keys.add(f"{family} {' '.join(given)}")
        if len(given) > 1:
            initials = " ".join(part[0] for part in given if part)
            if initials:
                keys.add(f"{initials} {family}")
                keys.add(f"{family} {initials}")

    return {key for key in keys if key}


# ---------------------------------------------------------------------------
# Enhanced matching (handles WOS abbreviated initials, inverted format, etc.)
# ---------------------------------------------------------------------------

def _normalize_allcaps(name: str) -> str:
    """'FU, DARWIN Y' → 'Fu, Darwin Y'. Only triggers when entire name is uppercase."""
    stripped = re.sub(r"[,.\s]", "", name)
    if stripped.isalpha() and stripped.isupper() and len(stripped) > 2:
        return name.title()
    return name


def _is_initials_token(s: str) -> bool:
    """Return True if s looks like initials: 1–4 uppercase-only alpha chars (e.g. 'K', 'KM', 'CA')."""
    s = re.sub(r"[\s.]+", "", s)
    return bool(s) and s.isalpha() and s.upper() == s and 1 <= len(s) <= 4


def _expand_initials(token: str) -> list[str]:
    """Split a given-name token into a list of single uppercase initials.

    'KM'       → ['K', 'M']     (WOS concatenated syllable initials for Chinese names)
    'K M'      → ['K', 'M']
    'K.'       → ['K']
    'Kaiming'  → ['K']          (full name → just first char)
    'Christopher' → ['C']
    """
    token = token.strip().rstrip(".")
    parts = [p.rstrip(".") for p in re.split(r"[\s.]+", token) if p.rstrip(".")]
    if not parts:
        return []
    if len(parts) > 1:
        return [p[0].upper() for p in parts if p]
    token = parts[0]
    # Concatenated uppercase initials like "KM", "XY", "CA"
    if token.isupper() and token.isalpha() and 2 <= len(token) <= 4:
        return list(token)
    return [token[0].upper()]


def _parse_for_match(name: str) -> tuple[str, list[str]]:
    """Parse any name format → (family_normalized, [given_initials])."""
    name = _normalize_allcaps(name.strip())
    family, given_parts = split_name_parts(name)

    if not family:
        return "", []

    given_str = " ".join(given_parts)
    if _is_initials_token(family) and given_str and len(given_str) > 3:
        family, given_parts = given_str, [family]

    family_norm = _clean_token(strip_accents(family))

    initials: list[str] = []
    for part in given_parts:
        initials.extend(_expand_initials(part))

    return family_norm, initials


def _parse_first_given(name: str) -> tuple[str, str]:
    """Parse any name format → (family_norm, first_given_norm).

    Preserves the full first given-name token (not reduced to initial) so that
    names_match can distinguish 'Christopher' from 'Carol' even though both start with C.

    'He, Kaiming'     → ('he', 'kaiming')
    'He, KM'          → ('he', 'km')         ← len<=2 → treated as initials downstream
    'Eger, T'         → ('eger', 't')         ← len=1  → initials
    'H, Melchinger'   → ('melchinger', 'h')   ← inverted
    'FU, DARWIN Y'    → ('fu', 'darwin')
    'Manning, Christopher D.' → ('manning', 'christopher')
    """
    name = _normalize_allcaps(name.strip())
    family, given_parts = split_name_parts(name)

    if not family:
        return "", ""

    given_str = " ".join(given_parts)
    if _is_initials_token(family) and given_str and len(given_str) > 3:
        family, given_parts = given_str, [family]

    family_norm = _clean_token(strip_accents(family))
    first_given = _clean_token(strip_accents(given_parts[0])) if given_parts else ""
    return family_norm, first_given


def names_match(name_a: str, name_b: str) -> bool:
    """Return True if two name strings likely refer to the same person.

    Matching rules, applied in order:

    1. Exact match after normalization.
    2. Family name must be identical.
    3. If either side has no given-name info → family match is sufficient.
    4. If either first given token is 'initials' (len ≤ 2, e.g. 'k', 'km', 't'):
       → first character must match.
       'He, KM' matches 'He, Kaiming'  (k == k)
       'Eger, T' matches 'Eger, Thomas' (t == t)
    5. Both sides have full given names (len ≥ 3):
       → first 3 characters must match.
       'Manning, Christopher' does NOT match 'Manning, Carol'  (chr ≠ car)
       'He, Kaiming' matches 'He, Kai'  (kai == kai, prefix of length 3)
       'Li, Wei' does NOT match 'Li, Wenbo'  (wei ≠ wen)

    Rule 5 prevents two distinct people with the same surname and same first
    initial from being incorrectly merged.
    """
    if not name_a or not name_b:
        return False

    # Rule 1
    if _clean_token(strip_accents(name_a)) == _clean_token(strip_accents(name_b)):
        return True

    fam_a, given_a = _parse_first_given(name_a)
    fam_b, given_b = _parse_first_given(name_b)

    # Rule 2
    if not fam_a or not fam_b or fam_a != fam_b:
        return False

    # Rule 3
    if not given_a or not given_b:
        return True

    # Rules 4 & 5: initials = len ≤ 2 after clean_token
    is_init_a = len(given_a) <= 2
    is_init_b = len(given_b) <= 2

    if is_init_a or is_init_b:
        # Rule 4: at least one abbreviated → first character must match
        return given_a[0] == given_b[0]

    # Rule 5: both full names → 3-char prefix must match
    prefix = min(len(given_a), len(given_b), 3)
    return given_a[:prefix] == given_b[:prefix]


def to_natural_name(name: str) -> str:
    """Convert any name format to natural 'First Last' (no comma).

    'He, Kaiming'    → 'Kaiming He'
    'He, KM'         → 'KM He'
    'Manning, Christopher D.' → 'Christopher D. Manning'
    'H, Melchinger'  → 'H Melchinger'   (inverted detected: H is initial, Melchinger is surname)
    'FU, DARWIN Y'   → 'Darwin Y Fu'    (all-caps normalized)
    'Kaiming He'     → 'Kaiming He'     (already natural, no change)
    """
    name = _normalize_allcaps(name.strip())
    family, given_parts = split_name_parts(name)

    if not family:
        return name

    # Inverted detection
    given_str = " ".join(given_parts)
    if _is_initials_token(family) and given_str and len(given_str) > 3:
        family, given_parts = given_str, [family]

    if not given_parts:
        return family

    given = " ".join(given_parts)
    return f"{given} {family}"
