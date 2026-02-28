from fuzzy_match import extract_amenities
from NER_training import amenities_map
from master_pipeline import smart_search

print("=" * 60)
print("TEST 1: Direct amenities extraction")
print("=" * 60)
test_query = '2bhk with gym and swimming pool in whitefield '
result = extract_amenities(test_query, amenities_map)

print('Test Query:', test_query)
print('\nExtracted Amenities:')
print('  Names:', result['amenities_name'])
print('  IDs:', result['amenities_id'])

print("\n" + "=" * 60)
print("TEST 2: Full smart_search pipeline")
print("=" * 60)
full_result = smart_search(test_query)

print('\nFull Search Result:')
print('  BHK:', full_result.get('bhk_numbers'))
print('  Locality:', full_result.get('locality'))
print('  Amenities Names:', full_result.get('amenities_name'))
print('  Amenities IDs:', full_result.get('amenities_id'))

print("\n" + "=" * 60)
print("TEST 3: Another query with different amenities")
print("=" * 60)
test_query2 = '3bhk apartment with power backup and gym'
result2 = extract_amenities(test_query2, amenities_map)
print('Query:', test_query2)
print('Amenities Found:', result2['amenities_name'])
print('Amenity IDs:', result2['amenities_id'])
