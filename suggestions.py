#!/usr/bin/env python
# coding: utf-8

"""
suggestions.py — 3-Layer AI Property Search Suggestion Engine
==============================================================

Role: You are an AI property search suggestion engine.
      Your job is to generate structured search suggestions (NOT listings).

Layer Architecture
------------------
  Layer 1 — Direct Intent Suggestions  (slots 0-2)
      Mirror exactly what the user asked, only varying one concrete dimension
      (price bracket, same locality).  High confidence, zero drift from intent.

  Layer 2 — Popular Variations  (slots 3-5)
      CTR-ranked alternatives: nearby localities the majority of users click on
      for this property type + price band.  Anchors BHK/type, varies location.

  Layer 3 — Semantic Suggestions  (slots 6-7)
      Go beyond the literal query.  Infer unstated needs from context:
      add lifestyle amenity, upgrade furnishing, suggest complementary property
      types, surface "ready to move" when timing signals detected, etc.

Output contract (UNCHANGED from original)
-----------------------------------------
  buy_suggestions()        → same output keys as before
  rental_suggestions()     → same output keys as before
  pg_suggestions()         → same output keys as before
  commercial_suggestions() → same output keys as before

All slot dicts carry exactly the same ID fields they always did.
Only the "value" label text and the slot-filling logic change.
"""

import os
import re
import json
import pandas as pd

# ── Load JSON config files ──────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))

def _load(f):
    p = os.path.join(_BASE, f)
    return json.load(open(p)) if os.path.exists(p) else {}

_RENT = _load("rent.json")
_PG   = _load("pg.json")
_COMM = _load("commerical.json")

# ── Locality map from CSV ────────────────────────────────────────────────────
_CSV = os.environ.get("HOMES247_CSV",
       os.path.join(_BASE, "buy_searchproperty_new 2(Sheet1).csv"))
_df  = pd.read_csv(_CSV)
_JUNK = {"thhhhhhh","tttt","revrbrbewreb","njking","snr","edfdsdf",
         "harihara","tipturu","nittvali","ebre","konanakutie"}
_LOCALITY_ID = {
    r["locality"].strip(): int(r["localityId"])
    for _, r in _df[["locality","localityId"]].dropna().drop_duplicates().iterrows()
    if r["locality"].strip().lower() not in _JUNK and len(r["locality"].strip()) > 2
}
_ALL_LOCALITIES = list(_LOCALITY_ID.keys())

# City name -> cityId  (from CSV)
_CITY_ID = {
    str(r["city"]).strip(): int(r["cityId"])
    for _, r in _df[["city","cityId"]].dropna().drop_duplicates().iterrows()
}

def _city_id_lookup(city_val, result_cityid=None):
    if result_cityid is not None:
        try: return int(result_cityid)
        except (TypeError, ValueError): pass
    if not city_val: return None
    city = city_val[0] if isinstance(city_val, list) else city_val
    v = _CITY_ID.get(str(city).strip())
    return int(v) if v is not None else None

# ── CTR-ranked top localities  (Layer 2 pool — ordered by click popularity) ─
# Ordered so that the most-clicked neighbourhood comes first per intent type.
_TOP_LOCS = [
    "Whitefield","Koramangala","HSR Layout","Indiranagar",
    "Marathahalli","Electronic City","Hebbal","Sarjapur Road",
    "JP Nagar","Bellandur","Bannerghatta Road","Yelahanka",
]

# ── BUY BHK ID map ───────────────────────────────────────────────────────────
_bhk_id_df = _df[["bhk_numbers","bhkId"]].dropna().drop_duplicates()
_BUY_BHK_ID = {
    str(r["bhk_numbers"]).strip().upper(): int(r["bhkId"])
    for _, r in _bhk_id_df.iterrows()
}

def _buy_bhk_id(label) -> int | None:
    if label is None: return None
    key = str(label).replace(" ", "").upper()
    return _BUY_BHK_ID.get(key)

# ── BUY Property Type ID map ─────────────────────────────────────────────────
_BUY_PROP_ID = {
    str(r["propertyType_name"]).strip().lower(): int(r["propertyType_id"])
    for _, r in _df[["propertyType_name","propertyType_id"]].dropna().drop_duplicates().iterrows()
}
_BUY_PROP_ID["flat"] = _BUY_PROP_ID.get("apartment", next(iter(_BUY_PROP_ID.values()), None))

def _buy_prop_id(name) -> int | None:
    if name is None: return None
    return _BUY_PROP_ID.get(str(name).strip().lower())

# ── BUY Amenities ID map ─────────────────────────────────────────────────────
_BUY_AMEN_ID = {
    str(r["amenities_name"]).strip().lower(): int(r["amenities_id"])
    for _, r in _df[["amenities_name","amenities_id"]].dropna().drop_duplicates().iterrows()
}

def _buy_amen_ids(amen_list) -> list | None:
    if not amen_list: return None
    out = [_BUY_AMEN_ID[a.strip().lower()] for a in amen_list if a.strip().lower() in _BUY_AMEN_ID]
    return out if out else None

# ════════════════════════════════════════════════════════════════════════════
# ID LOOKUP TABLES — from JSON files
# ════════════════════════════════════════════════════════════════════════════

_RENT_BHK    = {x["bhk"].strip().upper(): int(x["id"])           for x in _RENT.get("Bhks", [])}
_RENT_FUR    = {x["furnish"].strip().lower(): int(x["id"])       for x in _RENT.get("Furnish", [])}
_RENT_TEN    = {x["tenants"].strip().lower(): int(x["id"])       for x in _RENT.get("Tenants", [])}
_RENT_PROP   = {x["propertytype"].strip().lower(): int(x["id"])  for x in _RENT.get("Propertytype", [])}
_RENT_PROP["flat"] = _RENT_PROP.get("apartment", next(iter(_RENT_PROP.values()), None))
_RENT_AMEN   = {x["amenities"].strip().lower(): int(x["id"])     for x in _RENT.get("Amenities", [])}
_RENT_DOOR   = {x["doorface"].strip().lower(): int(x["id"])      for x in _RENT.get("Doorface", [])}
_RENT_NEARBY = {x["nearby"].strip().lower(): int(x["id"])        for x in _RENT.get("Nearby", [])}
_RENT_BATH   = {x["bathroom"].strip(): int(x["id"])              for x in _RENT.get("Bathroom", [])}

_PG_AVAIL  = {x["label"].strip().lower(): int(x["key"])   for x in _PG.get("pgAvailableForList", [])}
_PG_SUIT   = {x["label"].strip().lower(): int(x["key"])   for x in _PG.get("pgBestSuitForList", [])}
_PG_ROOM   = {x["label"].strip().lower(): int(x["value"]) for x in _PG.get("roomTypes", [])}
_PG_AMEN   = {x["label"].strip().lower(): int(x["key"])   for x in _PG.get("pg_AmenitiesList", [])}
_PG_SVC    = {x["label"].strip().lower(): int(x["key"])   for x in _PG.get("pgServiceList", [])}
_PG_FAC    = {x["label"].strip().lower(): int(x["key"])   for x in _PG.get("pgFacilitiesList", [])}
_PG_MEAL   = {x["label"].strip().lower(): int(x["key"])   for x in _PG.get("meels", [])}

