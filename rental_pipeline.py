#!/usr/bin/env python
# coding: utf-8

"""
rental_pipeline.py — Natural language search parser for RENTAL properties.

Fully integrated with:
  - fuzzy_match.py  → locality extraction (handles typos, multi-locality)
  - NER_training.py → locality→city inference, city direct match
  - regex_extraction.py → area extraction (reused)

Output keys match rental.csv headers exactly:
  bhk, Bathroom, Balcony, Furnish, Tenants, Propertytype,
  Ownership, Doorface, Amenities, Facilities, Nearby, Parking, PlotType
  + locality, localityId, city, cityId, minRent, maxRent
"""

import re

# ── NER + Fuzzy imports (same as buy pipeline) ─────────────────────────────
from NER_training import (
    locality_list_norm,
    locality_map_norm,
    locality_to_city,
    locality_to_city_id,
    city_map,
)
from fuzzy_match import (
    extract_locality,
    infer_city,
    extract_city_direct,
    _ensure_indexes,
)

# Pre-build indexes at import time
_ensure_indexes(locality_list_norm)

# ═══════════════════════════════════════════════════════════════════════════
# AMENITIES ID MAP  (from rent.json) — bhkId/PropertytypeId use inline maps
# ═══════════════════════════════════════════════════════════════════════════

_AMENITIES_ID = {
    "Gym": 45, "Swimming Pool": 49, "Power Backup": 32,
    "Car Parking": 41, "Club House": 43, "Elevator": 37,
    "Garden": 28, "Wifi": 36,
}


def _to_amenities_ids(labels):
    """Convert list of amenity labels → list of IDs. Returns None if empty."""
    if not labels:
        return None
    ids = [_AMENITIES_ID[l] for l in labels if l in _AMENITIES_ID]
    return ids if ids else None


# ═══════════════════════════════════════════════════════════════════════════
# MASTER VALUE MAPS  (from rental.csv)
# ═══════════════════════════════════════════════════════════════════════════

# FIX: Use regex patterns instead of exact keywords to handle typos like
#      "semi-furished", "semifurished", "semi furnised", "unfurnish" etc.
# Order matters — check fully/semi BEFORE bare "furnished"
_FURNISH_PATTERNS = [
    (r'\bfully\s+furn\w*\b',         "Furnished"),
    (r'\bfull\s+furn\w*\b',          "Furnished"),
    (r'\bsemi[\s\-]?furi?\w*\b',     "Semi furnished"),   # semi-furished, semi furished
    (r'\bsemi[\s\-]?furn\w*\b',      "Semi furnished"),   # semi-furnished, semifurnished
    (r'\bunfurn\w*\b',               "Unfurnished"),
    (r'\bun[\s\-]furnished\b',       "Unfurnished"),
    (r'\bbare[\s\-]?shell\b',        "Unfurnished"),
    (r'\bfurnish\w*\b',              "Furnished"),         # catch-all last
]

def _extract_furnish(text_lower: str):
    for pat, label in _FURNISH_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE):
            return label
    return None

RENTAL_FURNISH_MAP = {
    "fully furnished":  "Furnished",
    "furnished":        "Furnished",
    "semi-furnished":   "Semi furnished",
    "semi furnished":   "Semi furnished",
    "semifurnished":    "Semi furnished",
    "unfurnished":      "Unfurnished",
    "un furnished":     "Unfurnished",
    "bare shell":       "Unfurnished",
}

RENTAL_TENANT_MAP = {
    "bachelor":     "Bachelor",
    "bachelors":    "Bachelor",
    "boys":         "Bachelor",
    "family":       "Family",
    "families":     "Family",
    "ladies":       "Ladies",
    "girls":        "Ladies",
    "women":        "Ladies",
    "anyone":       "Anyone",
}

RENTAL_PROPERTY_TYPE_MAP = {
    "independent house": "Independent House",
    "independent home":  "Independent House",
    "apartment":         "Apartment",
    "flat":              "Apartment",
    "flate":             "Apartment",
    "villa":             "Villa",
    "bungalow":          "Independent House",
    "house":             "Independent House",
    "plot":              "Plot",
    "land":              "Plot",
}

RENTAL_OWNERSHIP_MAP = {
    "owner":  "Owner",
    "direct": "Owner",
    "no broker": "Owner",
    "broker": "Broker",
    "agent":  "Broker",
}

RENTAL_DOOR_FACE_MAP = {
    "north": "North",
    "south": "South",
    "east":  "East",
    "west":  "West",
}

