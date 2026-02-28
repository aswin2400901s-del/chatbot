#!/usr/bin/env python
# coding: utf-8

"""
pg_pipeline.py — Natural language search parser for PG / Hostel properties.

Fully integrated with:
  - fuzzy_match.py  → locality extraction (handles typos, multi-locality)
  - NER_training.py → locality→city inference, city direct match

Output keys match pg.csv headers exactly:
  meels, parking, pgAvailableForList, pgBestSuitForList, pgFacilitiesList,
  pgFoodChargesList, pgListingAsList, pgMealTypeList, pgNoticePeriodList,
  pgRulesList, pgServiceList, pgStartedYearList, pgTenantsReturnByList,
  pg_AmenitiesList, propertyAvailableList, propertyTypeList,
  roomOtherTypes, roomTypes
  + locality, localityId, city, cityId, minRent, maxRent
"""

import re

# ── NER + Fuzzy imports ────────────────────────────────────────────────────
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

_ensure_indexes(locality_list_norm)

# ═══════════════════════════════════════════════════════════════════════════
# ID LOOKUP TABLES  (from pg.json)
# ═══════════════════════════════════════════════════════════════════════════

PG_AVAILABLE_FOR_ID   = {"Boys": 1, "Girls": 2, "Co-living": 3}
PG_BEST_SUIT_ID       = {"Students": 1, "Working Professionals": 2, "All": 3}
PG_ROOM_TYPE_ID       = {
    "Private Room": 1, "Two Sharing": 2, "Three Sharing": 3,
    "Four Sharing": 4, "Five Sharing": 5, "Six Sharing": 6, "Others": 13,
}
PG_AMENITIES_ID       = {
    "Gym": 2, "Wi-Fi Connection": 10, "Power Backup": 9, "TV": 11,
    "Microwave": 6, "Washing Machine": 4, "Dining Area": 14, "CCTV": 12,
}
PG_SERVICE_ID         = {
    "Laundry": 1, "Security": 4, "Room Cleaning": 5, "Biometric": 2, "Warden": 3,
}
PG_FACILITIES_ID      = {
    "Air Conditioner": 31, "Attached Bathroom": 21, "Geyser": 19,
    "Table Fan": 30, "Cupboard": 29,
}
PG_MEALS_ID           = {"Breakfast": 1, "Lunch": 2, "Dinner": 3}

# Meal alias map — catches count-based phrases like "1 meal only", "2 meals", etc.
MEALS_ALIAS_MAP = {
    "3 meals":       ["Breakfast", "Lunch", "Dinner"],
    "three meals":   ["Breakfast", "Lunch", "Dinner"],
    "all meals":     ["Breakfast", "Lunch", "Dinner"],
    "all 3 meals":   ["Breakfast", "Lunch", "Dinner"],
    "2 meals":       ["Breakfast", "Lunch"],
    "two meals":     ["Breakfast", "Lunch"],
    "1 meal":        ["Breakfast"],
    "one meal":      ["Breakfast"],
    "meal only":     ["Breakfast"],
    "meals only":    ["Breakfast"],
    "food included": ["Breakfast"],
    "meal included": ["Breakfast"],
    "meal":          ["Breakfast"],
    "meals":         ["Breakfast"],
    "food":          ["Breakfast"],
    "breakfast":     ["Breakfast"],
    "lunch":         ["Lunch"],
    "dinner":        ["Dinner"],
}


def _to_id(label, id_map):
    """Return id for a single label string, or None."""
    return id_map.get(label) if label else None


def _to_id_list(labels, id_map):
    """Return list of ids for a list of labels, skipping unknowns."""
    return [id_map[l] for l in (labels or []) if l in id_map] or []