_COMM_PROP   = {x["label"].strip().lower(): int(x["key"]) for x in _COMM.get("commercialPropertyTypeList", [])}
_COMM_BUILD  = {x["label"].strip().lower(): int(x["key"]) for x in _COMM.get("buildingTypeList", [])}
_COMM_FUR    = {x["label"].strip().lower(): int(x["key"]) for x in _COMM.get("furnishTypeList", [])}
_COMM_OFFICE = {x["label"].strip().lower(): int(x["key"]) for x in _COMM.get("officeSuitedFor", [])}
_COMM_AMEN   = {x["label"].strip().lower(): int(x["key"]) for x in _COMM.get("commercial_AmenitiesList", [])}
_COMM_STATUS = {x["label"].strip().lower(): int(x["key"]) for x in _COMM.get("propertyStatusList", [])}
_COMM_FACE   = {x["label"].strip().lower(): int(x["key"]) for x in _COMM.get("propertyFacingList", [])}

_COMM_PROP_ID2LABEL   = {int(x["key"]): x["label"] for x in _COMM.get("commercialPropertyTypeList", [])}
_COMM_FUR_ID2LABEL    = {int(x["key"]): x["label"] for x in _COMM.get("furnishTypeList", [])}
_COMM_OFFICE_ID2LABEL = {int(x["key"]): x["label"] for x in _COMM.get("officeSuitedFor", [])}
_COMM_AMEN_ID2LABEL   = {int(x["key"]): x["label"] for x in _COMM.get("commercial_AmenitiesList", [])}
_COMM_STATUS_ID2LABEL = {int(x["key"]): x["label"] for x in _COMM.get("propertyStatusList", [])}
_COMM_FACE_ID2LABEL   = {int(x["key"]): x["label"] for x in _COMM.get("propertyFacingList", [])}

def _comm_id_to_label(val, id2label_map):
    if val is None: return None
    if isinstance(val, int): return id2label_map.get(val)
    if isinstance(val, list): return id2label_map.get(val[0]) if val else None
    return val

def _comm_ids_to_labels(val, id2label_map):
    if val is None: return []
    if isinstance(val, list): return [id2label_map[v] for v in val if v in id2label_map]
    if isinstance(val, int):
        lbl = id2label_map.get(val); return [lbl] if lbl else []
    return [val] if val else []


# ════════════════════════════════════════════════════════════════════════════
# QUERY PARSER  — unchanged from original
# ════════════════════════════════════════════════════════════════════════════

def _parse_query(query: str) -> dict:
    q = query.lower().strip()
    _is_rent_or_pg = bool(re.search(r'\b(rent|rental|lease|pg|hostel|paying guest|per month|\/month|pm)\b', q))
    _is_buy        = not _is_rent_or_pg
    _has_k_amount  = bool(re.search(r'\d+\s*k\b', q))
    _has_lac_crore = bool(re.search(r'\d+\s*(lakh|l\b|crore|cr\b|lac)', q))
    return {
        "mentioned_bhk":       bool(re.search(r'\d+\s*(?:bhk|b[\s\.]*h[\s\.]*k|rk|r[\s\.]*k)', q, re.IGNORECASE)),
        "mentioned_locality":  bool(re.search(r'\b(in|near|at)\b\s+\w+', q) or
                                    any(loc.lower() in q for loc in _ALL_LOCALITIES[:200])),
        "mentioned_price":     bool(_has_lac_crore and not _is_rent_or_pg) or bool(_has_k_amount and _is_buy),
        "mentioned_rent":      bool(_has_k_amount and _is_rent_or_pg) or bool(_has_lac_crore and _is_rent_or_pg),
        "mentioned_area":      bool(re.search(r'\d+\s*(sqft|sft|sq\.?ft|square feet|sqt)', q)),
        "mentioned_proptype":  bool(re.search(
            r'\b(apartment|flat|villa|plot|independent house|house|bungalow|'
            r'office|shop|showroom|warehouse|coworking|co-working|pg|hostel)\b', q)),
        "mentioned_furnishing":bool(re.search(r'\b(furnished|semi.?furnished|unfurnished)\b', q)),
        "mentioned_tenant":    bool(re.search(r'\b(family|bachelor|ladies|anyone|working professional)\b', q)),
        "mentioned_amenity":   bool(re.search(
            r'\b(gym|pool|swimming|parking|garden|club|cctv|wifi|wi.fi|'
            r'elevator|lift|power backup|jogging|tennis|badminton)\b', q)),
        "mentioned_gender":    bool(re.search(r'\b(boys?|girls?|male|female|co.?living|unisex)\b', q)),
        "mentioned_sharing":   bool(re.search(
            r'\b(single|private|double|two sharing|three sharing|four sharing|triple|sharing)\b', q)),
        "mentioned_occupant":  bool(re.search(
            r'\b(student|working professional|professional|executive)\b', q)),
        "mentioned_comm_type": bool(re.search(
            r'\b(office|shop|showroom|warehouse|coworking|co.?working|plot)\b', q)),
        "mentioned_facing":    bool(re.search(r'\b(east|west|north|south)\s*facing\b', q)),
        # Layer 3 semantic signals
        "urgency":             bool(re.search(r'\b(asap|urgent(ly)?|immediately|right away|ready to move|ready-to-move|immediate)\b', q)),
        "family_signal":       bool(re.search(r'\b(family|kids?|children|school|safe|gated)\b', q)),
        "investment_signal":   bool(re.search(r'\b(invest|investment|returns?|roi|resale|rental income)\b', q)),
        "luxury_signal":       bool(re.search(r'\b(luxury|premium|high.?end|spacious|elite|exclusive)\b', q)),
        "budget_signal":       bool(re.search(r'\b(cheap|affordable|budget|economical|low cost|pocket.?friendly)\b', q)),
        "wfh_signal":          bool(re.search(r'\b(work from home|wfh|home office|study room)\b', q)),
    }


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _fmt(v: int) -> str:
    if v >= 10_000_000: return f"{v/10_000_000:g} crore"
    if v >= 100_000:    return f"{v/100_000:g} lakh"
    return f"{v:,}"

def _step_up(v, steps):
    a = [s for s in steps if s > v]; return a[0] if a else None

def _step_down(v, steps):
    b = [s for s in steps if s < v]; return b[-1] if b else None

def _alt_locs(used, n=4):
    if isinstance(used, str): used = [used]
    s = {l.lower() for l in (used or [])}
    return [l for l in _TOP_LOCS if l.lower() not in s][:n]

