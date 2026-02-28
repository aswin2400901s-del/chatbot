#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
import re
from rapidfuzz import process, fuzz

# ===============================
# TEXT NORMALIZATION (MUST BE FIRST)
# ===============================

def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

# ===============================
# LOAD DATA
# ===============================

# Resolve CSV path relative to this file's directory (no hardcoded absolute path)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_PATH = os.path.join(_BASE_DIR, "buy_searchproperty_new 2(Sheet1).csv")

# Fallback: allow override via environment variable
CSV_PATH = os.environ.get("HOMES247_CSV", CSV_PATH)

df = pd.read_csv(CSV_PATH)

# ===============================
# MAPS
# ===============================

city_map = (
    df[["city", "cityId"]]
    .dropna()
    .drop_duplicates()
    .set_index("city")["cityId"]
    .to_dict()
)

locality_map = (
    df[["locality", "localityId"]]
    .dropna()
    .drop_duplicates()
    .set_index("locality")["localityId"]
    .to_dict()
)

property_type_map = (
    df[["propertyType_name", "propertyType_id"]]
    .dropna()
    .drop_duplicates()
    .set_index("propertyType_name")["propertyType_id"]
    .to_dict()
)

amenities_map = (
    df[["amenities_name", "amenities_id"]]
    .dropna()
    .drop_duplicates()
    .set_index("amenities_name")["amenities_id"]
    .to_dict()
)

# ===============================
# LOCALITY → CITY RELATION
# FIX: Normalize keys so title-cased lookups always work
# ===============================

locality_to_city = {
    str(loc).title(): city
    for loc, city in zip(df["locality"], df["city"])
    if pd.notna(loc) and pd.notna(city)
}

locality_to_city_id = {
    str(loc).title(): cid
    for loc, cid in zip(df["locality"], df["cityId"])
    if pd.notna(loc) and pd.notna(cid)
}

# ===============================
# NORMALIZED LOCALITY DATA
# ===============================

locality_map_norm = {
    normalize_text(k): v
    for k, v in locality_map.items()
    if isinstance(k, str)
}

locality_list_norm = list(locality_map_norm.keys())

# ===============================
# TEST
# ===============================

if __name__ == "__main__":
    print("City map sample:", list(city_map.items())[:3])
    print("Locality map sample:", list(locality_map.items())[:3])
    print("Amenities sample:", list(amenities_map.items())[:5])