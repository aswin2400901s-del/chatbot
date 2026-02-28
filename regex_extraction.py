#!/usr/bin/env python
# coding: utf-8

import re

# ===============================
# BHK EXTRACTION
# ===============================

def extract_bhk(text):
    """Extract single BHK — used only as a utility; master_pipeline handles multi-BHK."""
    m = re.search(r"(\d+)\s*bhk", text.lower())
    if m:
        bhk = int(m.group(1))
        return {"bhk_numbers": bhk, "bhkId": bhk}
    return {}


# ===============================
# BATHROOM EXTRACTION
# FIX: When multiple BHKs are present (bhk is a list), bathroom count
#      mirrors each BHK value → [2, 3, 4] BHK → [2, 3, 4] bathrooms.
#      If the user explicitly states a bathroom count, that single value
#      is replicated across all BHKs.
# ===============================

def extract_bathroom(text, bhk):
    """
    Extract bathroom count.
    FIX: bhk is now a label string like "2 BHK" or "1 RK" (not a bare int).
         Extract the numeric part for bathroom count.
         1 RK -> 1 bathroom, 2 BHK -> 2 bathrooms, etc.
    """
    import re as _re

    def _bhk_to_num(b):
        """Extract numeric part from "2 BHK", "1 RK", or bare int."""
        if b is None: return None
        m = _re.match(r'(\d+)', str(b).strip())
        return int(m.group(1)) if m else None

    m = re.search(r"(\d+)\s*(bath|bathroom|toilet)s?", text.lower())

    if m:
        explicit = int(m.group(1))
        bath = [explicit] * len(bhk) if isinstance(bhk, list) else explicit
    elif isinstance(bhk, list):
        bath = [_bhk_to_num(b) for b in bhk]
    else:
        bath = _bhk_to_num(bhk)   # "2 BHK" -> 2,  "1 RK" -> 1

    return {
        "bathroom": bath,
        "bathroomId": bath
    }


# ===============================
# AREA TYPE MAP
# ===============================

AREA_TYPE_MAP = {
    "carpet area": "Carpet Area",
    "carpete area": "Carpet Area",
    "carpate area": "Carpet Area",
    "carpet": "Carpet Area",
    "super built up area": "Super Built-up Area",
    "super builtup area": "Super Built-up Area",
    "superbuilt area": "Super Built-up Area",
    "super built": "Super Built-up Area",
    "superbuilt": "Super Built-up Area",
    "sba": "Super Built-up Area"
}


def extract_area_type(text):
    text = text.lower()
    for key, value in AREA_TYPE_MAP.items():
        if key in text:
            return value
    return None


# ===============================
# PRICE EXTRACTION
# FIX: "3 cr and 5 cr" was incorrectly matched as a range.
#      Now only treats it as a range if preceded by clear range keywords
#      (to / - / between). "and" is only a range separator when used with
#      "between X and Y" pattern.
# ===============================

