from master_pipeline import smart_search

print("=" * 70)
print("FULL PIPELINE TEST - PRICE RANGES")
print("=" * 70)

test_queries = [
    "2bhk apartment with gym 30l to 60l  in whitefield",
    "3bhk villa 50l-1cr in bangalore",
    "1bhk flat under 25 lakhs",
    "4bhk house above 1 crore with swimming pool",
]

for query in test_queries:
    print(f"\n📍 Query: {query}")
    result = smart_search(query)
    print(f"   minPrice: ₹{result['minPrice']:,}" if result['minPrice'] else f"   minPrice: 0")
    print(f"   maxPrice: ₹{result['maxPrice']:,}" if result['maxPrice'] else f"   maxPrice: Not specified")
    print(f"   BHK: {result['bhk_numbers']}")
    print(f"   Locality: {result.get('locality', 'Not specified')}")
    print(f"   City: {result.get('city', 'Not specified')}")
