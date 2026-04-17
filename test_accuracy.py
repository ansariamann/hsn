import json
from hsn_lookup import HSLookup
import time

def test_lookup():
    print("Loading HSLookup...")
    l = HSLookup()
    
    test_cases = [
        ("Chocolate Cupcake", "19", "0.95-1.00"),
        ("Live Horses", "01", "0.95-1.00"),
        ("Fresh Chicken", "02", "0.85-1.00"),
        ("Ketchup", "21", "0.85-1.00"),
        ("Canned Sausages", "16", "0.85-1.00"),
    ]
    
    for product, expected_ch, expected_conf in test_cases:
        t0 = time.time()
        res = l.lookup(product)
        t1 = time.time()
        
        ch = res.get("chapter", "none")
        conf = res.get("confidence", 0)
        
        status = "PASS" if ch == expected_ch else "FAIL"
        print(f"[{status}] {product} -> Ch {ch} (expected {expected_ch}), conf={conf} (time: {t1-t0:.3f}s)")

if __name__ == "__main__":
    test_lookup()