def _extract_meals(text_lower: str) -> list:
    """
    Extract meal labels using alias map (longest match first),
    then fall back to individual meal names.
    Returns list of meal LABELS e.g. ["Breakfast", "Lunch"].

    FIX: Only use the alias map for MULTI-meal shorthand phrases
         (e.g. "all meals", "3 meals", "food included").
         Single-meal aliases like "breakfast", "lunch", "dinner" are
         handled by the individual-scan loop below, so that
         "breakfast and lunch" correctly returns ["Breakfast", "Lunch"]
         instead of short-circuiting on "breakfast" → ["Breakfast"].
    """
    # Only fire alias map for phrases that represent MORE THAN ONE meal
    # (i.e. the value list has length > 1), so we never swallow individual
    # mentions that appear alongside other meal words.
    for kw in sorted(MEALS_ALIAS_MAP, key=len, reverse=True):
        if len(MEALS_ALIAS_MAP[kw]) > 1:          # multi-meal alias only
            if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                return MEALS_ALIAS_MAP[kw]

    # Individual meal scan — catches "breakfast", "lunch", "dinner"
    # and any combination thereof (e.g. "breakfast and lunch")
    found = []
    for meal in ["Breakfast", "Lunch", "Dinner"]:
        if re.search(rf"\b{re.escape(meal.lower())}\b", text_lower):
            if meal not in found:
                found.append(meal)

    if found:
        return found

    # Final fallback: single-meal aliases like "food included", "meal", "food"
    for kw in sorted(MEALS_ALIAS_MAP, key=len, reverse=True):
        if re.search(rf"\b{re.escape(kw)}\b", text_lower):
            return MEALS_ALIAS_MAP[kw]

    return []


# ═══════════════════════════════════════════════════════════════════════════
# MASTER VALUE MAPS  (from pg.csv)
# ═══════════════════════════════════════════════════════════════════════════

PG_AVAILABLE_FOR_MAP = {
    "co-living":  "Co-living",
    "co living":  "Co-living",
    "coliving":   "Co-living",
    "mixed":      "Co-living",
    "boys":       "Boys",
    "male":       "Boys",
    "gents":      "Boys",
    "girls":      "Girls",
    "female":     "Girls",
    "ladies":     "Girls",
}

PG_SUITED_FOR_MAP = {
    "working professionals": "Working Professionals",
    "working professional":  "Working Professionals",
    "professionals":         "Working Professionals",
    "students":              "Students",
    "student":               "Students",
    "working":               "Working Professionals",
    "all":                   "All",
    "anyone":                "All",
}

# roomTypes (standard, from CSV)
ROOM_TYPES = {
    "four sharing":  "Four Sharing",
    "three sharing": "Three Sharing",
    "two sharing":   "Two Sharing",
    "double sharing":"Two Sharing",
    "triple sharing":"Three Sharing",
    "private room":  "Private Room",
    "private":       "Private Room",
    "single room":   "Private Room",
    "single":        "Private Room",
    "4 sharing":     "Four Sharing",
    "3 sharing":     "Three Sharing",
    "2 sharing":     "Two Sharing",
    "others":        "Others",
}

# roomOtherTypes (large sharing, from CSV)
ROOM_OTHER_TYPES = {
    "ten sharing":    "Ten Sharing",
    "nine sharing":   "Nine Sharing",
    "eight sharing":  "Eight Sharing",
    "seven sharing":  "Seven Sharing",
    "six sharing":    "Six Sharing",
    "five sharing":   "Five Sharing",
    "10 sharing":     "Ten Sharing",
    "9 sharing":      "Nine Sharing",
    "8 sharing":      "Eight Sharing",
    "7 sharing":      "Seven Sharing",
    "6 sharing":      "Six Sharing",
    "5 sharing":      "Five Sharing",
}

MEAL_TYPE_MAP = {
    "veg/non veg":  "Veg/Non Veg",
    "non-veg":      "Veg/Non Veg",
    "non veg":      "Veg/Non Veg",
    "nonveg":       "Veg/Non Veg",
    "veg only":     "Veg Only",
    "vegetarian":   "Veg Only",
    "veg":          "Veg Only",
}

FOOD_CHARGES_MAP = {
    "included in rent": "Included in rent",
    "per meal basis":   "Per Meal Basis",
    "per meal":         "Per Meal Basis",
    "included":         "Included in rent",
    "free food":        "Included in rent",
    "pay per meal":     "Per Meal Basis",
}

MEALS_LIST = ["Breakfast", "Lunch", "Dinner"]

PG_FACILITIES_LIST = [
    "Air Conditioner", "Attached Bathroom", "Cupboard",
    "Geyser", "Mattress", "Table Fan", "Table and Chair", "Television",
]

PG_AMENITIES_LIST = [
    "CCTV", "Dining Area", "Elevator", "Fridge", "Gym", "Indoor Games",
    "Lobby", "Microwave", "Mineral Water", "Power Backup",
    "Self Cooking Kitchen", "Shoe Rack", "TV", "Washing Machine",
    "Wi-Fi Connection",
]

PG_SERVICES_LIST = [
    "Biometric", "Laundry", "Room Cleaning", "Security", "Warden",
]