def extract_price(text):
    text = text.lower().replace(",", "").strip()

    # Normalize shorthand units
    text = re.sub(r'(\d+(?:\.\d+)?)\s*l\b', r'\1 lakh', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*lakhs?\b', r'\1 lakh', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*c\b', r'\1 crore', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*cr\b', r'\1 crore', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*k\b', r'\1 k', text)

    def to_number(value, unit):
        value = float(value)
        if unit == "lakh":
            return int(value * 100_000)
        if unit == "crore":
            return int(value * 10_000_000)
        if unit == "k" or unit == "thousand":
            return int(value * 1_000)
        return 0

    # ✅ NEW: Match "40-50 lakh" format first (most common in India)
    compact_range = re.search(
        r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(lakh|crore|k)',
        text
    )
    if compact_range:
        min_val = to_number(compact_range.group(1), compact_range.group(3))
        max_val = to_number(compact_range.group(2), compact_range.group(3))
        return {"minPrice": min(min_val, max_val), "maxPrice": max(min_val, max_val)}

    # FIX: Mixed-unit range — "24k to 50l", "50k to 2cr", "5l to 1cr"
    # Each number can have its own unit (k / lakh / crore), separated by to / -
    _unit = r'(lakh|crore|k)'
    mixed_range = re.search(
        rf'(\d+(?:\.\d+)?)\s*{_unit}\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*{_unit}',
        text
    )
    if mixed_range:
        min_val = to_number(mixed_range.group(1), mixed_range.group(2))
        max_val = to_number(mixed_range.group(3), mixed_range.group(4))
        return {"minPrice": min(min_val, max_val), "maxPrice": max(min_val, max_val)}

    # Range: "between 20 lakh and 50 lakh"
    range_match = re.search(
        r'between\s*(\d+(?:\.\d+)?)\s*(lakh|crore|k)\s*and\s*(\d+(?:\.\d+)?)\s*(lakh|crore|k)',
        text
    )
    if range_match:
        min_val = to_number(range_match.group(1), range_match.group(2))
        max_val = to_number(range_match.group(3), range_match.group(4))
        return {"minPrice": min(min_val, max_val), "maxPrice": max(min_val, max_val)}

    # Range: "20 lakh to 50 lakh" (same-unit, lakh/crore only — kept for legacy)
    range_match = re.search(
        r'(\d+(?:\.\d+)?)\s*(lakh|crore)\s*(?:to|-)\s*(\d+(?:\.\d+)?)\s*(lakh|crore)',
        text
    )
    if range_match:
        min_val = to_number(range_match.group(1), range_match.group(2))
        max_val = to_number(range_match.group(3), range_match.group(4))
        return {"minPrice": min(min_val, max_val), "maxPrice": max(min_val, max_val)}

    # under / below / less than  (supports lakh, crore, AND k)
    # FIX: "under 50l and 20l" → capture BOTH prices as [minPrice, maxPrice]
    #      where minPrice = smaller value, maxPrice = larger value
    # FIX2: Added k/thousand to unit group so "under 20k" is captured
    under_multi = re.findall(
        r'(?:under|below|less than)\s*(\d+(?:\.\d+)?)\s*(lakh|crore|k|thousand)'
        r'(?:\s*(?:and|&|,)\s*(\d+(?:\.\d+)?)\s*(lakh|crore|k|thousand))?',
        text
    )
    if under_multi:
        values = []
        for m in under_multi:
            values.append(to_number(m[0], m[1]))
            if m[2]:  # second price in same "under X and Y" pattern
                values.append(to_number(m[2], m[3]))
        if len(values) >= 2:
            return {"minPrice": min(values), "maxPrice": max(values)}
        return {"minPrice": 0, "maxPrice": values[0]}

    # above / over / more than  (supports lakh, crore, AND k)
    above = re.search(r'(above|over|more than)\s*(\d+(?:\.\d+)?)\s*(lakh|crore|k|thousand)', text)
    if above:
        return {"minPrice": to_number(above.group(2), above.group(3)), "maxPrice": None}

    # MULTIPLE separate prices: "3 cr and 5 cr" → pick the LARGER as maxPrice
    multi_price = re.findall(r'(\d+(?:\.\d+)?)\s*(lakh|crore)', text)
    if len(multi_price) >= 2:
        values = [to_number(v, u) for v, u in multi_price]
        return {"minPrice": min(values), "maxPrice": max(values)}

    # Single price (lakh/crore)
    if len(multi_price) == 1:
        v, u = multi_price[0]
        return {"minPrice": 0, "maxPrice": to_number(v, u)}

    # Single price with k/thousand (only if no lakh/crore found)
    single_k = re.search(r'(\d+(?:\.\d+)?)\s*(k|thousand)', text)
    if single_k:
        return {"minPrice": 0, "maxPrice": to_number(single_k.group(1), single_k.group(2))}

    return {"minPrice": None, "maxPrice": None}


# ===============================
# AREA EXTRACTION
# ===============================

def extract_area(text):
    text = text.lower()

    replacements = {
        "sqt": "sqft",
        "sft": "sqft",
        "sq ft": "sqft",
        "super built area": "sqft",
        "super builtup area": "sqft",
        "super built": "sqft",
        "superbuilt": "sqft",
        "super built-up": "sqft",
        "sba": "sqft",
        "carpet area": "sqft",
        "carpete": "sqft",
        "carpate": "sqft",
        "carpatearea": "sqft"
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    # between 2000 to 2500 sqft
    between_to = re.search(r'between\s*(\d+)\s*(?:to|-)\s*(\d+)\s*sqft', text)
    if between_to:
        return {"minArea": int(between_to.group(1)), "maxArea": int(between_to.group(2))}

    # 2000 or 2500 sqft
    or_match = re.search(r'(\d+)\s*(?:or|-|/)\s*(\d+)\s*sqft', text)
    if or_match:
        v1, v2 = int(or_match.group(1)), int(or_match.group(2))
        return {"minArea": min(v1, v2), "maxArea": max(v1, v2)}

    # between 2000 and 2500 sqft
    between_and = re.search(r'between\s*(\d+)\s*and\s*(\d+)\s*sqft', text)
    if between_and:
        return {"minArea": int(between_and.group(1)), "maxArea": int(between_and.group(2))}

    # under / below / less than
    under = re.search(r'(under|below|less than)\s*(\d+)\s*sqft', text)
    if under:
        return {"minArea": None, "maxArea": int(under.group(2))}

    # above / more than / over
    above = re.search(r'(above|more than|over)\s*(\d+)\s*sqft', text)
    if above:
        return {"minArea": int(above.group(2)), "maxArea": None}

    # single value
    single = re.search(r'(\d+)\s*sqft', text)
    if single:
        val = int(single.group(1))
        return {"minArea": val, "maxArea": val}

    return {"minArea": None, "maxArea": None}