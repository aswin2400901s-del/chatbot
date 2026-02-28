from regex_extraction import extract_price

print("=" * 60)
print("PRICE RANGE EXTRACTION TESTS")
print("=" * 60)

test_cases = [
    # Range tests
    ("2bhk in bangalore 20 to 50 lakhs", "20-50 lakhs"),
    ("flat 30l-60l with gym", "30-60 lakhs"),
    ("apartment between 40 and 80 lakh", "40-80 lakhs"),
    ("villa 50l to 1 crore", "50l to 1cr (mixed units)"),
    ("plot 2 crore to 5 crore", "2-5 crore"),
    
    # Single value tests
    ("under 50l", "under 50 lakhs"),
    ("above 25 lakh", "above 25 lakhs"),
    ("50 crore", "single 50 crore"),
    ("budget 30l", "single 30 lakhs"),
]

for query, desc in test_cases:
    result = extract_price(query)
    print(f"\n✓ {desc}")
    print(f"  Query: '{query}'")
    print(f"  minPrice: ₹{result['minPrice']:,}" if result['minPrice'] else f"  minPrice: None")
    print(f"  maxPrice: ₹{result['maxPrice']:,}" if result['maxPrice'] else f"  maxPrice: None")