def _loc_id(name):
    if not name: return None
    if isinstance(name, list): name = name[0]
    return _LOCALITY_ID.get(name)

def _bhk_str(bhk) -> str:
    if bhk is None: return ""
    import re as _re
    def _fmt_one(b):
        s = str(b).strip()
        if _re.search(r'\bRK\b', s, _re.IGNORECASE):
            num = _re.match(r'(\d+)', s); return f"{num.group(1)}RK" if num else "1RK"
        cleaned = s.replace(" BHK","").replace(" RK","").strip()
        try: return f"{int(cleaned)}BHK"
        except ValueError: return f"{cleaned}BHK"
    if isinstance(bhk, list):
        labels = list(dict.fromkeys(_fmt_one(b) for b in bhk))
        return ", ".join(labels)
    return _fmt_one(bhk)

def _single(bhk):
    return (bhk[0] if bhk else None) if isinstance(bhk, list) else bhk

def _join(*parts) -> str:
    return " ".join(p for p in parts if p and str(p).strip())

def _fmt_price_natural(v) -> str:
    if v is None: return ""
    if v >= 10_000_000: return f"₹{v/10_000_000:g} Cr"
    if v >= 100_000:    return f"₹{v/100_000:g}L"
    return f"₹{v:,}"

def _bhk_natural(bhk) -> str:
    if bhk is None: return ""
    import re as _re
    def _one(b):
        s = str(b).strip()
        if _re.search(r'\bRK\b', s, _re.IGNORECASE):
            num = _re.match(r'(\d+)', s); return f"{num.group(1)} RK" if num else "1 RK"
        num = _re.match(r'(\d+)', s); return f"{num.group(1)} BHK" if num else s
    if isinstance(bhk, list):
        unique = list(dict.fromkeys(_one(b) for b in bhk)); return " & ".join(unique)
    return _one(bhk)

def _bhk_step_up(bhk):
    """Return the next BHK up e.g. '2 BHK' → '3 BHK'."""
    if bhk is None: return None
    import re as _re
    b = _single(bhk); s = str(b).strip()
    if _re.search(r'\bRK\b', s, _re.IGNORECASE): return "1 BHK"
    m = _re.match(r'(\d+)', s)
    if m:
        n = int(m.group(1))
        return f"{n+1} BHK" if n < 5 else None
    return None

def _bhk_step_down(bhk):
    """Return the next BHK down e.g. '3 BHK' → '2 BHK'."""
    if bhk is None: return None
    import re as _re
    b = _single(bhk); s = str(b).strip()
    if _re.search(r'\bRK\b', s, _re.IGNORECASE): return None
    m = _re.match(r'(\d+)', s)
    if m:
        n = int(m.group(1))
        if n == 1: return "1 RK"
        return f"{n-1} BHK" if n > 1 else None
    return None


# ════════════════════════════════════════════════════════════════════════════
# VALUE BUILDERS  (unchanged from original — keeps label wording consistent)
# ════════════════════════════════════════════════════════════════════════════

def _buy_value(bhk, prop, loc, max_p, min_p=None, amenity=None, intent=None) -> str:
    b = _bhk_natural(bhk); p = prop or "property"
    l = f"in {loc}" if loc else ""
    price = _fmt_price_natural(max_p); pr_s = f"under {price}" if price else ""
    if intent == "up":     return _join(b, p, l, f"— expand budget to {price}")
    if intent == "down":   return _join(b, p, l, f"— tighten budget to {price}")
    if intent == "amen" and amenity: return _join(b, p, l, f"with {amenity}", pr_s)
    if intent == "bhk_up": return _join(f"More space? Try {b}", p, l, pr_s)
    if intent == "bhk_dn": return _join(f"Compact option: {b}", p, l, pr_s)
    if intent == "prop":   return _join(b, p, l, pr_s)
    if intent == "rtm":    return _join(b, p, l, "— Ready to Move", pr_s)
    if intent == "invest": return _join(b, p, l, pr_s, "— Good Investment")
    return _join(b, p, l, pr_s)

def _rent_value(bhk, furnish, prop, tenant, loc, max_rent, amenity=None, intent=None) -> str:
    b = _bhk_natural(bhk); f = furnish or ""; p = prop or "flat"
    t = f"for {tenant}" if tenant else ""
    l = f"in {loc}" if loc else ""
    rent = _fmt_price_natural(max_rent); r_s = f"under {rent}/mo" if rent else ""
    if intent == "up":     return _join(b, l, f"— stretch rent to {rent}/mo")
    if intent == "down":   return _join(b, l, f"— affordable at {rent}/mo")
    if intent == "amen" and amenity: return _join(b, f, p, "for rent", t, l, f"with {amenity}")
    if intent == "fur":    return _join(b, f, p, "for rent", t, l, r_s)
    if intent == "ten":    return _join(b, f, p, "for rent", t, l, r_s)
    if intent == "bhk_up": return _join(f"More room: {b}", p, "for rent", t, l, r_s)
    if intent == "bhk_dn": return _join(f"Budget pick: {b}", p, "for rent", t, l, r_s)
    if intent == "prop":   return _join(b, f, p, "for rent", t, l, r_s)
    if intent == "rtm":    return _join(b, f, p, "for rent", t, l, r_s, "— Ready to Move")
    return _join(b, f, p, "for rent", t, l, r_s)

def _pg_value(pg_type, occupant, loc, max_rent, sharing=None, amenity=None,
              service=None, intent=None) -> str:
    pg  = pg_type or "PG"; occ = f"for {occupant}" if occupant else ""
    l   = f"near {loc}" if loc else ""
    rent= _fmt_price_natural(max_rent); r_s = f"under {rent}/mo" if rent else ""
    sh  = f"— {sharing}" if sharing else ""
    if intent == "up":      return _join(pg, occ, l, f"— up to {rent}/mo")
    if intent == "down":    return _join(pg, occ, l, f"— budget {rent}/mo")
    if intent == "amen" and amenity: return _join(pg, f"with {amenity}", occ, l, r_s)
    if intent == "svc" and service:  return _join(pg, f"with {service}", occ, l, r_s)
    if intent == "gender":  return _join(pg, occ, l, r_s)
    if intent == "sharing" and sharing: return _join(pg, sh, occ, l, r_s)
    if intent == "occ":     return _join(pg, occ, l, r_s)
    return _join(pg, sh, occ, l, r_s)

