#!/usr/bin/env python
# coding: utf-8

"""
fuzzy_match.py — 3-Layer Locality Matching Pipeline
=====================================================

Layer 1 — Trigram TF-IDF (sklearn, char n-grams 2–3)
    Handles: spaced names ("white field"), partial names, character swaps
    Speed: fast after index is built at startup

Layer 2 — Soundex Phonetic (pure Python, no extra library needed)
    Handles: pronunciation-based typos ("koramangla", "hebal", "indranagar")
    Speed: very fast

Layer 3 — Levenshtein Edit Distance (difflib.SequenceMatcher, stdlib)
    Handles: any remaining character-level typos not caught above
    Speed: fast

Each layer returns a (locality_norm, score) tuple or None.
The pipeline accepts the FIRST layer that finds a confident match.
If multiple layers match, the highest scoring result wins.
"""

import re
import difflib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from NER_training import normalize_text, amenities_map


# ===============================================================
# SOUNDEX — Pure Python (no jellyfish needed)
# Maps a word to a 4-character phonetic code.
# Words that sound alike get the same code.
# ===============================================================

def soundex(word: str) -> str:
    """
    Returns a 4-char Soundex code for a word.
    Example:
      soundex("koramangla") == soundex("koramangala") == "K655"
      soundex("whitfield")  == soundex("whitefield")  == "W314"
    """
    if not word:
        return "0000"

    word = word.upper()
    code = word[0]

    digits_map = {
        'B': '1', 'F': '1', 'P': '1', 'V': '1',
        'C': '2', 'G': '2', 'J': '2', 'K': '2',
        'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
        'D': '3', 'T': '3',
        'L': '4',
        'M': '5', 'N': '5',
        'R': '6'
        # A, E, I, O, U, H, W, Y → ignored (treated as 0)
    }

    prev = digits_map.get(word[0], '0')
    for char in word[1:]:
        digit = digits_map.get(char, '0')
        if digit != '0' and digit != prev:
            code += digit
        prev = digit

    return (code + '000')[:4]


def soundex_phrase(phrase: str) -> str:
    """
    Soundex for multi-word locality names — encodes each word and joins.
    Example: "hsr layout" → "H260-L300"
    """
    return "-".join(soundex(w) for w in phrase.split() if w)


# ===============================================================
# TRIGRAM INDEX — Built once at import time from locality list
# ===============================================================

class TrigramIndex:
    """
    Builds a TF-IDF character n-gram (2–3) index over all locality names.
    Allows fast cosine-similarity lookup for any query chunk.

    Best at:
      "white field"     → "whitefield"     (spaced variant)
      "hsr layot"       → "hsr layout"     (typo in multi-word)
      "electronik city" → "electronic city" (phonetic swap)
    """

    def __init__(self, locality_list_norm: list):
        self.localities = locality_list_norm
        # char_wb wraps words with boundaries — better for short locality strings
        self.vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(2, 3),
            min_df=1
        )
        if locality_list_norm:
            self.matrix = self.vectorizer.fit_transform(locality_list_norm)
        else:
            self.matrix = None

    def query(self, chunk: str, threshold: float = 0.62):
        """
        Returns (best_locality_norm, cosine_score) or None if below threshold.
        """
        if self.matrix is None:
            return None
        try:
            vec = self.vectorizer.transform([chunk])
        except Exception:
            return None

        sims = cosine_similarity(vec, self.matrix)[0]
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score >= threshold:
            return (self.localities[best_idx], best_score)
        return None


# ===============================================================
# SOUNDEX INDEX — Built once at import time
# Maps soundex code → list of locality_norm strings
# ===============================================================