PG_RULES_LIST = [
    "No Alcohol", "No Guardians Stay", "No Loud Music", "No Non Veg",
    "No Opposite Gender", "No Party", "No Somoking", "No Visitors Entry",
]

PG_LISTING_MAP = {
    "property manager": "Property Manager",
    "manager":          "Property Manager",
    "owner":            "Owner",
    "direct":           "Owner",
    "broker":           "Broker",
    "agent":            "Broker",
}

NOTICE_PERIOD_MAP = {
    "45-60 days": "45-60 Days",
    "30-45 days": "30-45 Days",
    "15-30 days": "15-30 Days",
    "0-15 days":  "0-15 Days",
    "60 days":    "60 Days",
    "45 days":    "45-60 Days",
    "30 days":    "30-45 Days",
    "15 days":    "15-30 Days",
    "2 months":   "60 Days",
    "1 month":    "30-45 Days",
}

RETURN_BY_MAP = {
    "no gate closing time": "No Gate Closing time",
    "no gate closing":      "No Gate Closing time",
    "no curfew":            "No Gate Closing time",
    "anytime":              "No Gate Closing time",
    "11 pm":                "11 PM",
    "10 pm":                "10 PM",
    "11pm":                 "11 PM",
    "10pm":                 "10 PM",
    "9 pm":                 "9 PM",
    "8 pm":                 "8 PM",
    "9pm":                  "9 PM",
    "8pm":                  "8 PM",
}

PARKING_MAP = {
    "two-wheeler":  "Two Wheeler",
    "two wheeler":  "Two Wheeler",
    "four-wheeler": "Four Wheeler",
    "four wheeler": "Four Wheeler",
    "both":         "Both",
    "bike":         "Two Wheeler",
    "car":          "Four Wheeler",
}

PROPERTY_AVAILABLE_MAP = {
    "pg/hostel":   "PG/Hostel",
    "pg hostel":   "PG/Hostel",
    "hostel":      "PG/Hostel",
    "pg":          "PG/Hostel",
    "rent/lease":  "Rent/Lease",
    "rent":        "Rent/Lease",
    "lease":       "Rent/Lease",
    "sale":        "Sale",
}