def _comm_value(prop, loc, area, max_p, amenity=None, furnish=None,
                status=None, intent=None) -> str:
    p = prop or "Commercial Space"; l = f"in {loc}" if loc else ""
    a_s = f"{area:,} sqft" if area else ""
    price= _fmt_price_natural(max_p); pr_s = f"under {price}" if price else ""
    if intent == "up":     return _join(p, l, f"— increase budget to {price}")
    if intent == "down":   return _join(p, l, f"— under {price}")
    if intent == "amen" and amenity: return _join(p, f"with {amenity}", l, a_s, pr_s)
    if intent == "area_u": return _join(p, f"— larger {a_s}", l, pr_s)
    if intent == "area_d": return _join(p, f"— compact {a_s}", l, pr_s)
    if intent == "prop":   return _join(p, l, a_s, pr_s)
    if intent == "fur" and furnish: return _join(furnish, p, l, a_s, pr_s)
    if intent == "rtm":    return _join(p, "— Ready to Move", l, a_s, pr_s)
    return _join(p, l, a_s, pr_s)


# ════════════════════════════════════════════════════════════════════════════
# ID HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _id_lookup(table: dict, label) -> list | None:
    if label is None: return None
    labels = label if isinstance(label, list) else [label]
    out = []
    for lbl in labels:
        v = table.get(str(lbl).strip().lower())
        if v is not None: out.append(v)
    return out if out else None

def _id_multi(table: dict, *labels) -> list | None:
    out = []
    for lbl in labels:
        if lbl is None: continue
        lst = lbl if isinstance(lbl, list) else [lbl]
        for l in lst:
            v = table.get(str(l).strip().lower())
            if v is not None: out.append(v)
    return out if out else None

def _rent_bhk_ids(bhk) -> list | None:
    if bhk is None: return None
    vals = bhk if isinstance(bhk, list) else [bhk]
    out = []
    for b in vals:
        s = str(b).strip().upper()
        v = _RENT_BHK.get(s)
        if v is None:
            import re as _re
            m = _re.match(r'(\d+)', s)
            if m:
                n = m.group(1)
                v = _RENT_BHK.get(f"{n} BHK") or _RENT_BHK.get(f"{n} RK")
        if v is not None: out.append(v)
    return out if out else None

def _to_indexed(lst: list) -> dict:
    return {str(i): item for i, item in enumerate(lst)}

def _dedupe(lst, limit=8) -> list:
    seen, out = set(), []
    for item in lst:
        k = item.get("value","").strip()
        if k and k not in seen:
            seen.add(k); out.append(item)
        if len(out) == limit: break
    return out

# Price step tables
_BUY_STEPS  = [2_000_000,3_000_000,4_000_000,5_000_000,7_500_000,
               10_000_000,15_000_000,20_000_000,30_000_000,50_000_000]
_RENT_STEPS = [8_000,10_000,12_000,15_000,18_000,20_000,
               25_000,30_000,35_000,40_000,50_000]
_PG_STEPS   = [4_000,5_000,6_000,7_000,8_000,10_000,12_000,15_000]
_COMM_STEPS = [2_000_000,5_000_000,10_000_000,20_000_000,50_000_000]
_AREA_STEPS = [500,750,1000,1200,1500,2000,2500,3000]


# ════════════════════════════════════════════════════════════════════════════
# LAYER 3 SEMANTIC INFERENCE HELPERS
# These pick the best semantic expansion based on query signals.
# ════════════════════════════════════════════════════════════════════════════

# Lifestyle amenities ranked by conversion rate per property type
_L3_BUY_AMENITIES    = ["Swimming Pool", "Gym", "Club House", "Power Backup", "Car Parking"]
_L3_RENT_AMENITIES   = ["Gym", "Swimming Pool", "Car Parking", "Power Backup", "Wifi"]
_L3_PG_AMENITIES     = ["Wi-Fi Connection", "Gym", "Power Backup", "TV", "CCTV"]
_L3_COMM_AMENITIES   = ["Air Conditioner", "Power Backup", "Internet Connectivity", "CCTV", "Elevator"]

# Semantic prop-type expansion: if user said "apartment", also show villa, independent house
_BUY_PROP_EXPAND = {
    "Apartment":        ["Villa", "Independent House"],
    "Independent House":["Villa", "Apartment"],
    "Villa":            ["Independent House", "Apartment"],
    "Plot":             ["Apartment"],
}
_RENT_PROP_EXPAND = {
    "Apartment":        ["Villa", "Independent House"],
    "Independent House":["Apartment"],
    "Villa":            ["Apartment"],
}

def _pick_semantic_amenity(used_set: set, pool: list) -> str | None:
    """Pick the highest-ranked amenity not already in the user's query."""
    for am in pool:
        if am.lower() not in used_set:
            return am
    return None

def _semantic_label_buy(m: dict, bhk, prop_s: str, anchor_loc: str,
                         max_p, amenities: list) -> list:
    """
    Layer 3 semantic slots for BUY.
    Returns 0–2 suggestion dicts using contextual signals.
    """
    slots = []
    used_amen = {a.lower() for a in amenities}

    if m["urgency"]:
        # Signal: user needs to move fast → Ready to Move suggestion
        slots.append(("rtm", None, anchor_loc, max_p, prop_s, amenities))
    elif m["investment_signal"]:
        # Signal: investor mindset → surface investment-value label
        slots.append(("invest", bhk, anchor_loc, max_p, prop_s, amenities))
    elif m["luxury_signal"]:
        # Signal: luxury intent → push premium amenity + step-up price
        am = _pick_semantic_amenity(used_amen, _L3_BUY_AMENITIES)
        if am:
            slots.append(("amen", bhk, anchor_loc, max_p, prop_s, amenities + [am]))
    elif m["family_signal"]:
        # Signal: family buyer → suggest gated community / club house amenity
        fam_amen = next((a for a in ["Club House", "Swimming Pool", "Gym"]
                         if a.lower() not in used_amen), None)
        if fam_amen:
            slots.append(("amen", bhk, anchor_loc, max_p, prop_s, amenities + [fam_amen]))
    else:
        # Default semantic: suggest a popular amenity
        am = _pick_semantic_amenity(used_amen, _L3_BUY_AMENITIES)
        if am:
            slots.append(("amen", bhk, anchor_loc, max_p, prop_s, amenities + [am]))

    # Second semantic slot: alternate property type OR bhk step
    prop_alts = _BUY_PROP_EXPAND.get(prop_s, [])
    if prop_alts:
        slots.append(("prop", bhk, anchor_loc, max_p, prop_alts[0], amenities))
    elif not m["mentioned_bhk"]:
        # no BHK stated → suggest the most popular BHK (2 BHK)
        slots.append(("loc", "2 BHK", anchor_loc, max_p, prop_s, amenities))

    return slots[:2]   # cap at 2