class SoundexIndex:
    """
    Pre-computes soundex codes for all localities.
    Lookup: given a chunk's soundex code, find candidate localities,
    then pick the best by Levenshtein similarity.

    Best at:
      "koramangla"  → "koramangala"  (dropped vowel)
      "hebal"       → "hebbal"       (dropped double letter)
      "indranagar"  → "indiranagar"  (dropped vowel)
      "hebbal"      → "hebbal"       (exact → score 1.0)
    """

    def __init__(self, locality_list_norm: list):
        self.localities = locality_list_norm
        # soundex_code → [locality_norm, ...]
        self.index: dict = {}
        for loc in locality_list_norm:
            code = soundex_phrase(loc)
            self.index.setdefault(code, []).append(loc)

    def query(self, chunk: str, lev_threshold: float = 0.75):
        """
        Returns (best_locality_norm, levenshtein_score) or None.
        """
        code = soundex_phrase(chunk)
        candidates = self.index.get(code, [])
        if not candidates:
            return None

        best_loc = None
        best_score = 0.0
        for loc in candidates:
            score = difflib.SequenceMatcher(None, chunk, loc).ratio()
            if score > best_score:
                best_score = score
                best_loc = loc

        if best_loc and best_score >= lev_threshold:
            return (best_loc, best_score)
        return None


# ===============================================================
# LEVENSHTEIN LAYER — difflib.SequenceMatcher (Python stdlib)
# Final fallback for typos not caught by trigram or soundex
# ===============================================================

def levenshtein_match(chunk: str, locality_list_norm: list, threshold: float = 0.80):
    """
    Finds the best edit-distance match for a chunk across all localities.
    Returns (best_locality_norm, score) or None if below threshold.

    Uses difflib.get_close_matches for fast pre-filtering,
    then re-ranks top 5 with full SequenceMatcher ratio.

    Best at:
      "jp nagr"     → "jp nagar"    (1 char missing)
      "banergata"   → "bannerghatta road"  (multiple char edits)
    """
    close = difflib.get_close_matches(chunk, locality_list_norm, n=5, cutoff=threshold)
    if not close:
        return None

    best_loc = None
    best_score = 0.0
    for loc in close:
        score = difflib.SequenceMatcher(None, chunk, loc).ratio()
        if score > best_score:
            best_score = score
            best_loc = loc

    if best_loc:
        return (best_loc, best_score)
    return None


# ===============================================================
# 3-LAYER MATCHER — Runs all layers, picks best result
# ===============================================================

def match_chunk(
    chunk: str,
    locality_list_norm: list,
    trigram_index: TrigramIndex,
    soundex_index: SoundexIndex,
    trigram_threshold: float = 0.62,
    soundex_lev_threshold: float = 0.75,
    levenshtein_threshold: float = 0.80,
):
    """
    Runs the 3-layer pipeline for a single text chunk.

    Order:
      1. Trigram TF-IDF  → if score >= 0.85, return immediately (high confidence)
      2. Soundex+Lev     → catches pronunciation typos trigram may score < 0.85 on
      3. Levenshtein     → final safety net for simple char typos

    Returns: (locality_norm, score, layer_name) or None
    """
    results = []

    # ---- Layer 1: Trigram TF-IDF ----
    tri = trigram_index.query(chunk, threshold=trigram_threshold)
    if tri:
        loc, score = tri
        results.append((loc, score, "trigram"))
        # High confidence — no need to check other layers
        if score >= 0.85:
            return results[0]

    # ---- Layer 2: Soundex + Levenshtein ----
    snd = soundex_index.query(chunk, lev_threshold=soundex_lev_threshold)
    if snd:
        loc, score = snd
        results.append((loc, score, "soundex"))

    # ---- Layer 3: Levenshtein only ----
    lev = levenshtein_match(chunk, locality_list_norm, threshold=levenshtein_threshold)
    if lev:
        loc, score = lev
        results.append((loc, score, "levenshtein"))

    if not results:
        return None

    # Pick the highest-scoring result across all layers
    return max(results, key=lambda x: x[1])


# ===============================================================
# NON-LOCALITY BLOCKLIST
# These words are never valid locality names.
# Prevents amenity/query words from getting matched as localities.
# ===============================================================