RENTAL_AMENITIES = [
    "Atm", "Auditorium", "Badminton Court", "Basket Ball Court", "CCTV",
    "Cafeteria", "Cafeteria/Food Court", "Car Parking", "Club House",
    "Cycling track", "Dance Studio", "Elevator", "Garden", "Gym",
    "Indoor Games", "Jogging Track", "Library", "Maintenance Staff",
    "Party House", "Power Backup", "Rainwater Harvesting", "Sewage Treatment",
    "Sewage treatment plant", "Study room", "Swimming Pool", "Tennis Court",
    "Water Front", "Water Supply", "Wifi",
]

RENTAL_FACILITIES = [
    "Parking", "Power Backup", "Power Supply",
    "Rainwater Harvesting", "Sewage Water Treatment",
]

RENTAL_NEARBY = [
    "Bus Stand", "Hospital", "Metro Station", "Restaurant", "Super Market",
]

# FIX: Alias map for nearby keywords that don't exactly match the list values
# e.g. user says "near metro" → maps to "Metro Station"
# FIX BUG-E: Alias map so "metro", "bus stop", "supermarket", "clinic" all resolve correctly
RENTAL_NEARBY_ALIASES = {
    "metro station": "Metro Station",
    "metro":         "Metro Station",
    "hospital":      "Hospital",
    "clinic":        "Hospital",
    "bus stand":     "Bus Stand",
    "bus stop":      "Bus Stand",
    "bus depot":     "Bus Stand",
    "restaurant":    "Restaurant",
    "cafe":          "Restaurant",
    "super market":  "Super Market",
    "supermarket":   "Super Market",
    "grocery":       "Super Market",
    "mall":          "Super Market",
}

RENTAL_PARKING_MAP = {
    "parking not available": "Parking Not Available",
    "no parking":            "Parking Not Available",
    "both parking":          "Both",
    "two-wheeler":           "Two Wheeler",
    "two wheeler":           "Two Wheeler",
    "four-wheeler":          "Four Wheeler",
    "four wheeler":          "Four Wheeler",
    "both":                  "Both",
    "bike":                  "Two Wheeler",
    "car":                   "Four Wheeler",
    "with parking":          "Both",
    "has parking":           "Both"
}

RENTAL_PLOT_TYPE_MAP = {
    "gated community": "Gated Communuity",
    "gated":           "Gated Communuity",
    "independent plot":"Independent Plot",
    "layout":          "Layout",
}

# ── ID LOOKUP MAPS (from rent.json) ────────────────────────────────────────

_FURNISH_ID_MAP = {
    "Semi furnished": 1,
    "Furnished":      2,
    "Unfurnished":    3,
}

_TENANT_ID_MAP = {
    "Bachelor": 1,
    "Family":   2,
    "Anyone":   3,
    "Ladies":   4,
}

_PROP_ID_MAP = {
    "Apartment":        1,
    "Villa":            2,
    "Plot":             3,
    "Independent House":4,
}

_DOORFACE_ID_MAP = {
    "East":  1,
    "West":  2,
    "South": 3,
    "North": 4,
}

_NEARBY_ID_MAP = {
    "Restaurant":    1,
    "Hospital":      2,
    "Metro Station": 3,
    "Super Market":  4,
    "Bus Stand":     5,
}

_BATHROOM_ID_MAP = {
    1: 24750, 2: 24751, 3: 24752, 4: 24753, 5: 24754,
}

# Ownership & Parking are free-text in rent.json (no fixed IDs), keep as labels
# PlotType is also free-text — no fixed IDs in rent.json


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_map_field(text_lower: str, mapping: dict):
    """Match longest keyword first to avoid 'furnished' beating 'semi furnished'."""
    for keyword in sorted(mapping, key=len, reverse=True):
        if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
            return mapping[keyword]
    return None


def _extract_list_field(text_lower: str, value_list: list) -> list:
    found = []
    for val in value_list:
        if re.search(rf"\b{re.escape(val.lower())}\b", text_lower):
            found.append(val)
    return found


def _extract_nearby(text_lower: str) -> list:
    """FIX: Use alias map so 'metro', 'bus stop', 'supermarket' all match correctly."""
    found = set()
    for kw in sorted(RENTAL_NEARBY_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(kw)}\b", text_lower):
            found.add(RENTAL_NEARBY_ALIASES[kw])
    return sorted(found)