def _semantic_label_rent(m: dict, bhk, furnish, prop_s: str,
                          tenant, anchor_loc: str, max_rent, amenities: list) -> list:
    slots = []
    used_amen = {a.lower() for a in amenities}

    if m["urgency"]:
        slots.append(("rtm", bhk, furnish, prop_s, tenant, anchor_loc, max_rent, amenities))
    elif m["family_signal"] and not m["mentioned_tenant"]:
        # Infer family tenant from query context
        slots.append(("ten", bhk, furnish, prop_s, "Family", anchor_loc, max_rent, amenities))
    elif m["wfh_signal"]:
        # WFH signal → surface furnished + wifi combo
        wfh_fur = "Furnished" if not furnish else furnish
        am = next((a for a in ["Wifi", "Power Backup"] if a.lower() not in used_amen), None)
        new_amen = amenities + [am] if am else amenities
        slots.append(("fur", bhk, wfh_fur, prop_s, tenant, anchor_loc, max_rent, new_amen))
    elif m["budget_signal"] and not m["mentioned_furnishing"]:
        # Budget signal → suggest unfurnished to save cost
        slots.append(("fur", bhk, "Unfurnished", prop_s, tenant, anchor_loc, max_rent, amenities))
    else:
        am = _pick_semantic_amenity(used_amen, _L3_RENT_AMENITIES)
        if am:
            slots.append(("amen", bhk, furnish, prop_s, tenant, anchor_loc, max_rent, amenities + [am]))

    # Second semantic slot
    prop_alts = _RENT_PROP_EXPAND.get(prop_s, [])
    if prop_alts:
        slots.append(("prop", bhk, furnish, prop_alts[0], tenant, anchor_loc, max_rent, amenities))
    elif m["mentioned_bhk"]:
        # suggest sibling BHK
        up = _bhk_step_up(bhk)
        if up:
            slots.append(("bhk_up", up, furnish, prop_s, tenant, anchor_loc, max_rent, amenities))

    return slots[:2]


def _semantic_label_pg(m: dict, pg_s: str, occupant, anchor_loc: str,
                        max_rent, sharing, amenities: list, services: list) -> list:
    slots = []
    used_amen = {a.lower() for a in amenities}

    if m["budget_signal"] and not sharing:
        # Budget → suggest three-sharing to cut cost
        slots.append(("sharing", pg_s, occupant, anchor_loc, max_rent, "Three Sharing", amenities, services))
    elif m["luxury_signal"] and not sharing:
        # Luxury → suggest private room
        slots.append(("sharing", pg_s, occupant, anchor_loc, max_rent, "Private Room", amenities, services))
    elif m["urgency"]:
        # Urgency → surface a nearby locality variation quickly
        alts = _alt_locs([anchor_loc])
        if alts:
            slots.append(("loc", pg_s, occupant, alts[0], max_rent, sharing, amenities, services))
    else:
        am = _pick_semantic_amenity(used_amen, _L3_PG_AMENITIES)
        if am:
            slots.append(("amen", pg_s, occupant, anchor_loc, max_rent, sharing, [am], services))

    # Second semantic slot: occupant type if not stated
    if not m["mentioned_occupant"] and len(slots) < 2:
        occ_sug = "Working Professionals" if not occupant else None
        if occ_sug:
            slots.append(("occ", pg_s, occ_sug, anchor_loc, max_rent, sharing, amenities, services))

    return slots[:2]


def _semantic_label_comm(m: dict, prop_s: str, anchor_loc: str,
                          max_p, area, amenities: list,
                          furnish, status) -> list:
    slots = []
    used_amen = {a.lower() for a in amenities}

    if m["urgency"]:
        slots.append(("rtm", prop_s, anchor_loc, area, max_p, amenities, furnish))
    elif m["budget_signal"] and not furnish:
        slots.append(("fur", prop_s, anchor_loc, area, max_p, amenities, "Unfurnish"))
    elif m["luxury_signal"]:
        am = _pick_semantic_amenity(used_amen, _L3_COMM_AMENITIES)
        if am:
            slots.append(("amen", prop_s, anchor_loc, area, max_p, amenities + [am], furnish))
    else:
        am = _pick_semantic_amenity(used_amen, _L3_COMM_AMENITIES)
        if am:
            slots.append(("amen", prop_s, anchor_loc, area, max_p, amenities + [am], furnish))

    # Second: area variation if area given
    if area and len(slots) < 2:
        larger = next((s for s in _AREA_STEPS if s > area), None)
        if larger:
            slots.append(("area_u", prop_s, anchor_loc, larger, max_p, amenities, furnish))

    return slots[:2]


# ════════════════════════════════════════════════════════════════════════════
# BUY SUGGESTIONS
# ════════════════════════════════════════════════════════════════════════════

def buy_suggestions(result: dict, query: str = "") -> dict:
    """
    Layer 1 — Direct Intent  (slots 0-2)
        Exact user parameters, only price varies (current / step-up / step-down).
    Layer 2 — Popular Variations CTR-ranked  (slots 3-5)
        Same BHK + prop type, 3 highest-traffic alternative localities.
    Layer 3 — Semantic Suggestions  (slots 6-7)
        Contextual expansion: amenity, property type alt, urgency (RTM),
        investment signal, family lifestyle, BHK step.
    """
    m         = _parse_query(query)
    bhk       = result.get("bhk_numbers")
    locality  = result.get("locality")
    city      = result.get("city")
    city_id   = result.get("cityId")
    max_p     = result.get("maxPrice")
    min_p     = result.get("minPrice")
    prop      = result.get("propertyType_name")
    amenities = result.get("amenities_name") or []

    prop_s        = (prop[0] if isinstance(prop, list) else prop) or "flat"
    loc_val       = locality or city
    is_city_match = (locality is None and city is not None)
    user_loc      = loc_val[0] if isinstance(loc_val, list) else loc_val
    anchor_loc    = user_loc if not is_city_match else _TOP_LOCS[0]

    _NOAMEN = object()

    def _make(value, bhk_=None, loc_=None, mp_=None, prop_=None, amen_=_NOAMEN):
        b  = bhk_  if bhk_  is not None else bhk
        l  = loc_  if loc_  is not None else anchor_loc
        mp = mp_   if mp_   is not None else max_p
        pt = prop_ if prop_ is not None else prop_s
        am = None if amen_ is _NOAMEN else (amen_ if amen_ else None)
        bid = _buy_bhk_id(b) if isinstance(b, str) else b
        out = {
            "value":           value,
            "bhkId":           bid,
            "propertyType_id": _buy_prop_id(pt),
            "localityId":      _loc_id(l),
            "cityId":          _city_id_lookup(city, city_id),
            "minPrice":        min_p,
            "maxPrice":        mp,
        }
        if am is not None:
            out["amenities_id"] = _buy_amen_ids(am)
        return out

    raw = []
    _price_steps = _RENT_STEPS if (max_p and max_p < 200_000) else _BUY_STEPS

    # ── LAYER 1: Direct Intent — same locality, vary price ───────────────────
    if max_p:
        raw.append(_make(_buy_value(bhk, prop_s, anchor_loc, max_p, intent="loc"),
                         loc_=anchor_loc, mp_=max_p))
        u = _step_up(max_p, _price_steps)
        if u:
            raw.append(_make(_buy_value(bhk, prop_s, anchor_loc, u, intent="up"),
                             loc_=anchor_loc, mp_=u))
        d = _step_down(max_p, _price_steps)
        if d:
            raw.append(_make(_buy_value(bhk, prop_s, anchor_loc, d, intent="down"),
                             loc_=anchor_loc, mp_=d))
    else:
        # No price stated → show 3 popular price brackets (direct intent fallback)
        for step in [5_000_000, 10_000_000, 15_000_000]:
            raw.append(_make(_buy_value(bhk, prop_s, anchor_loc, step, intent="loc"),
                             loc_=anchor_loc, mp_=step))

    # ── LAYER 2: Popular Variations — CTR-ranked alt localities ─────────────
    exclude_set = {anchor_loc.lower()} if anchor_loc else set()
    alt_locs    = [l for l in _TOP_LOCS if l.lower() not in exclude_set][:3]
    for alt in alt_locs:
        raw.append(_make(_buy_value(bhk, prop_s, alt, max_p, intent="loc"),
                         loc_=alt, mp_=max_p))

    # ── LAYER 3: Semantic Suggestions — context-aware expansion ─────────────
    for intent, b_, l_, mp_, pt_, am_ in _semantic_label_buy(
            m, bhk, prop_s, anchor_loc, max_p, amenities):
        raw.append(_make(
            _buy_value(b_ or bhk, pt_, l_, mp_, intent=intent),
            bhk_=b_, loc_=l_, mp_=mp_, prop_=pt_, amen_=am_))

    return _to_indexed(_dedupe(raw, 8))