NON_LOCALITY_WORDS = {
    # amenities
    "garden", "area", "room", "pool", "court", "gym", "yoga",
    "swimming", "badminton", "tennis", "park", "club", "hall",
    "lift", "security", "parking", "terrace", "balcony", "play",
    "children", "power", "backup", "water", "solar", "cctv",
    "intercom", "wifi", "gated", "community", "society",
    # query words
    "bhk", "budget", "need", "want", "looking", "with", "and",
    "or", "in", "at", "near", "for", "the", "a", "an", "of",
    "under", "below", "above", "crore", "lakh", "lakhs",
    "flat", "apartment", "villa", "plot", "house", "floor",
    "sqft", "sft", "sqt", "carpet", "super", "built",
    "room", "bath", "bathroom", "toilet", "kitchen",
}


# ===============================================================
# MODULE-LEVEL INDEX INSTANCES (built once, reused every call)
# ===============================================================

_trigram_index: TrigramIndex = None
_soundex_index: SoundexIndex = None


def _ensure_indexes(locality_list_norm: list):
    """Lazily builds trigram and soundex indexes on first call."""
    global _trigram_index, _soundex_index
    if _trigram_index is None or _trigram_index.localities != locality_list_norm:
        _trigram_index = TrigramIndex(locality_list_norm)
    if _soundex_index is None or _soundex_index.localities != locality_list_norm:
        _soundex_index = SoundexIndex(locality_list_norm)


# ===============================================================
# LOCALITY EXTRACTION — Main entry point
# ===============================================================

def extract_locality(text, locality_list_norm, locality_map_norm, threshold=None):
    """
    Finds ALL localities mentioned in a query using the 3-layer pipeline.

    Steps:
      1. Normalize query text
      2. Generate 1–3 word chunks + space-collapsed variants
         ("white field" → also try "whitefield")
      3. Skip chunks where all words are in NON_LOCALITY_WORDS blocklist
      4. Run 3-layer matcher on each chunk
      5. Apply length-ratio guard to reject short chunks matching long names
      6. Deduplicate and return

    Examples:
      "white field"     → Whitefield   (trigram: spaces collapsed)
      "koramangla"      → Koramangala  (soundex: dropped vowel)
      "hebal"           → Hebbal       (soundex: dropped double letter)
      "indranagar"      → Indiranagar  (levenshtein: missing vowel)
      "hsr layot"       → Hsr Layout   (trigram: char typo)
    """
    if not text:
        return {"locality": None, "localityId": None}

    _ensure_indexes(locality_list_norm)

    query = normalize_text(text)
    words = query.split()

    # Build chunk list: normal + space-collapsed for multi-word chunks
    chunks = []
    seen_chunks = set()

    for i in range(len(words)):
        for size in [1, 2, 3]:
            if i + size > len(words):
                break
            chunk_words = words[i:i + size]

            # Skip if ALL words in chunk are non-locality words
            if all(w in NON_LOCALITY_WORDS for w in chunk_words):
                continue

            # Normal chunk e.g. "white field"
            normal = " ".join(chunk_words)
            if normal not in seen_chunks:
                seen_chunks.add(normal)
                chunks.append(normal)

            # Space-collapsed e.g. "whitefield" — handles user typing with spaces
            if size > 1:
                collapsed = "".join(chunk_words)
                if collapsed not in seen_chunks:
                    seen_chunks.add(collapsed)
                    chunks.append(collapsed)

    found_localities = []
    found_ids = []
    seen_matched = set()

    for chunk in chunks:
        result = match_chunk(
            chunk,
            locality_list_norm,
            _trigram_index,
            _soundex_index,
        )

        if result is None:
            continue

        locality_norm, score, layer = result

        # Length ratio guard:
        # A short chunk (1 word) should not match a long locality name (3 words).
        # Require chunk word count >= 60% of matched locality word count.
        chunk_word_count = len(chunk.split())
        locality_word_count = len(locality_norm.split())
        if chunk_word_count / locality_word_count < 0.6:
            continue

        if locality_norm in seen_matched:
            continue

        seen_matched.add(locality_norm)
        found_localities.append(locality_norm.title())
        found_ids.append(int(locality_map_norm[locality_norm]))

    if not found_localities:
        return {"locality": None, "localityId": None}
    elif len(found_localities) == 1:
        return {
            "locality": found_localities[0],
            "localityId": found_ids[0]
        }
    else:
        return {
            "locality": found_localities,
            "localityId": found_ids
        }


