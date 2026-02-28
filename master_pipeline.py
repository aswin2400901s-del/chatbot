#!/usr/bin/env python
# coding: utf-8

import re

# -----------------------------------------------------------------------
# FIX: Use EXPLICIT imports instead of wildcard "from X import *"
#      Wildcard imports caused infer_city and extract_locality to be
#      silently overwritten with the wrong version, causing TypeErrors.
# -----------------------------------------------------------------------

from NER_training import (
    normalize_text,
    locality_list_norm,
    locality_map_norm,
    locality_to_city,
    locality_to_city_id,
    property_type_map,
    amenities_map,
)

from regex_extraction import (
    extract_price,
    extract_area,
    extract_bathroom,
)

from fuzzy_match import (
    extract_locality,       # multi-locality aware version (4 args)
    infer_city,             # multi-locality aware version (3 args)
    extract_city_direct,    # fallback: match city name typed directly (e.g. "banglore")
    extract_property_type,
    extract_amenities,
)

from NER_training import city_map as _city_map   # needed by extract_city_direct

# Sub-type pipelines
from rental_pipeline     import rental_search
from commercial_pipeline import commercial_search
from pg_pipeline         import pg_search

# Suggestions engine
from suggestions import (
    buy_suggestions,
    rental_suggestions,
    commercial_suggestions,
    pg_suggestions,
)


# ===============================
# SEARCH TYPE DETECTOR
# ===============================

_RENTAL_KEYWORDS = {
    "rent", "rental", "for rent", "for lease", "lease", "renting",
    "monthly rent", "per month", "tenant", "tenants",
}

_COMMERCIAL_KEYWORDS = {
    "office", "office space", "commercial", "shop", "showroom",
    "warehouse", "godown", "coworking", "co-working", "co working",
    "retail space", "business space", "industrial", "factory",
    "commercial plot", "shed",
}

_PG_KEYWORDS = {
    "pg", "p.g", "p.g.", "paying guest", "hostel", "dormitory",
    "co-living", "coliving", "co living", "shared accommodation",
    "boys pg", "girls pg", "boys hostel", "girls hostel",
}

_BUY_KEYWORDS = {
    "buy", "purchase", "buying", "sale", "for sale", "sell",
    "own", "ownership", "property for sale", "invest",
}


def detect_search_type(text: str) -> str:
    """
    Infer the search category from the query text.

    Priority order:
      1. PG / Hostel
      2. Commercial
      3. Rental
      4. Buy (default)

    Returns one of: "pg", "commercial", "rental", "buy"
    """
    tl = text.lower()

    for kw in _PG_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", tl):
            return "pg"

    for kw in _COMMERCIAL_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", tl):
            return "commercial"

    for kw in _RENTAL_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", tl):
            return "rental"

    return "buy"


# ===============================
# NORMALIZE IDs TO INT
# ===============================

def normalize_ids(result):
    for key in list(result.keys()):
        value = result[key]

        if key.lower().endswith("id") and value is not None and not isinstance(value, list):
            try:
                result[key] = int(value)
            except (TypeError, ValueError):
                result[key] = None

        if isinstance(value, list) and key.lower().endswith("id"):
            result[key] = [int(v) for v in value if v is not None]

    return result


# ===============================
# BUY PIPELINE  (original logic, unchanged)
# ===============================