# ════════════════════════════════════════════════════════════════════════════
# RENTAL SUGGESTIONS
# ════════════════════════════════════════════════════════════════════════════

def rental_suggestions(result: dict, query: str = "") -> dict:
    """
    Layer 1 — Direct Intent  (slots 0-2): rent range variations, same locality.
    Layer 2 — Popular Variations CTR-ranked  (slots 3-5): top alt localities.
    Layer 3 — Semantic  (slots 6-7): furnishing, tenant type, RTM, WFH, amenity.
    """
    m         = _parse_query(query)
    bhk       = result.get("bhk")
    locality  = result.get("locality")
    city      = result.get("city")
    city_id   = result.get("cityId")
    max_rent  = result.get("maxRent")
    furnish   = result.get("Furnish")
    tenant    = result.get("Tenants")
    prop      = result.get("Propertytype")
    amenities = result.get("Amenities") or []

    prop_s        = (prop[0] if isinstance(prop, list) else prop) or "flat"
    loc_val       = locality or city
    is_city_match = (locality is None and city is not None)
    user_loc      = loc_val[0] if isinstance(loc_val, list) else loc_val
    anchor_loc    = user_loc if not is_city_match else _TOP_LOCS[0]

    _NOAMEN = object()

    def _make(value, bhk_=None, loc_=None, rent_=None,
              fur_=None, ten_=None, prop_=None, amen_=_NOAMEN):
        b  = bhk_  if bhk_  is not None else bhk
        l  = loc_  if loc_  is not None else anchor_loc
        mr = rent_ if rent_ is not None else max_rent
        f  = fur_  if fur_  is not None else furnish
        t  = ten_  if ten_  is not None else tenant
        pt = prop_ if prop_ is not None else prop_s
        am = None if amen_ is _NOAMEN else (amen_ if amen_ else None)
        return {
            "value":        value,
            "Bhks":         _rent_bhk_ids(b),
            "Furnish":      _id_lookup(_RENT_FUR,  f),
            "Tenants":      _id_lookup(_RENT_TEN,  t),
            "Propertytype": _id_lookup(_RENT_PROP, pt),
            "Amenities":    _id_multi(_RENT_AMEN,  *am) if am else None,
            "localityId":   _loc_id(l),
            "cityId":       _city_id_lookup(city, city_id),
            "maxRent":      mr,
        }

    raw = []

    # ── LAYER 1: Direct Intent ───────────────────────────────────────────────
    if max_rent:
        raw.append(_make(_rent_value(bhk, furnish, prop_s, tenant, anchor_loc, max_rent, intent="loc"),
                         loc_=anchor_loc, rent_=max_rent))
        u = _step_up(max_rent, _RENT_STEPS)
        if u:
            raw.append(_make(_rent_value(bhk, furnish, prop_s, tenant, anchor_loc, u, intent="up"),
                             loc_=anchor_loc, rent_=u))
        d = _step_down(max_rent, _RENT_STEPS)
        if d:
            raw.append(_make(_rent_value(bhk, furnish, prop_s, tenant, anchor_loc, d, intent="down"),
                             loc_=anchor_loc, rent_=d))
    else:
        for step in [15_000, 25_000, 35_000]:
            raw.append(_make(_rent_value(bhk, furnish, prop_s, tenant, anchor_loc, step, intent="loc"),
                             loc_=anchor_loc, rent_=step))

    # ── LAYER 2: Popular Variations — CTR-ranked alt localities ─────────────
    exclude_set = {anchor_loc.lower()} if anchor_loc else set()
    alt_locs    = [l for l in _TOP_LOCS if l.lower() not in exclude_set][:3]
    for alt in alt_locs:
        raw.append(_make(_rent_value(bhk, furnish, prop_s, tenant, alt, max_rent, intent="loc"),
                         loc_=alt, rent_=max_rent))

    # ── LAYER 3: Semantic ────────────────────────────────────────────────────
    for sem in _semantic_label_rent(m, bhk, furnish, prop_s, tenant,
                                     anchor_loc, max_rent, amenities):
        intent_r, b_, f_, pt_, t_, l_, mr_, am_ = sem
        raw.append(_make(
            _rent_value(b_, f_, pt_, t_, l_, mr_, intent=intent_r),
            bhk_=b_, loc_=l_, rent_=mr_, fur_=f_, ten_=t_, prop_=pt_,
            amen_=am_ if am_ else _make.__defaults__))

    return _to_indexed(_dedupe(raw, 8))


# ════════════════════════════════════════════════════════════════════════════
# PG SUGGESTIONS
# ════════════════════════════════════════════════════════════════════════════

