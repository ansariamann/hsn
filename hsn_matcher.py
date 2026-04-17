import json
import os
from fuzzywuzzy import process
from fuzzywuzzy import fuzz

class HSNMatcher:
    def __init__(self, hs_codes_file='hs_codes_sa.json'):
        self.hs_codes = []
        self.code_descriptions = []
        
        if os.path.exists(hs_codes_file):
            with open(hs_codes_file, 'r', encoding='utf-8') as f:
                self.hs_codes = json.load(f)
                # Prepare a list of strings to match against 
                # Combining chapter and description for better context
                # Use 'full_text' if available (from deep crawl), otherwise fallback
                self.code_descriptions = [
                    item.get('full_text', f"{item['chapter']} - {item['description']}") 
                    for item in self.hs_codes
                ]
        else:
            print(f"Warning: {hs_codes_file} not found. Matcher will return empty results.")
            
    def get_match(self, product_name):
        """Match a product name to the best HS code"""
        if not product_name or not self.hs_codes:
            return None, None, 0
            
        # Use token set ratio to handle multi-word products
        best_match, score = process.extractOne(
            str(product_name).lower(), 
            self.code_descriptions, 
            scorer=fuzz.token_set_ratio
        )
        
        # Increased threshold for better match quality. A low threshold like 30 can lead to many incorrect matches.
        if score > 60: # Minimum acceptable score threshold
            # Find the original object
            idx = self.code_descriptions.index(best_match)
            return self.hs_codes[idx]['code'], self.hs_codes[idx]['description'], score
            
        return None, None, 0

if __name__ == "__main__":
    # Test
    matcher = HSNMatcher()
    print(matcher.get_match("coffee beans"))
    print(matcher.get_match("apple fruit"))