def buy_search(text: str):
    """
    Parses a natural language property BUY/SALE query and returns a
    structured dict with all extracted fields.
    """
    result = {}
    text_lower = text.lower()

    # ---------- BHK ----------
    # Capture digit + suffix to correctly distinguish "1 RK" from "1 BHK"
    bhk_raw = re.findall(
        r'(\d+)\s*(bhk|b[\s\.]*h[\s\.]*k|rk|r[\s\.]*k)',
        text_lower, re.IGNORECASE)

    if not bhk_raw and re.search(r'\brk\b', text_lower):
        bhk_raw = [("1", "rk")]

    # --- BHK ID lookup table from CSV (normalized: strip spaces, uppercase) ---
    # CSV stores "1RK ", "1BHK ", "2BHK " — we normalize to "1RK","1BHK","2BHK"
    import pandas as _pd
    _bhk_df = _pd.read_csv(
        __import__('os').environ.get("HOMES247_CSV",
        __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),
        "buy_searchproperty_new 2(Sheet1).csv")),
        usecols=["bhk_numbers","bhkId"]).dropna().drop_duplicates()
    _BUY_BHK_ID = {
        str(r["bhk_numbers"]).strip().upper(): int(r["bhkId"])
        for _, r in _bhk_df.iterrows()
    }
    # _BUY_BHK_ID = {"1RK":9, "1BHK":1, "2BHK":2, "3BHK":3, "4BHK":4, "5BHK":5}

    def _buy_bhk_label(digit, suffix):
        """Return display label e.g. '1 RK', '2 BHK'"""
        n = int(digit)
        is_rk = re.match(r'r[\s\.]*k', suffix.strip(), re.IGNORECASE) is not None
        return f"{n} {'RK' if is_rk else 'BHK'}"

    def _buy_bhk_id(label):
        """Lookup bhkId from CSV map. '1 RK' -> 9, '2 BHK' -> 2"""
        key = str(label).replace(" ", "").upper()   # "1 RK" -> "1RK"
        return _BUY_BHK_ID.get(key)

    if len(bhk_raw) == 0:
        bhk_list  = None
        bhk_id    = None
        bhk_for_bathroom = None
    elif len(bhk_raw) == 1:
        bhk_list  = _buy_bhk_label(*bhk_raw[0])
        bhk_id    = _buy_bhk_id(bhk_list)
        bhk_for_bathroom = bhk_list
    else:
        bhk_list  = [_buy_bhk_label(d, s) for d, s in bhk_raw]
        bhk_id    = [_buy_bhk_id(b) for b in bhk_list]
        bhk_for_bathroom = bhk_list

    result["bhk_numbers"] = bhk_list
    result["bhkId"]       = bhk_id    # integer id from CSV (9 for 1RK, 1 for 1BHK …)

    # ---------- PRICE ----------
    result.update(extract_price(text))

    # ---------- AREA ----------
    result.update(extract_area(text))

    # ---------- LOCALITY ----------
    loc_data = extract_locality(text, locality_list_norm, locality_map_norm)
    result.update(loc_data)

    # ---------- CITY (inferred from locality) ----------
    result.update(infer_city(loc_data.get("locality"), locality_to_city, locality_to_city_id))

    # ---------- CITY FALLBACK (direct city name in query) ----------
    if result.get("city") is None:
        city_fallback = extract_city_direct(text, _city_map)
        if city_fallback.get("city"):
            result.update(city_fallback)

    # ---------- PROPERTY TYPE ----------
    result.update(extract_property_type(text, property_type_map))

    # ---------- BHK PAIRING WITH PROPERTY TYPES ----------
    prop_name = result.get("propertyType_name")
    if isinstance(prop_name, list) and not isinstance(result.get("bhk_numbers"), list):
        bhk_val = result.get("bhk_numbers")
        if bhk_val is not None:
            replicated = [bhk_val] * len(prop_name)
            result["bhk_numbers"] = replicated
            # replicate the id too (already resolved above)
            id_val = result.get("bhkId")
            result["bhkId"] = [id_val] * len(prop_name)
            bhk_for_bathroom = replicated

    # ---------- BATHROOM ----------
    result.update(extract_bathroom(text, bhk_for_bathroom))

    # ---------- AMENITIES ----------
    result.update(extract_amenities(text, amenities_map))

    # ---------- NORMALIZE ALL IDs TO INT ----------
    normalize_ids(result)

    # ---------- SMART QUERY ----------
    parts = []

    def fmt_price(v):
        if v is None:
            return None
        if v >= 10_000_000:
            return f"Rs.{v/10_000_000:.2g}Cr"
        if v >= 100_000:
            return f"Rs.{v/100_000:.4g}L"
        return f"Rs.{v:,}"

    bhk_val = result.get("bhk_numbers")
    if bhk_val is not None:
        def _bhk_display(b):
            """Format single BHK label for smart_query display."""
            s = str(b).strip()
            import re as _re
            if _re.search(r'\bRK\b', s, _re.IGNORECASE):
                num = _re.match(r'(\d+)', s)
                return f"{num.group(1)}RK" if num else "1RK"
            # strip " BHK" suffix if present, then add it back cleanly
            cleaned = s.replace(" BHK","").replace(" RK","").strip()
            return f"{cleaned}BHK"
        if isinstance(bhk_val, list):
            unique_bhk = list(dict.fromkeys(bhk_val))
            parts.append(" & ".join(_bhk_display(b) for b in unique_bhk))
        else:
            parts.append(_bhk_display(bhk_val))

    prop = result.get("propertyType_name")
    if prop:
        if isinstance(prop, list):
            parts.append(" & ".join(prop))
        else:
            parts.append(prop)

    loc = result.get("locality")
    if loc:
        if isinstance(loc, list):
            parts.append(" & ".join(loc))
        else:
            parts.append(loc)
    elif result.get("city"):
        city_val = result["city"]
        if isinstance(city_val, list):
            unique_cities = list(dict.fromkeys(city_val))
            parts.append(" & ".join(unique_cities))
        else:
            parts.append(city_val)

    min_p = result.get("minPrice")
    max_p = result.get("maxPrice")
    if min_p is not None and max_p is not None:
        if min_p == 0:
            parts.append(f"under {fmt_price(max_p)}")
        else:
            parts.append(f"{fmt_price(min_p)} - {fmt_price(max_p)}")
    elif min_p:
        parts.append(f"above {fmt_price(min_p)}")
    elif max_p:
        parts.append(f"under {fmt_price(max_p)}")

    min_a = result.get("minArea")
    max_a = result.get("maxArea")
    if min_a is not None and max_a is not None:
        if min_a == max_a:
            parts.append(f"{min_a:,} sqft")
        else:
            parts.append(f"{min_a:,}-{max_a:,} sqft")
    elif min_a:
        parts.append(f"above {min_a:,} sqft")
    elif max_a:
        parts.append(f"under {max_a:,} sqft")

    amenities = result.get("amenities_name", [])
    if amenities:
        parts.append("with " + ", ".join(amenities))

    result["smart_query"] = " ".join(parts) if parts else text
    result["search_type"] = "buy"

    # ---------- SUGGESTIONS ----------
    result["suggestions"] = buy_suggestions(result, text)

    return result