# ===============================================================
# CITY INFERENCE FROM LOCALITY
# ===============================================================

def infer_city(locality, locality_to_city, locality_to_city_id):
    """
    Infers city from locality.
    Handles both single locality (string) and multiple localities (list).
    """
    if not locality:
        return {"city": None, "cityId": None}

    if isinstance(locality, list):
        cities = []
        city_ids = []
        for loc in locality:
            loc_key = str(loc).title()
            cities.append(locality_to_city.get(loc_key))
            city_ids.append(locality_to_city_id.get(loc_key))
        return {"city": cities, "cityId": city_ids}

    loc_key = str(locality).title()
    return {
        "city": locality_to_city.get(loc_key),
        "cityId": locality_to_city_id.get(loc_key)
    }


# ===============================================================
# DIRECT CITY MATCHING
# Handles queries like "2bhk in bangalore" / "banglore" / "bengaluru"
# where the user types the city name instead of a specific locality.
# ===============================================================

# Canonical city name synonyms — keys are normalized variants
CITY_SYNONYMS = {
    "bangalore":  "Bangalore",
    "bangaluru":  "Bangalore",
    "banglore":   "Bangalore",
    "bengaluru":  "Bangalore",
    "bengalore":  "Bangalore",
    "bengalor":   "Bangalore",
    "blr":        "Bangalore",
    "mumbai":     "Mumbai",
    "bombay":     "Mumbai",
    "delhi":      "Delhi",
    "new delhi":  "Delhi",
    "hyderabad":  "Hyderabad",
    "hyd":        "Hyderabad",
    "chennai":    "Chennai",
    "madras":     "Chennai",
    "pune":       "Pune",
    "kolkata":    "Kolkata",
    "calcutta":   "Kolkata",
}


def extract_city_direct(text: str, city_map: dict):
    """
    Directly matches a city name (or common misspelling/synonym) from the query.
    Returns {"city": name, "cityId": id} or {"city": None, "cityId": None}.

    Used as a FALLBACK when no locality is found — catches queries like
    "2bhk in banglore under 50l" where "banglore" is a city, not a locality.
    """
    text_norm = normalize_text(text)
    words = text_norm.split()

    # Try 1-word and 2-word chunks against CITY_SYNONYMS
    for size in [2, 1]:
        for i in range(len(words) - size + 1):
            chunk = " ".join(words[i:i + size])
            canonical = CITY_SYNONYMS.get(chunk)
            if canonical:
                city_id = city_map.get(canonical)
                return {
                    "city": canonical,
                    "cityId": int(city_id) if city_id is not None else None
                }

    # Fuzzy fallback: try levenshtein against all city names in city_map
    all_cities = list(city_map.keys())
    for chunk_size in [2, 1]:
        for i in range(len(words) - chunk_size + 1):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk in NON_LOCALITY_WORDS:
                continue
            close = difflib.get_close_matches(chunk, [c.lower() for c in all_cities], n=1, cutoff=0.82)
            if close:
                # Find the original-case city name
                matched_lower = close[0]
                for city_name in all_cities:
                    if city_name.lower() == matched_lower:
                        return {
                            "city": city_name,
                            "cityId": int(city_map[city_name])
                        }

    return {"city": None, "cityId": None}


# ===============================================================
# PROPERTY TYPE EXTRACTION
# Collects ALL matched property types ("villa AND apartment")
# ===============================================================