# ═══════════════════════════════════════════════════════════════════════════
# RENT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_rent(text: str) -> dict:
    t = text.lower().replace(",", "")

    def to_num(val, unit=""):
        v = float(val)
        u = (unit or "").strip().lower()
        if u in ("k", "thousand"): return int(v * 1_000)
        if u in ("l", "lakh", "lakhs"): return int(v * 100_000)
        return int(v)

    # Normalize: "15k" → "15 k"
    t = re.sub(r'(\d)(k)\b', r'\1 \2', t)

    # FIX: remove sqft expressions BEFORE any rent matching so that
    # "2000 - 3000sqft" is never mistaken for a rent range.
    # Covers: "2000sqft", "2000 sqft", "2000 - 3000sqft", "2000 to 3000 sq ft" etc.
    t_no_area = re.sub(r'\d+\s*(?:-|to)\s*\d+\s*sqft', '', t)
    t_no_area = re.sub(r'\d+\s*sqft', '', t_no_area)

    units = r'(k|thousand|l|lakh|lakhs)?'

    # Range: "15k to 25k" / "between 15000 and 25000" — use area-stripped text
    rng = re.search(
        rf'(?:between\s*)?(\d+(?:\.\d+)?)\s*{units}\s*(?:to|-|and)\s*(\d+(?:\.\d+)?)\s*{units}'
        rf'(?:\s*(?:rent|per month|/month|pm))?', t_no_area)
    if rng:
        v1 = to_num(rng.group(1), rng.group(2) or "")
        v2 = to_num(rng.group(3), rng.group(4) or "")
        if v1 > 100 and v2 > 100:
            return {"minRent": min(v1, v2), "maxRent": max(v1, v2)}

    # under / below / upto — use original text (no conflict with sqft here)
    under = re.search(
        rf'(?:under|below|less than|upto|up to)\s*(\d+(?:\.\d+)?)\s*{units}', t)
    if under:
        return {"minRent": None, "maxRent": to_num(under.group(1), under.group(2) or "")}

    # above / over / more than
    above = re.search(
        rf'(?:above|over|more than|minimum)\s*(\d+(?:\.\d+)?)\s*{units}', t)
    if above:
        return {"minRent": to_num(above.group(1), above.group(2) or ""), "maxRent": None}

    # explicit "rent 15000" / "15k rent" / "15000/month"
    single = re.search(
        rf'(\d+(?:\.\d+)?)\s*{units}(?:\s*(?:rent|per month|/month|pm))', t)
    if single:
        return {"minRent": None, "maxRent": to_num(single.group(1), single.group(2) or "")}

    # bare 4–6 digit number — use area-stripped text so sqft numbers are gone
    bare = [int(x) for x in re.findall(r'\b(\d{4,6})\b', t_no_area)
            if int(x) >= 1000]
    if len(bare) == 1:
        return {"minRent": None, "maxRent": bare[0]}
    if len(bare) >= 2:
        return {"minRent": min(bare), "maxRent": max(bare)}

    return {"minRent": None, "maxRent": None}


