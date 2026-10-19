"""Quick verification of WebResolver functionality"""
from brain.web_resolver import WebResolver, SearchResult

def verify_web_resolver():
    resolver = WebResolver()
    
    print("\n" + "="*60)
    print("WEBRESOLVER PHASE 2 - QUICK VERIFICATION")
    print("="*60)
    
    # Test 1: Normal query
    print("\n1. Normal query (Saiyaara):")
    result = resolver.resolve_youtube('Saiyaara')
    print(f"   URL: {result.url}")
    print(f"   Confidence: {result.confidence}")
    assert "youtube.com/results" in result.url
    assert result.confidence == 0.75
    print("   ✓ PASS")
    
    # Test 2: Cache reuse
    print("\n2. Cache reuse (same query):")
    result2 = resolver.resolve_youtube('Saiyaara')
    print(f"   Same object: {result is result2}")
    assert result is result2
    print("   ✓ PASS")
    
    # Test 3: Empty query
    print("\n3. Empty query:")
    result3 = resolver.resolve_youtube('')
    print(f"   Returns None: {result3 is None}")
    assert result3 is None
    print("   ✓ PASS")
    
    # Test 4: Special characters
    print("\n4. Special characters (Maruti - Full):")
    result4 = resolver.resolve_youtube('Maruti - Full')
    print(f"   URL: {result4.url}")
    assert "youtube.com/results" in result4.url
    print("   ✓ PASS")
    
    # Test 5: Spaces normalization
    print("\n5. Spaces normalization:")
    result5a = resolver.resolve_youtube('Test  Query')
    result5b = resolver.resolve_youtube('Test Query')
    print(f"   Cache hit with spaces: {result5a is result5b}")
    assert result5a is result5b
    print("   ✓ PASS")
    
    # Test 6: Open URL (doesn't actually open)
    print("\n6. Open URL (safe, doesn't launch browser):")
    can_open = WebResolver.open_url("https://www.youtube.com/results?search_query=test")
    print(f"   open_url() returns bool: {isinstance(can_open, bool)}")
    assert isinstance(can_open, bool)
    print("   ✓ PASS")
    
    print("\n" + "="*60)
    print("✓ ALL VERIFICATION TESTS PASSED")
    print("WebResolver Phase 2 is working correctly!")
    print("="*60 + "\n")

if __name__ == "__main__":
    verify_web_resolver()