PROPERTY_TYPE_MAP = {
    "commercial":  "Commercial",
    "residential": "Residential",
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_map_field(text_lower: str, mapping: dict):
    for keyword in sorted(mapping, key=len, reverse=True):
        if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
            return mapping[keyword]
    return None


def _extract_list_field(text_lower: str, value_list: list) -> list:
    """
    FIX: Labels like "Wi-Fi Connection" have hyphens that break \b word
         boundaries. We handle these with custom alias patterns.
    """
    _ALIASES = {
        "wi-fi connection": [r"wi[\s\-]?fi", r"wifi"],
        "power backup":     [r"power\s*backup"],
        "washing machine":  [r"washing\s*machine", r"washer"],
        "dining area":      [r"dining\s*(area|hall)?"],
    }
    found = []
    for v in value_list:
        key = v.lower()
        matched = False
        if key in _ALIASES:
            for pat in _ALIASES[key]:
                if re.search(pat, text_lower):
                    matched = True
                    break
        else:
            try:
                matched = bool(re.search(rf"\b{re.escape(key)}\b", text_lower))
            except re.error:
                matched = key in text_lower
        if matched:
            found.append(v)
    return found


def _extract_multi_map(text_lower: str, mapping: dict) -> list:
    """Return ALL matching values (multi-select fields like meals)."""
    seen, found = set(), []
    for kw in sorted(mapping, key=len, reverse=True):
        if re.search(rf"\b{re.escape(kw)}\b", text_lower):
            val = mapping[kw]
            if val not in seen:
                seen.add(val)
                found.append(val)
    return found


# ═══════════════════════════════════════════════════════════════════════════
# RENT EXTRACTION (PG-specific: ₹3k–₹30k/month range)
# ═══════════════════════════════════════════════════════════════════════════

def _extract_pg_rent(text: str) -> dict:
    t = text.lower().replace(",", "")
    t = re.sub(r'(\d)(k)\b', r'\1 \2', t)

    def to_num(val, unit=""):
        v = float(val)
        u = (unit or "").strip().lower()
        if u in ("k", "thousand"): return int(v * 1_000)
        if u in ("l", "lakh"):     return int(v * 100_000)
        return int(v)

    units = r'(k|thousand|l|lakh)?'

    # Range
    rng = re.search(
        rf'(?:between\s*)?(\d+(?:\.\d+)?)\s*{units}\s*(?:to|-|and)\s*(\d+(?:\.\d+)?)\s*{units}'
        rf'(?:\s*(?:rent|per month|/month|pm))?', t)
    if rng:
        v1 = to_num(rng.group(1), rng.group(2) or "")
        v2 = to_num(rng.group(3), rng.group(4) or "")
        if v1 > 500 and v2 > 500:
            return {"minRent": min(v1, v2), "maxRent": max(v1, v2)}

    under = re.search(rf'(?:under|below|less than|upto|up to)\s*(\d+(?:\.\d+)?)\s*{units}', t)
    if under:
        # FIX: minRent should be null (not 0) when only an upper bound is stated
        return {"minRent": None, "maxRent": to_num(under.group(1), under.group(2) or "")}

    above = re.search(rf'(?:above|over|more than|minimum)\s*(\d+(?:\.\d+)?)\s*{units}', t)
    if above:
        return {"minRent": to_num(above.group(1), above.group(2) or ""), "maxRent": None}

    # explicit rent keyword
    single = re.search(
        rf'(\d+(?:\.\d+)?)\s*{units}(?:\s*(?:rent|per month|/month|pm))', t)
    if single:
        return {"minRent": 0, "maxRent": to_num(single.group(1), single.group(2) or "")}

    # bare 4–5 digit number (PG range: 1000–99999) — exclude years
    year_nums = set(re.findall(r'\b(20\d{2})\b', t))
    bare = [int(x) for x in re.findall(r'\b(\d{4,5})\b', t)
            if 1000 <= int(x) <= 99999 and x not in year_nums]
    if len(bare) == 1:
        return {"minRent": 0, "maxRent": bare[0]}

    return {"minRent": None, "maxRent": None}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN PG SEARCH FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def pg_search(text: str) -> dict:
    """
    Parse a natural-language PG/Hostel query.
    Fully integrated with fuzzy locality matching and NER city inference.
    """
    tl = text.lower()

    # ── LOCALITY + CITY ────────────────────────────────────────────────────
    loc_data  = extract_locality(text, locality_list_norm, locality_map_norm)
    city_data = infer_city(loc_data.get("locality"), locality_to_city, locality_to_city_id)
    if city_data.get("city") is None:
        city_data = extract_city_direct(text, city_map)

    city_id = city_data.get("cityId")
    if isinstance(city_id, list):
        city_id = [int(c) for c in city_id]
    elif city_id is not None:
        city_id = int(city_id)

    # ── ROOM TYPE: standard vs large sharing ──────────────────────────────
    room_type       = _extract_map_field(tl, ROOM_TYPES)
    room_other_type = _extract_map_field(tl, ROOM_OTHER_TYPES)

    # ── YEAR ──────────────────────────────────────────────────────────────
    year_m = re.search(r'\b(20\d{2})\b', text)

    rent = _extract_pg_rent(text)

    # ── Extract labels first (needed for smart_query + ID conversion) ────────
    _avail_label    = _extract_map_field(tl, PG_AVAILABLE_FOR_MAP)
    _suited_label   = _extract_map_field(tl, PG_SUITED_FOR_MAP)
    _room_label     = room_type                                       # already extracted above
    _meal_labels    = _extract_meals(tl)                              # list of meal label strings
    _amenity_labels = _extract_list_field(tl, PG_AMENITIES_LIST)
    _service_labels = _extract_list_field(tl, PG_SERVICES_LIST)
    _facility_labels= _extract_list_field(tl, PG_FACILITIES_LIST)

    result = {
        # ── IDs from pg.json ──
        "meels":                 _to_id_list(_meal_labels,     PG_MEALS_ID),
        "parking":               _extract_map_field(tl, PARKING_MAP),
        "pgAvailableForList":    _to_id(_avail_label,          PG_AVAILABLE_FOR_ID),
        "pgBestSuitForList":     _to_id(_suited_label,         PG_BEST_SUIT_ID),
        "pgFacilitiesList":      (_to_id_list(_facility_labels, PG_FACILITIES_ID) if _facility_labels else None),
        "pgFoodChargesList":     _extract_map_field(tl, FOOD_CHARGES_MAP),
        "pgListingAsList":       _extract_map_field(tl, PG_LISTING_MAP),
        "pgMealTypeList":        _extract_map_field(tl, MEAL_TYPE_MAP),
        "pgNoticePeriodList":    _extract_map_field(tl, NOTICE_PERIOD_MAP),
        "pgRulesList":           (_extract_list_field(tl, PG_RULES_LIST) or None),
        # FIX: store labels for suggestions.py; IDs in pgServiceListIds
        # Empty list → null (not-specified vs found-nothing distinction)
        "pgServiceList":         _service_labels if _service_labels else None,
        "pgServiceListIds":      (_to_id_list(_service_labels, PG_SERVICE_ID)
                                  if _service_labels else None),
        "pgStartedYearList":     year_m.group(1) if year_m else None,
        "pgTenantsReturnByList": _extract_map_field(tl, RETURN_BY_MAP),
        # FIX: store labels so suggestions.py can pass them to _id_multi correctly.
        # The API payload IDs are available via pg_AmenitiesListIds.
        # Empty list → null (not-specified vs found-nothing distinction)
        "pg_AmenitiesList":      _amenity_labels if _amenity_labels else None,
        "pg_AmenitiesListIds":   (_to_id_list(_amenity_labels, PG_AMENITIES_ID)
                                  if _amenity_labels else None),
        "propertyAvailableList": _extract_map_field(tl, PROPERTY_AVAILABLE_MAP),
        "propertyTypeList":      _extract_map_field(tl, PROPERTY_TYPE_MAP),
        "roomOtherTypes":        room_other_type,
        "roomTypes":             _to_id(_room_label,           PG_ROOM_TYPE_ID),
        # ── locality / city ──
        "locality":              loc_data.get("locality"),
        "localityId":            loc_data.get("localityId"),
        "city":                  city_data.get("city"),
        "cityId":                city_id,
        # ── rent ──
        "minRent":               rent.get("minRent"),
        "maxRent":               rent.get("maxRent"),
    }

    # ── SMART QUERY — uses original labels, NOT ids ─────────────────────────
    parts = []
    if _avail_label:   parts.append(f"{_avail_label} PG")
    if _suited_label:  parts.append(f"for {_suited_label}")
    if _room_label:    parts.append(_room_label)
    elif room_other_type: parts.append(room_other_type)
    if result["pgMealTypeList"]: parts.append(result["pgMealTypeList"])
    if _meal_labels:   parts.append(" + ".join(_meal_labels))

    if result["locality"]:
        parts.append(result["locality"] if isinstance(result["locality"], str)
                     else " & ".join(result["locality"]))
    elif result["city"]:
        parts.append(result["city"])

    def fmt(v):
        if v is None: return None
        if v >= 1_000: return f"Rs.{v/1_000:.4g}k/mo"
        return f"Rs.{v}/mo"

    mn, mx = result["minRent"], result["maxRent"]
    if mn and mx:   parts.append(f"{fmt(mn)} - {fmt(mx)}")
    elif mx:        parts.append(f"under {fmt(mx)}")
    elif mn:        parts.append(f"above {fmt(mn)}")

    if _amenity_labels:
        parts.append("with " + ", ".join(_amenity_labels))
    if _service_labels:
        parts.append("+ " + ", ".join(_service_labels))

    result["smart_query"] = " | ".join(parts) if parts else text
    result["search_type"] = "pg"

    return result


# ═══════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    tests = [
        # basic
        "boys pg for working professionals private room with wifi and gym under 8k",
        # locality exact
        "girls pg in whitefield two sharing veg food included laundry",
        # locality typo
        "co-living near koramangla with gym and washing machine",
        # city typo
        "boys hostel in banglore under 12000",
        # multi-locality
        "pg in whitefield and hebbal private room with ac geyser",
        # meals
        "pg with breakfast lunch and dinner veg only included in rent",
        # rules + services
        "pg no alcohol no smoking with security and room cleaning",
        # return time + notice period
        "girls pg 10 pm gate closing 30 days notice private room under 9k",
        # large sharing
        "pg five sharing six sharing boys near metro with cctv power backup",
        # year started
        "pg started 2020 boys working professionals ac geyser",
    ]

    print("=" * 70)
    print("PG PIPELINE TEST")
    print("=" * 70)
    for q in tests:
        r = pg_search(q)
        print(f"\nQ : {q}")
        print(f"  pgFor={r['pgAvailableForList']}  suitedFor={r['pgBestSuitForList']}")
        print(f"  roomType={r['roomTypes']}  roomOther={r['roomOtherTypes']}")
        print(f"  locality={r['locality']}  city={r['city']}")
        print(f"  rent={r['minRent']}-{r['maxRent']}  meals={r['meels']}")
        print(f"  amenities={r['pg_AmenitiesList']}  services={r['pgServiceList']}")
        print(f"  smart_query → {r['smart_query']}")