# ═══════════════════════════════════════════════════════════════════════════
# AREA EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_area(text: str) -> dict:
    t = text.lower()
    for k, v in {"sq ft": "sqft", "sft": "sqft", "sqt": "sqft"}.items():
        t = t.replace(k, v)

    # Range: "between 1000 and 2000 sqft"
    m = re.search(r'between\s*(\d+)\s*(?:to|-|and)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": int(m.group(1)), "maxArea": int(m.group(2))}

    # Range: "1000 - 2000 sqft" or "1000 to 2000 sqft"
    m = re.search(r'(\d+)\s*(?:-|to)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": int(m.group(1)), "maxArea": int(m.group(2))}

    # Upper bound: "under 2000 sqft"
    m = re.search(r'(?:under|below|less than)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": None, "maxArea": int(m.group(1))}

    # Lower bound: "above 1000 sqft"
    m = re.search(r'(?:above|more than|over)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": int(m.group(1)), "maxArea": None}

    # Single value: "2000 sqft" → maxArea only, minArea null
    m = re.search(r'(\d+)\s*sqft', t)
    if m: return {"minArea": None, "maxArea": int(m.group(1))}

    return {"minArea": None, "maxArea": None}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN RENTAL SEARCH FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def rental_search(text: str) -> dict:
    """
    Parse a natural-language rental query.

    Fully integrated with fuzzy locality matching and NER city inference —
    same capability as the buy pipeline.

    Output keys:
      bhk, Bathroom, Balcony, Furnish, Tenants, Propertytype, Ownership,
      Doorface, Amenities, Facilities, Nearby, Parking, PlotType,
      locality, localityId, city, cityId, minRent, maxRent
    """
    tl = text.lower()

    # ── BHK ──────────────────────────────────────────────────────────────
    # FIX: capture both digit AND suffix so "1 RK" -> "1 RK", not "1 BHK"
    bhk_matches = re.findall(
        r'(\d+)\s*(bhk|b[\s\.]*h[\s\.]*k|rk|r[\s\.]*k)',
        tl, re.IGNORECASE)

    # bare "rk" with no leading digit -> treat as "1 RK"
    if not bhk_matches and re.search(r'\brk\b', tl):
        bhk_matches = [("1", "rk")]

    def _label(digit, suffix):
        """Return canonical label: '1 RK', '2 BHK', etc."""
        n = int(digit)
        is_rk = re.match(r'r[\s\.]*k', suffix.strip(), re.IGNORECASE) is not None
        return f"{n} {'RK' if is_rk else 'BHK'}"

    if len(bhk_matches) == 1:
        bhk_val = _label(*bhk_matches[0])
    elif len(bhk_matches) > 1:
        bhk_val = [_label(d, s) for d, s in bhk_matches]
    else:
        bhk_val = None

    # ── BATHROOM ─────────────────────────────────────────────────────────
    bath = re.search(r'(\d+)\s*(?:bath|bathroom|toilet)s?', tl)
    bathroom_val = int(bath.group(1)) if bath else None

    # ── BALCONY ──────────────────────────────────────────────────────────
    bm = re.search(r'(\d+)\s*balcon', tl)
    balcony_val = int(bm.group(1)) if bm else (1 if re.search(r'\bbalcon', tl) else None)

    # ── LOCALITY + CITY (fuzzy match, same as buy pipeline) ───────────────
    loc_data = extract_locality(text, locality_list_norm, locality_map_norm)
    city_data = infer_city(loc_data.get("locality"), locality_to_city, locality_to_city_id)

    # Fallback: direct city name match (handles "banglore", "bengaluru", etc.)
    if city_data.get("city") is None:
        city_data = extract_city_direct(text, city_map)

    # ── RENT + AREA ───────────────────────────────────────────────────────
    rent = _extract_rent(text)
    area = _extract_area(text)

    # ── BUILD RESULT ──────────────────────────────────────────────────────
    # BHK ID lookup
    _BHK_ID_MAP = {
        "1 RK": 3550, "1 BHK": 3551, "2 BHK": 3552,
        "3 BHK": 3553, "4 BHK": 3554, "5 BHK": 3555,
    }
    def _bhk_to_id(bhk):
        if bhk is None: return None
        if isinstance(bhk, list):
            ids = [_BHK_ID_MAP[b] for b in bhk if b in _BHK_ID_MAP]
            return ids if ids else None
        return _BHK_ID_MAP.get(bhk)

    # Resolve all labels first so IDs can reference them
    _furnish_label  = _extract_furnish(tl)
    _tenant_label   = _extract_map_field(tl, RENTAL_TENANT_MAP)
    _prop_label     = _extract_map_field(tl, RENTAL_PROPERTY_TYPE_MAP)
    _doorface_label = _extract_map_field(tl, RENTAL_DOOR_FACE_MAP)
    _nearby_labels  = _extract_nearby(tl) or None
    _bathroom_int   = bathroom_val

    # Bathroom → ID via lookup map (1→24750 … 5→24754)
    _bathroom_id    = _BATHROOM_ID_MAP.get(_bathroom_int) if _bathroom_int else None

    # Nearby → list of IDs
    _nearby_ids     = ([_NEARBY_ID_MAP[n] for n in _nearby_labels if n in _NEARBY_ID_MAP]
                       if _nearby_labels else None)

    result = {
        "bhk":            bhk_val,
        "bhkId":          _bhk_to_id(bhk_val),
        "Bathroom":       _bathroom_int,
        "BathroomId":     _bathroom_id,
        "Balcony":        balcony_val,
        "Furnish":        _furnish_label,
        "FurnishId":      _FURNISH_ID_MAP.get(_furnish_label),
        "Tenants":        _tenant_label,
        "TenantsId":      _TENANT_ID_MAP.get(_tenant_label),
        "Propertytype":   _prop_label,
        "PropertytypeId": _PROP_ID_MAP.get(_prop_label),
        "Ownership":      _extract_map_field(tl, RENTAL_OWNERSHIP_MAP),
        "Doorface":       _doorface_label,
        "DoorfaceId":     _DOORFACE_ID_MAP.get(_doorface_label),
        "Amenities":      (_extract_list_field(tl, RENTAL_AMENITIES) or None),
        "AmenitiesId":    _to_amenities_ids(_extract_list_field(tl, RENTAL_AMENITIES)),
        "Facilities":     (_extract_list_field(tl, RENTAL_FACILITIES) or None),
        "Nearby":         _nearby_labels,
        "NearbyId":       _nearby_ids,
        "Parking":        _extract_map_field(tl, RENTAL_PARKING_MAP),
        "PlotType":       _extract_map_field(tl, RENTAL_PLOT_TYPE_MAP),
        # ── locality / city from fuzzy + NER ──
        "locality":     loc_data.get("locality"),
        "localityId":   loc_data.get("localityId"),
        "city":         city_data.get("city"),
        "cityId":       ([int(c) for c in city_data["cityId"]] if isinstance(city_data.get("cityId"), list)
                         else (int(city_data["cityId"]) if city_data.get("cityId") is not None else None)),
        # ── price / area ──
        "minRent":      rent.get("minRent"),
        "maxRent":      rent.get("maxRent"),
        "minArea":      area.get("minArea"),
        "maxArea":      area.get("maxArea"),
    }

    # ── SMART QUERY ───────────────────────────────────────────────────────
    parts = []
    if result["bhk"]:
        parts.append(result["bhk"] if isinstance(result["bhk"], str)
                     else " & ".join(result["bhk"]))
    if result["Furnish"]:      parts.append(result["Furnish"])
    if result["Propertytype"]: parts.append(result["Propertytype"])
    if result["Tenants"]:      parts.append(f"for {result['Tenants']}")

    if result["locality"]:
        loc_str = result["locality"] if isinstance(result["locality"], str) \
                  else " & ".join(result["locality"])
        parts.append(loc_str)
    elif result["city"]:
        parts.append(result["city"])

    def fmt(v):
        if v is None: return None
        if v >= 100_000: return f"Rs.{v/100_000:.2g}L/mo"
        if v >= 1_000:   return f"Rs.{v/1_000:.4g}k/mo"
        return f"Rs.{v}/mo"

    mn, mx = result["minRent"], result["maxRent"]
    if mn and mx:   parts.append(f"{fmt(mn)} - {fmt(mx)}")
    elif mx:        parts.append(f"under {fmt(mx)}")
    elif mn:        parts.append(f"above {fmt(mn)}")

    if result["Nearby"]:   parts.append("near " + ", ".join(result["Nearby"]))
    if result["Amenities"]: parts.append("with " + ", ".join(result["Amenities"]))

    result["smart_query"] = " | ".join(parts) if parts else text
    result["search_type"] = "rental"

    return result


# ═══════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    tests = [
        # basic
        "2bhk furnished apartment for family under 25k near hospital",
        # with locality (exact)
        "2bhk furnished flat for family under 25k in whitefield",
        # locality typo
        "3bhk villa for bachelor with gym in koramangla",
        # city typo
        "1bhk flat owner east facing under 15000 in banglore",
        # multi-locality
        "2bhk semi furnished in whitefield and hebbal under 30k",
        # area + amenities
        "3bhk unfurnished 1500 sqft with swimming pool and gym near metro",
        # rent range
        "2bhk house for rent 20k to 35k in indiranagar",
        # gated community + power backup
        "2bhk semi furnished with power backup gated community hsr layout",
        # multi-bhk
        "2bhk and 3bhk furnished flat for ladies under 40k",
        # bare number rent
        "1bhk apartment 12000 near restaurant south facing",
    ]

    print("=" * 70)
    print("RENTAL PIPELINE TEST")
    print("=" * 70)
    for q in tests:
        r = rental_search(q)
        print(f"\nQ : {q}")
        print(f"  bhk={r['bhk']}  furnish={r['Furnish']}  type={r['Propertytype']}")
        print(f"  locality={r['locality']}  city={r['city']}")
        print(f"  rent={r['minRent']}-{r['maxRent']}  area={r['minArea']}-{r['maxArea']}")
        print(f"  amenities={r['Amenities']}  nearby={r['Nearby']}")
        print(f"  smart_query → {r['smart_query']}")