def pg_suggestions(result: dict, query: str = "") -> dict:
    """
    Layer 1 — Direct Intent  (slots 0-2): rent range, same locality.
    Layer 2 — Popular Variations CTR-ranked  (slots 3-5): alt localities.
    Layer 3 — Semantic  (slots 6-7): sharing type, occupant inference, amenity.
    """
    m         = _parse_query(query)
    locality  = result.get("locality")
    city      = result.get("city")
    city_id   = result.get("cityId")
    max_rent  = result.get("maxRent")

    _PG_AVAIL_ID_TO_LABEL = {1: "Boys", 2: "Girls", 3: "Co-living"}
    _PG_SUIT_ID_TO_LABEL  = {1: "Students", 2: "Working Professionals", 3: "All"}
    _PG_ROOM_ID_TO_LABEL  = {
        1: "Private Room", 2: "Two Sharing", 3: "Three Sharing",
        4: "Four Sharing", 5: "Five Sharing", 6: "Six Sharing", 13: "Others",
    }

    _gender_id   = result.get("pgAvailableForList")
    _occupant_id = result.get("pgBestSuitForList")
    _sharing_id  = result.get("roomTypes")

    gender   = _PG_AVAIL_ID_TO_LABEL.get(_gender_id,  "") if isinstance(_gender_id,  int) else (_gender_id  or "")
    occupant = _PG_SUIT_ID_TO_LABEL.get(_occupant_id, "") if isinstance(_occupant_id, int) else (_occupant_id or "")
    sharing  = _PG_ROOM_ID_TO_LABEL.get(_sharing_id,  "") if isinstance(_sharing_id,  int) else (_sharing_id  or "")
    amenities = result.get("pg_AmenitiesList") or []
    services  = result.get("pgServiceList")    or []
    meels     = result.get("meels")            or []

    loc_val       = locality or city
    is_city_match = (locality is None and city is not None)
    user_loc      = loc_val[0] if isinstance(loc_val, list) else loc_val
    anchor_loc    = user_loc if not is_city_match else _TOP_LOCS[0]

    g = gender.strip().lower()
    if "girl" in g:  pg_s = "Girls PG"
    elif "boy" in g: pg_s = "Boys PG"
    else:            pg_s = "PG"

    def _avail_id(label: str) -> list | None:
        gl = label.strip().lower()
        if "girl"  in gl: key = "girls"
        elif "boy" in gl: key = "boys"
        elif "co"  in gl: key = "co-living"
        else: return None
        v = _PG_AVAIL.get(key); return [v] if v is not None else None

    _NOAMEN = object()

    def _make(value, loc_=None, rent_=None, gender_=None,
              occupant_=None, sharing_=None, amen_=_NOAMEN, svc_=None, meals_=None):
        l   = loc_      if loc_      is not None else anchor_loc
        mr  = rent_     if rent_     is not None else max_rent
        g_  = gender_   if gender_   is not None else gender
        occ = occupant_ if occupant_ is not None else occupant
        sh  = sharing_  if sharing_  is not None else sharing
        am  = None if amen_ is _NOAMEN else (amen_ if amen_ else None)
        sv  = svc_      if svc_      is not None else services
        ml  = meals_    if meals_    is not None else (meels if meels else None)
        return {
            "value":              value,
            "pgAvailableForList": _avail_id(g_ or ""),
            "pgBestSuitForList":  _id_lookup(_PG_SUIT, occ) if occ else None,
            "roomTypes":          _id_lookup(_PG_ROOM, sh)  if sh  else None,
            "pg_AmenitiesList":   _id_multi(_PG_AMEN,  *am) if am  else None,
            "pgServiceList":      _id_multi(_PG_SVC,   *sv) if sv  else None,
            "meels":              ml if ml else None,
            "localityId":         _loc_id(l),
            "cityId":             _city_id_lookup(city, city_id),
            "maxRent":            mr,
        }

    raw = []

    # ── LAYER 1: Direct Intent ───────────────────────────────────────────────
    if max_rent:
        raw.append(_make(_pg_value(pg_s, occupant, anchor_loc, max_rent,
                                   sharing=sharing or None, intent="loc"),
                         loc_=anchor_loc, rent_=max_rent, sharing_=sharing or None))
        u = _step_up(max_rent, _PG_STEPS)
        if u:
            raw.append(_make(_pg_value(pg_s, occupant, anchor_loc, u,
                                       sharing=sharing or None, intent="up"),
                             loc_=anchor_loc, rent_=u, sharing_=sharing or None))
        d = _step_down(max_rent, _PG_STEPS)
        if d:
            raw.append(_make(_pg_value(pg_s, occupant, anchor_loc, d,
                                       sharing=sharing or None, intent="down"),
                             loc_=anchor_loc, rent_=d, sharing_=sharing or None))
    else:
        for step in [6_000, 8_000, 10_000]:
            raw.append(_make(_pg_value(pg_s, occupant, anchor_loc, step,
                                       sharing=sharing or None, intent="loc"),
                             loc_=anchor_loc, rent_=step, sharing_=sharing or None))

    # ── LAYER 2: Popular Variations — CTR-ranked alt localities ─────────────
    exclude_set = {anchor_loc.lower()} if anchor_loc else set()
    alt_locs    = [l for l in _TOP_LOCS if l.lower() not in exclude_set][:3]
    for alt in alt_locs:
        raw.append(_make(_pg_value(pg_s, occupant, alt, max_rent,
                                   sharing=sharing or None, intent="loc"),
                         loc_=alt, rent_=max_rent, sharing_=sharing or None))

    # ── LAYER 3: Semantic ────────────────────────────────────────────────────
    for sem in _semantic_label_pg(m, pg_s, occupant, anchor_loc,
                                   max_rent, sharing, amenities, services):
        intent_p, pg_, occ_, l_, mr_, sh_, am_, sv_ = sem
        raw.append(_make(
            _pg_value(pg_, occ_, l_, mr_, sharing=sh_, intent=intent_p),
            loc_=l_, rent_=mr_, occupant_=occ_, sharing_=sh_,
            amen_=am_ if am_ else _NOAMEN, svc_=sv_))

    return _to_indexed(_dedupe(raw, 8))


# ════════════════════════════════════════════════════════════════════════════
# COMMERCIAL SUGGESTIONS
# ════════════════════════════════════════════════════════════════════════════

