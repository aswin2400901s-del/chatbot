#!/usr/bin/env python
# coding: utf-8

"""
commercial_pipeline.py — Natural language search parser for COMMERCIAL properties.

Fully integrated with:
  - fuzzy_match.py  → locality extraction (handles typos, multi-locality)
  - NER_training.py → locality→city inference, city direct match

Output keys match commercial CSV headers exactly:
  FacilitiesList, buildingTypeList, commercialListingAsList,
  commercialPropertyTypeList, commercial_AmenitiesList, furnishTypeList,
  imageslist, lockInPeriodList, officeSuitedFor, plotTypeList, plotViewList,
  propertyAgeList, propertyFacingList, propertyStatusList, suitedForList,
  warehousesuitedfor
  + locality, localityId, city, cityId, minPrice, maxPrice, minArea, maxArea
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
# MASTER VALUE MAPS  (from commerical.csv)
# ═══════════════════════════════════════════════════════════════════════════

COMMERCIAL_PROPERTY_TYPE_MAP = {
    "co-working space": "Co-working space",
    "coworking space":  "Co-working space",
    "co working space": "Co-working space",
    "coworking":        "Co-working space",
    "co-working":       "Co-working space",
    "shared office":    "Co-working space",
    "office space":     "Office Space",
    "office":           "Office Space",
    "shop/showroom":    "Shop/Showroom",
    "showroom":         "Shop/Showroom",
    "shop":             "Shop/Showroom",
    "retail":           "Shop/Showroom",
    "warehouse":        "Warehouse",
    "godown":           "Warehouse",
    "commercial plot":  "Plot",
    "plot":             "Plot",
    "land":             "Plot",
}

BUILDING_TYPE_MAP = {
    "commercial complex": "Commercial Complex",
    "industrial building":"Industrial Building",
    "independent building":"Independent Building",
    "shared building":    "Shared Building",
    "suitable for all":   "Suitable For All",
    "independent":        "Independent Building",
    "industrial":         "Industrial Building",
    "shared":             "Shared Building",
    "mall":               "Mall",
    "shed":               "Shed",
}

COMMERCIAL_FURNISH_MAP = {
    "fully furnished": "Furnished",
    "furnished":       "Furnished",
    "semi furnished":  "Semi Furnish",
    "semi-furnished":  "Semi Furnish",
    "semifurnished":   "Semi Furnish",
    "unfurnished":     "Unfurnish",
    "bare shell":      "Unfurnish",
    "unfurnish":       "Unfurnish",
}

# FIX: fuzzy furnish extraction catches typos like semi-furished, semifurished etc.
_COMM_FURNISH_PATTERNS = [
    (r'\bfully\s+furn\w*\b',     "Furnished"),
    (r'\bfull\s+furn\w*\b',      "Furnished"),
    (r'\bsemi[\s\-]?furi?\w*\b', "Semi Furnish"),
    (r'\bsemi[\s\-]?furn\w*\b',  "Semi Furnish"),
    (r'\bunfurn\w*\b',           "Unfurnish"),
    (r'\bun[\s\-]furnished\b',   "Unfurnish"),
    (r'\bbare[\s\-]?shell\b',    "Unfurnish"),
    (r'\bfurnish\w*\b',          "Furnished"),
]

def _extract_comm_furnish(text_lower: str):
    for pat, label in _COMM_FURNISH_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE):
            return label
    return None

COMMERCIAL_LISTING_MAP = {
    "property manager": "Property Manager",
    "manager":          "Property Manager",
    "owner":            "Owner",
    "direct":           "Owner",
    "broker":           "Broker",
    "agent":            "Broker",
}

COMMERCIAL_AMENITIES = [
    "Air Conditioner", "Biometrics", "CCTV", "EV Charging Station",
    "Elevator", "Fridge", "GYM", "Garden", "Indoor Games",
    "Internet Connectivity", "Microwave", "Mineral Water",
    "Pet Friendly", "Power Backup", "TV",
]

# FIX: common aliases users type that don't match exact amenity names
COMMERCIAL_AMENITIES_ALIASES = {
    "ac":                   "Air Conditioner",
    "a/c":                  "Air Conditioner",
    "air conditioning":     "Air Conditioner",
    "air conditioner":      "Air Conditioner",
    "wifi":                 "Internet Connectivity",
    "wi-fi":                "Internet Connectivity",
    "wi fi":                "Internet Connectivity",
    "internet":             "Internet Connectivity",
    "internet connectivity":"Internet Connectivity",
    "broadband":            "Internet Connectivity",
    "cctv":                 "CCTV",
    "elevator":             "Elevator",
    "lift":                 "Elevator",
    "gym":                  "GYM",
    "power backup":         "Power Backup",
    "generator":            "Power Backup",
    "ev charging":          "EV Charging Station",
    "ev station":           "EV Charging Station",
    "fridge":               "Fridge",
    "refrigerator":         "Fridge",
    "microwave":            "Microwave",
    "mineral water":        "Mineral Water",
    "pet friendly":         "Pet Friendly",
    "pet":                  "Pet Friendly",
    "indoor games":         "Indoor Games",
    "garden":               "Garden",
    "tv":                   "TV",
    "television":           "TV",
    "biometric":            "Biometrics",
    "biometrics":           "Biometrics",
}

COMMERCIAL_FACILITIES = [
    "Auditorium", "Conference Hall", "Electricity Connection",
    "Gated Security", "Pantry", "Pantry/Cafeteria", "Private Washroom",
    "Reception", "Server Room", "Sewage Connection", "Shared Washroom",
    "Storage Area", "Street lights", "Water Supply",
]

OFFICE_SUITED_FOR_MAP = {
    "startup hub":      "Startup Hub",
    "corporate office": "Corporate Office",
    "regional office":  "Regional Office",
    "business park":    "Business Park",
    "call center":      "Call Center",
    "call centre":      "Call Center",
    "headquarters":     "Headquarters",
    "consultancy":      "Consultancy",
    "it park":          "IT park",
    "startup":          "Startup Hub",
    "corporate":        "Corporate Office",
    "bpo":              "BPO",
    "hq":               "Headquarters",
    "it":               "IT park",
}

SHOP_SUITED_FOR_MAP = {
    "clinic / health facility": "Clinic / Health Facility",
    "hotel / guest house":      "Hotel / Guest House",
    "grocery store":            "Grocery Store",
    "fashion store":            "Fashion Store",
    "guest house":              "Hotel / Guest House",
    "restaurant":               "Restaurant",
    "clinic":                   "Clinic / Health Facility",
    "health":                   "Clinic / Health Facility",
    "grocery":                  "Grocery Store",
    "supermarket":              "Grocery Store",
    "fashion":                  "Fashion Store",
    "clothing":                 "Fashion Store",
    "hotel":                    "Hotel / Guest House",
    "cafe":                     "Cafe",
    "gym":                      "GYM",
    "fitness":                  "GYM",
}

WAREHOUSE_SUITED_FOR_MAP = {
    "distribution center": "Distribution Center",
    "industrial storage":  "Industrial Storage",
    "logistics hub":       "Logistics Hub",
    "retail storage":      "Retail Storage",
    "cold storage":        "Cold Storage",
    "logistics":           "Logistics Hub",
    "distribution":        "Distribution Center",
    "cold":                "Cold Storage",
}

PLOT_TYPE_MAP = {
    "mixed-use plot":   "Mixed-Use Plot",
    "agricultural plot":"Agricultural Plot",
    "commercial plot":  "Commercial Plot",
    "industrial plot":  "Industrial Plot",
    "farmhouse plot":   "Farmhouse Plot",
    "independent plot": "Independent Plot",
    "gated community":  "gated community",
    "mixed use":        "Mixed-Use Plot",
    "agricultural":     "Agricultural Plot",
    "industrial":       "Industrial Plot",
    "farmhouse":        "Farmhouse Plot",
    "layout":           "layout",
}

PROPERTY_AGE_MAP = {
    "0-1 yrs":  "0-1 yrs",
    "1-5 yrs":  "1-5 yrs",
    "5-10 yrs": "5-10 yrs",
    "10+ yrs":  "10+ yrs",
    "0-1":      "0-1 yrs",
    "1-5":      "1-5 yrs",
    "5-10":     "5-10 yrs",
    "new":      "0-1 yrs",
    "old":      "10+ yrs",
}

PROPERTY_STATUS_MAP = {
    "ready to move":      "Ready to move",
    "under construction": "Under construction",
    "under-construction": "Under construction",
    "upcoming":           "Under construction",
    "ready":              "Ready to move",
}

DOOR_FACE_MAP = {
    "north": "North",
    "south": "South",
    "east":  "East",
    "west":  "West",
}

LOCK_IN_PERIOD_MAP = {
    "36-48 months": "36-48 Months",
    "24-36 months": "24-36 Months",
    "12-24 months": "12-24 Months",
    "12 months":    "12 Months",
    "2 years":      "12-24 Months",
    "1 year":       "12 Months",
}



# ═══════════════════════════════════════════════════════════════════════════
# ID LOOKUP TABLES  (from commerical.json — all use "key" field)
# Only fields present in commerical.json get integer keys.
# Fields not in the JSON (plotTypeList, warehousesuitedfor etc.) keep labels.
# ═══════════════════════════════════════════════════════════════════════════

_COMM_PROP_ID = {
    "Office Space": 1, "Shop/Showroom": 2, "Plot": 3,
    "Co-working space": 4, "Warehouse": 5, "Others": 6,
}

_BUILDING_TYPE_ID = {
    "Independent Building": 1, "Shared Building": 2, "Commercial Complex": 3,
    "Industrial Building": 4, "Shed": 5, "Mall": 6, "Suitable For All": 7, "Others": 9,
}

_FURNISH_TYPE_ID = {
    "Furnished": 1, "Semi Furnish": 2, "Unfurnish": 3,
}

_OFFICE_SUITED_ID = {
    "IT park": 1, "Business Park": 2, "Startup Hub": 3, "Corporate Office": 4,
    "Call Center": 5, "BPO": 6, "Consultancy": 7, "Headquarters": 8,
    "Regional Office": 9, "Others": 10,
}

_COMM_AMENITIES_ID = {
    "Air Conditioner": 12, "Internet Connectivity": 23, "Fridge": 24,
    "Microwave": 25, "Mineral Water": 26, "Elevator": 28, "GYM": 29,
    "Power Backup": 31, "Biometrics": 32, "TV": 35, "CCTV": 36,
    "Garden": 37, "EV Charging Station": 38, "Pet Friendly": 39, "Indoor Games": 40,
}

_PROPERTY_STATUS_ID = {
    "Ready to move": 1, "Under construction": 2,
}

_PROPERTY_FACING_ID = {
    "North": 1, "South": 2, "West": 3, "East": 4,
}


def _label_to_id(label, id_map):
    """Convert a label string to its integer key. Returns None if not found."""
    if label is None:
        return None
    return id_map.get(label)


def _labels_to_ids(labels, id_map):
    """Convert a list of label strings to their integer keys. Returns None if empty."""
    if not labels:
        return None
    ids = [id_map[l] for l in labels if l in id_map]
    return ids if ids else None

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_map_field(text_lower: str, mapping: dict):
    for keyword in sorted(mapping, key=len, reverse=True):
        if re.search(rf"\b{re.escape(keyword)}\b", text_lower):
            return mapping[keyword]
    return None


def _extract_list_field(text_lower: str, value_list: list) -> list:
    return [v for v in value_list
            if re.search(rf"\b{re.escape(v.lower())}\b", text_lower)]


def _extract_amenities_commercial(text_lower: str) -> list:
    """FIX: Use alias map so 'ac', 'wifi', 'lift' etc. match correctly."""
    found = set()
    for kw in sorted(COMMERCIAL_AMENITIES_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(kw)}\b", text_lower):
            found.add(COMMERCIAL_AMENITIES_ALIASES[kw])
    return sorted(found)


# ═══════════════════════════════════════════════════════════════════════════
# PRICE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_price(text: str) -> dict:
    t = text.lower().replace(",", "")
    t = re.sub(r'(\d+(?:\.\d+)?)\s*cr\b', r'\1 crore', t)
    t = re.sub(r'(\d+(?:\.\d+)?)\s*l\b',  r'\1 lakh', t)
    t = re.sub(r'(\d+(?:\.\d+)?)\s*k\b',  r'\1 thousand', t)

    def to_num(val, unit):
        v = float(val)
        u = (unit or "").strip().lower()
        if u == "crore":    return int(v * 10_000_000)
        if u == "lakh":     return int(v * 100_000)
        if u == "thousand": return int(v * 1_000)
        return int(v)

    units = r"(crore|lakh|thousand)"

    rng = re.search(
        rf'(?:between\s*)?(\d+(?:\.\d+)?)\s*{units}\s*(?:to|-|and)\s*(\d+(?:\.\d+)?)\s*{units}', t)
    if rng:
        return {"minPrice": to_num(rng.group(1), rng.group(2)),
                "maxPrice": to_num(rng.group(3), rng.group(4))}

    under = re.search(rf'(?:under|below|less than|upto)\s*(\d+(?:\.\d+)?)\s*{units}', t)
    if under:
        return {"minPrice": 0, "maxPrice": to_num(under.group(1), under.group(2))}

    above = re.search(rf'(?:above|over|more than|minimum)\s*(\d+(?:\.\d+)?)\s*{units}', t)
    if above:
        return {"minPrice": to_num(above.group(1), above.group(2)), "maxPrice": None}

    multi = re.findall(rf'(\d+(?:\.\d+)?)\s*{units}', t)
    if len(multi) >= 2:
        vals = [to_num(v, u) for v, u in multi]
        return {"minPrice": min(vals), "maxPrice": max(vals)}
    if len(multi) == 1:
        return {"minPrice": 0, "maxPrice": to_num(multi[0][0], multi[0][1])}

    return {"minPrice": None, "maxPrice": None}


# ═══════════════════════════════════════════════════════════════════════════
# AREA EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_area(text: str) -> dict:
    t = text.lower()
    for k, v in {"sq ft": "sqft", "sft": "sqft", "sqt": "sqft"}.items():
        t = t.replace(k, v)

    # Range: "between 2000 to 3000 sqft" or "between 2000 and 3000 sqft"
    m = re.search(r'between\s*(\d+)\s*(?:to|-|and)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": int(m.group(1)), "maxArea": int(m.group(2))}

    # Range: "2000 - 3000 sqft" or "2000 to 3000 sqft"
    m = re.search(r'(\d+)\s*(?:-|to)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": int(m.group(1)), "maxArea": int(m.group(2))}

    # Upper bound only: "under 3000 sqft"
    m = re.search(r'(?:under|below|less than)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": None, "maxArea": int(m.group(1))}

    # Lower bound only: "above 2000 sqft"
    m = re.search(r'(?:above|more than|over)\s*(\d+)\s*sqft', t)
    if m: return {"minArea": int(m.group(1)), "maxArea": None}

    # Single value: "3000 sqft" → maxArea only, minArea null
    m = re.search(r'(\d+)\s*sqft', t)
    if m: return {"minArea": None, "maxArea": int(m.group(1))}

    return {"minArea": None, "maxArea": None}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN COMMERCIAL SEARCH FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def commercial_search(text: str) -> dict:
    """
    Parse a natural-language commercial property query.
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

    # ── suitedForList: office or shop suited-for ───────────────────────────
    suited_for = (_extract_map_field(tl, OFFICE_SUITED_FOR_MAP) or
                  _extract_map_field(tl, SHOP_SUITED_FOR_MAP))

    price = _extract_price(text)
    area  = _extract_area(text)

    # Extract raw labels first (needed for smart_query display)
    _prop_type_label   = _extract_map_field(tl, COMMERCIAL_PROPERTY_TYPE_MAP)
    _building_label    = _extract_map_field(tl, BUILDING_TYPE_MAP)
    _furnish_label     = _extract_comm_furnish(tl)
    _office_suit_label = _extract_map_field(tl, OFFICE_SUITED_FOR_MAP)
    _amenity_labels    = _extract_amenities_commercial(tl)
    _status_label      = _extract_map_field(tl, PROPERTY_STATUS_MAP)
    _facing_label      = _extract_map_field(tl, DOOR_FACE_MAP)
    _facilities        = _extract_list_field(tl, COMMERCIAL_FACILITIES)

    result = {
        # Fields in commerical.json → store integer key
        "commercialPropertyTypeList": _label_to_id(_prop_type_label,   _COMM_PROP_ID),
        "buildingTypeList":           _label_to_id(_building_label,     _BUILDING_TYPE_ID),
        "furnishTypeList":            _label_to_id(_furnish_label,      _FURNISH_TYPE_ID),
        "officeSuitedFor":            _label_to_id(_office_suit_label,  _OFFICE_SUITED_ID),
        "suitedForList":              _label_to_id(suited_for,          _OFFICE_SUITED_ID),
        "commercial_AmenitiesList":   _labels_to_ids(_amenity_labels,   _COMM_AMENITIES_ID),
        "propertyStatusList":         _label_to_id(_status_label,       _PROPERTY_STATUS_ID),
        "propertyFacingList":         _label_to_id(_facing_label,       _PROPERTY_FACING_ID),
        # Fields NOT in commerical.json → keep label string as-is
        "FacilitiesList":             _facilities if _facilities else None,
        "commercialListingAsList":    _extract_map_field(tl, COMMERCIAL_LISTING_MAP),
        "imageslist":                 None,
        "lockInPeriodList":           _extract_map_field(tl, LOCK_IN_PERIOD_MAP),
        "plotTypeList":               _extract_map_field(tl, PLOT_TYPE_MAP),
        "plotViewList":               None,
        "propertyAgeList":            _extract_map_field(tl, PROPERTY_AGE_MAP),
        "warehousesuitedfor":         _extract_map_field(tl, WAREHOUSE_SUITED_FOR_MAP),
        # ── locality / city ──
        "locality":                   loc_data.get("locality"),
        "localityId":                 loc_data.get("localityId"),
        "city":                       city_data.get("city"),
        "cityId":                     city_id,
        # ── price / area ──
        "minPrice":                   price.get("minPrice"),
        "maxPrice":                   price.get("maxPrice"),
        "minArea":                    area.get("minArea"),
        "maxArea":                    area.get("maxArea"),
    }

    # ── SMART QUERY ────────────────────────────────────────────────────────
    # smart_query uses original labels (not IDs) for human-readable display
    parts = []
    if _prop_type_label:   parts.append(_prop_type_label)
    if _building_label:    parts.append(f"in {_building_label}")
    if _furnish_label:     parts.append(_furnish_label)
    if _office_suit_label: parts.append(f"for {_office_suit_label}")
    elif suited_for:       parts.append(f"for {suited_for}")
    elif result["warehousesuitedfor"]: parts.append(f"for {result['warehousesuitedfor']}")

    if result["locality"]:
        parts.append(result["locality"] if isinstance(result["locality"], str)
                     else " & ".join(result["locality"]))
    elif result["city"]:
        parts.append(result["city"])

    def fmt(v):
        if v is None: return None
        if v >= 10_000_000: return f"Rs.{v/10_000_000:.2g}Cr"
        if v >= 100_000:    return f"Rs.{v/100_000:.4g}L"
        if v >= 1_000:      return f"Rs.{v/1_000:.4g}k"
        return f"Rs.{v:,}"

    mn, mx = result["minPrice"], result["maxPrice"]
    if mn and mx:   parts.append(f"{fmt(mn)} - {fmt(mx)}")
    elif mx:        parts.append(f"under {fmt(mx)}")
    elif mn:        parts.append(f"above {fmt(mn)}")

    mn_a, mx_a = result["minArea"], result["maxArea"]
    if mn_a and mx_a: parts.append(f"{mn_a:,}-{mx_a:,} sqft")
    elif mn_a:        parts.append(f"above {mn_a:,} sqft")
    elif mx_a:        parts.append(f"under {mx_a:,} sqft")

    if _amenity_labels:
        parts.append("with " + ", ".join(_amenity_labels))
    if _facilities:
        parts.append("+ " + ", ".join(_facilities))

    result["smart_query"] = " | ".join(parts) if parts else text
    result["search_type"] = "commercial"

    return result