def extract_property_type(text, property_type_map):
    text_lower = text.lower()

    property_synonyms = {
        "flat": "Apartment",
        "flate": "Apartment",
        "apartment": "Apartment",
        "house":"Independent House",
        "apt": "Apartment",
        "villa": "Villa",
        "vill": "Villa",
        "vila": "Villa",
        "plot": "Plot",
        "land": "Plot"
    }

    found_names = []
    found_ids = []
    seen_canonical = set()

    for keyword, canonical in property_synonyms.items():
        if re.search(rf"\b{re.escape(keyword)}\b", text_lower) and canonical in property_type_map:
            if canonical not in seen_canonical:
                seen_canonical.add(canonical)
                found_names.append(canonical)
                found_ids.append(int(property_type_map[canonical]))

    if not found_names:
        return {"propertyType_name": None, "propertyType_id": None}
    elif len(found_names) == 1:
        return {"propertyType_name": found_names[0], "propertyType_id": found_ids[0]}
    else:
        return {"propertyType_name": found_names, "propertyType_id": found_ids}


# ===============================================================
# AMENITIES EXTRACTION
# ===============================================================

def extract_amenities(text, amenities_map, threshold=80):
    """
    Matches amenities using exact word match first, fuzzy partial as fallback.
    Skips names shorter than 3 characters to avoid false positives.
    Uses rapidfuzz if available, falls back to difflib otherwise.
    """
    found = {}
    text_lower = text.lower()

    for name, aid in amenities_map.items():
        name_lower = name.lower()
        if len(name_lower) < 3:
            continue

        # Exact word match (preferred, fastest)
        if re.search(rf"\b{re.escape(name_lower)}\b", text_lower):
            found[name] = int(aid)
            continue

        # Fuzzy fallback — try rapidfuzz first, difflib if not available
        try:
            from rapidfuzz import fuzz as rfuzz
            score = rfuzz.partial_ratio(name_lower, text_lower)
            if score >= threshold:
                found[name] = int(aid)
        except ImportError:
            # difflib fallback
            ratio = difflib.SequenceMatcher(None, name_lower, text_lower).ratio() * 100
            if ratio >= threshold:
                found[name] = int(aid)

    return {
        "amenities_name": list(found.keys()),
        "amenities_id": list(found.values())
    }





# ===============================================================
# QUICK TEST (run this file directly to verify the pipeline)
# ===============================================================

if __name__ == "__main__":
    test_localities = [
        "whitefield", "koramangala", "hebbal", "indiranagar",
        "hsr layout", "jp nagar", "marathahalli", "electronic city",
        "bannerghatta road", "sarjapur road", "bellandur", "yelahanka"
    ]
    test_map = {loc: i + 1 for i, loc in enumerate(test_localities)}

    _ensure_indexes(test_localities)

    test_inputs = [
        ("white field",       "whitefield",        "trigram — spaced name"),
        ("koramangla",        "koramangala",        "soundex — dropped vowel"),
        ("hebal",             "hebbal",             "soundex — dropped double letter"),
        ("indranagar",        "indiranagar",        "levenshtein — missing vowel"),
        ("hsr layot",         "hsr layout",         "trigram — multi-word typo"),
        ("jp nagr",           "jp nagar",           "levenshtein — char missing"),
        ("electronik city",   "electronic city",    "trigram — phonetic swap"),
        ("sarjapur rd",       "sarjapur road",      "trigram — abbreviation"),
        ("bellanduru",        "bellandur",           "levenshtein — extra char"),
        ("yelahanca",         "yelahanka",           "soundex — char swap"),
    ]

    print(f"\n{'Input':<22} {'Expected':<22} {'Got':<22} {'Score':<7} {'Layer':<12} {'OK?'}")
    print("-" * 100)
    for inp, expected, desc in test_inputs:
        result = match_chunk(inp, test_localities, _trigram_index, _soundex_index)
        if result:
            loc, score, layer = result
            ok = "✓" if loc == expected else "✗"
            print(f"{inp:<22} {expected:<22} {loc:<22} {score:<7.3f} {layer:<12} {ok}  ({desc})")
        else:
            print(f"{inp:<22} {expected:<22} {'NO MATCH':<22} {'—':<7} {'—':<12} ✗  ({desc})")