# ===============================
# UNIFIED ENTRY POINT
# ===============================

def smart_search(text: str, search_type: str = None):
    """
    Auto-detects OR accepts an explicit search_type, then routes to
    the correct sub-pipeline.

    Args:
        text        : natural language query
        search_type : "buy" | "rental" | "commercial" | "pg"
                      If None, auto-detected from text.

    Returns:
        dict with all extracted fields + "search_type" key.
    """
    if search_type is None:
        search_type = detect_search_type(text)

    if search_type == "rental":
        result = rental_search(text)
        result["suggestions"] = rental_suggestions(result, text)
        return result
    elif search_type == "commercial":
        result = commercial_search(text)
        result["suggestions"] = commercial_suggestions(result, text)
        return result
    elif search_type == "pg":
        result = pg_search(text)
        result["suggestions"] = pg_suggestions(result, text)
        return result
    else:
        return buy_search(text)


# ===============================
# QUICK TEST
# ===============================

if __name__ == "__main__":
    import json

    tests = [
        # BUY
        ("buy",        "2bhk in whitefield under 50l"),
        ("buy",        "2bhk in banglore under 50l"),
        # RENTAL
        ("rental",     "2bhk furnished apartment for family under 25k near hospital"),
        ("rental",     "3bhk villa unfurnished for bachelor with gym"),
        # COMMERCIAL
        ("commercial", "office space under 1 crore with ac and conference hall"),
        ("commercial", "shop 2000 sqft ready to move east facing for restaurant"),
        # PG
        ("pg",         "boys pg for working professionals private room with wifi under 8k"),
        ("pg",         "girls hostel two sharing veg food included laundry"),
        # AUTO-DETECT
        (None,         "3bhk flat for rent under 30k semi furnished"),
        (None,         "pg near whitefield girls working professionals"),
        (None,         "office space for startup 3000 sqft"),
        (None,         "4bhk villa in koramangala 2 crore"),
    ]

    for stype, query in tests:
        print(f"\n[type={stype or 'auto'}] Query: {query}")
        print(json.dumps(smart_search(query, stype), indent=2))