# ═══════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    tests = [
        # office space
        "office space in whitefield under 1 crore with ac and conference hall",
        # typo locality
        "furnished coworking space for startup in koramangla with power backup",
        # city typo
        "shop 2000 sqft ready to move east facing for restaurant in banglore",
        # warehouse
        "warehouse for logistics hub above 5000 sqft in bangalore",
        # multiple localities
        "office space in whitefield and hebbal for IT park furnished",
        # price range + amenities
        "commercial plot industrial building 50 lakh to 2 crore",
        # broker listing
        "shop showroom 1000 sqft broker unfurnished north facing",
        # lock in + age
        "office space 12-24 months lock in 1-5 yrs old ready to move",
        # no location (just type + price)
        "coworking space under 50000 with internet connectivity and cctv",
    ]

    print("=" * 70)
    print("COMMERCIAL PIPELINE TEST")
    print("=" * 70)
    for q in tests:
        r = commercial_search(q)
        print(f"\nQ : {q}")
        print(f"  type={r['commercialPropertyTypeList']}  furnish={r['furnishTypeList']}")
        print(f"  locality={r['locality']}  city={r['city']}")
        print(f"  price={r['minPrice']}-{r['maxPrice']}  area={r['minArea']}-{r['maxArea']}")
        print(f"  officeSuitedFor={r['officeSuitedFor']}  suitedFor={r['suitedForList']}")
        print(f"  amenities={r['commercial_AmenitiesList']}  facilities={r['FacilitiesList']}")
        print(f"  smart_query → {r['smart_query']}")