def commercial_suggestions(result: dict, query: str = "") -> dict:
    """
    Layer 1 — Direct Intent  (slots 0-2): price range, same locality.
    Layer 2 — Popular Variations CTR-ranked  (slots 3-5): alt localities.
    Layer 3 — Semantic  (slots 6-7): amenity, RTM, area expansion, furnishing.
    """
    m         = _parse_query(query)
    locality  = result.get("locality")
    city      = result.get("city")
    city_id   = result.get("cityId")
    max_p     = result.get("maxPrice")
    min_a     = result.get("minArea")
    max_a     = result.get("maxArea")
    area      = max_a or min_a

    prop      = _comm_id_to_label(result.get("commercialPropertyTypeList"), _COMM_PROP_ID2LABEL)
    amenities = _comm_ids_to_labels(result.get("commercial_AmenitiesList"), _COMM_AMEN_ID2LABEL)
    furnish   = _comm_id_to_label(result.get("furnishTypeList"),            _COMM_FUR_ID2LABEL)
    status    = _comm_id_to_label(result.get("propertyStatusList"),         _COMM_STATUS_ID2LABEL)
    facing    = _comm_id_to_label(result.get("propertyFacingList"),         _COMM_FACE_ID2LABEL)

    prop_s        = prop or "Commercial Space"
    loc_val       = locality or city
    is_city_match = (locality is None and city is not None)
    user_loc      = loc_val[0] if isinstance(loc_val, list) else loc_val
    anchor_loc    = user_loc if not is_city_match else _TOP_LOCS[0]

    _NOAMEN = object()

    def _make(value, loc_=None, price_=None, max_area_=None,
              prop_=None, amen_=_NOAMEN, status_=None, fur_=None,
              facing_=None, office_sf_=None):
        l   = loc_      if loc_      is not None else anchor_loc
        mp  = price_    if price_    is not None else max_p
        mxa = max_area_ if max_area_ is not None else max_a
        pt  = prop_     if prop_     is not None else prop_s
        am  = None if amen_ is _NOAMEN else (amen_ if amen_ else None)
        st  = status_   if status_   is not None else status
        f   = fur_      if fur_      is not None else furnish
        fc  = facing_   if facing_   is not None else facing
        osf = office_sf_
        return {
            "value":                      value,
            "commercialPropertyTypeList": _id_lookup(_COMM_PROP,   pt),
            "furnishTypeList":            _id_lookup(_COMM_FUR,    f),
            "commercial_AmenitiesList":   _id_multi(_COMM_AMEN,   *am) if am else None,
            "propertyStatusList":         _id_lookup(_COMM_STATUS, st) if st else None,
            "propertyFacingList":         _id_lookup(_COMM_FACE,  fc) if fc else None,
            "officeSuitedFor":            _id_lookup(_COMM_OFFICE, osf) if osf else None,
            "localityId":                 _loc_id(l),
            "cityId":                     _city_id_lookup(city, city_id),
            "maxPrice":                   mp,
            "minArea":                    None,
            "maxArea":                    mxa,
        }

    raw = []

    # ── LAYER 1: Direct Intent ───────────────────────────────────────────────
    if max_p:
        raw.append(_make(_comm_value(prop_s, anchor_loc, area, max_p, intent="loc"),
                         loc_=anchor_loc, price_=max_p))
        u = _step_up(max_p, _COMM_STEPS)
        if u:
            raw.append(_make(_comm_value(prop_s, anchor_loc, area, u, intent="up"),
                             loc_=anchor_loc, price_=u))
        d = _step_down(max_p, _COMM_STEPS)
        if d:
            raw.append(_make(_comm_value(prop_s, anchor_loc, area, d, intent="down"),
                             loc_=anchor_loc, price_=d))
    else:
        for step in [5_000_000, 10_000_000, 20_000_000]:
            raw.append(_make(_comm_value(prop_s, anchor_loc, area, step, intent="loc"),
                             loc_=anchor_loc, price_=step))

    # ── LAYER 2: Popular Variations — CTR-ranked alt localities ─────────────
    exclude_set = {anchor_loc.lower()} if anchor_loc else set()
    alt_locs    = [l for l in _TOP_LOCS if l.lower() not in exclude_set][:3]
    for alt in alt_locs:
        raw.append(_make(_comm_value(prop_s, alt, area, max_p, intent="loc"),
                         loc_=alt, price_=max_p))

    # ── LAYER 3: Semantic ────────────────────────────────────────────────────
    for sem in _semantic_label_comm(m, prop_s, anchor_loc, max_p,
                                     area, amenities, furnish, status):
        intent_c, pt_, l_, ar_, mp_, am_, f_ = sem
        raw.append(_make(
            _comm_value(pt_, l_, ar_, mp_, intent=intent_c,
                        furnish=f_ if intent_c == "fur" else None),
            loc_=l_, price_=mp_, max_area_=ar_, prop_=pt_,
            amen_=am_ if am_ else _NOAMEN, fur_=f_))

    return _to_indexed(_dedupe(raw, 8))


# ════════════════════════════════════════════════════════════════════════════
# QUICK TEST
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json as _j

    cases = [
        # BUY — no price (Layer 1 fallback + semantic property-type expansion)
        ("BUY — no price",
         "2bhk house in hebbal",
         {"bhk_numbers": "2 BHK", "locality": "Hebbal", "city": "Bangalore",
          "cityId": 1, "maxPrice": None, "minPrice": None,
          "propertyType_name": "Independent House", "amenities_name": []},
         buy_suggestions),

        # BUY — with price + urgency signal (Layer 3: RTM)
        ("BUY — urgency signal",
         "2bhk apartment in whitefield under 80l ready to move asap",
         {"bhk_numbers": "2 BHK", "locality": "Whitefield", "city": "Bangalore",
          "cityId": 1, "maxPrice": 8_000_000, "minPrice": None,
          "propertyType_name": "Apartment", "amenities_name": []},
         buy_suggestions),

        # BUY — investment signal (Layer 3: investment label)
        ("BUY — investment signal",
         "3bhk villa koramangala good roi investment",
         {"bhk_numbers": "3 BHK", "locality": "Koramangala", "city": "Bangalore",
          "cityId": 1, "maxPrice": None, "minPrice": None,
          "propertyType_name": "Villa", "amenities_name": []},
         buy_suggestions),

        # RENTAL — WFH signal (Layer 3: Furnished + Wifi)
        ("RENTAL — WFH signal",
         "2bhk for rent work from home need wifi whitefield under 25k",
         {"bhk": "2 BHK", "locality": "Whitefield", "city": "Bangalore",
          "cityId": 1, "maxRent": 25_000, "Furnish": None, "Tenants": None,
          "Propertytype": "Apartment", "Amenities": []},
         rental_suggestions),

        # PG — budget signal (Layer 3: three sharing)
        ("PG — budget signal",
         "girls pg affordable near indiranagar",
         {"pgAvailableForList": "Girls", "locality": "Indiranagar",
          "city": "Bangalore", "cityId": 1, "maxRent": None,
          "pgBestSuitForList": None, "roomTypes": None,
          "pg_AmenitiesList": [], "pgServiceList": []},
         pg_suggestions),

        # COMMERCIAL — urgency (Layer 3: RTM)
        ("COMM — urgency",
         "office space hsr layout under 50l need immediately",
         {"commercialPropertyTypeList": "Office Space", "locality": "HSR Layout",
          "city": "Bangalore", "cityId": 1, "minArea": None, "maxArea": None,
          "maxPrice": 5_000_000, "commercial_AmenitiesList": [],
          "furnishTypeList": None, "propertyStatusList": None,
          "propertyFacingList": None, "officeSuitedFor": None},
         commercial_suggestions),
    ]

    for label, query, result, fn in cases:
        print(f"\n{'='*65}")
        print(f"[{label}]")
        print(f"Query: \"{query}\"")
        print('='*65)
        out = fn(result, query)
        for k, v in out.items():
            params = {pk: pv for pk, pv in v.items()
                      if pk != 'value' and pv is not None}
            layer = (
                "L1-DirectIntent" if int(k) < 3 else
                "L2-CTRVariation" if int(k) < 6 else
                "L3-Semantic"
            )
            print(f"  [{k}][{layer}] {v['value']}")
            if params:
                print(f"         IDs: {params}")