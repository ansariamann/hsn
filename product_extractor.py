import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

COMMON_FOOD_TERMS = [
    'dates', 'coffee', 'tea', 'sugar', 'rice', 'water', 'juice', 'milk',
    'cheese', 'dairy', 'oil', 'olive', 'spices', 'nuts', 'sweets', 'chocolate',
    'bakery', 'bread', 'cake', 'meat', 'chicken', 'fish', 'seafood', 'honey',
    'jam', 'sauce', 'pasta', 'flour', 'grains', 'canned', 'frozen', 'snack',
    'beverage', 'drink', 'fruits', 'vegetables', 'syrup', 'biscuit', 'cookie'
    'confectionery', 'wafer', 'candy', 'gum', 'butter', 'cream', 'yogurt',
    'poultry', 'beef', 'lamb', 'shrimp', 'prawn', 'tuna', 'sardine', 'pulse',
    'lentil', 'bean', 'pea', 'corn', 'wheat', 'barley', 'oat', 'salt', 'pepper',
    'herb', 'seasoning', 'vinegar', 'ketchup', 'mayonnaise', 'mustard', 'pickle',
    'coconut', 'almond', 'pistachio', 'cashew', 'walnut', 'hazelnut', 'tomato',
    'potato', 'onion', 'garlic', 'ginger', 'turmeric', 'saffron', 'cardamom',
    'clove', 'cinnamon', 'cumin', 'coriander', 'chili', 'paprika', 'curry',
    'masala', 'vanilla', 'cocoa', 'yeast', 'baking', 'powder', 'soda', 'gelatin',
    'jelly', 'pudding', 'custard', 'ice cream', 'sorbet', 'sherbet', 'smoothie',
    'shake', 'malt', 'hops', 'beer', 'wine', 'spirit', 'liquor', 'alcohol',
    'ethanol', 'brandy', 'whisky', 'rum', 'gin', 'vodka', 'tequila', 'liqueur',
    'cider', 'perry', 'mead', 'sake', 'soju', 'shochu', 'baijiu', 'food', 'market'
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\r\n\t]+', ' ', str(text))
    return re.sub(r'\s+', ' ', text).strip()

def is_valid_product_name(text):
    if not text:
        return False
    text = text.strip()
    if len(text) < 3 or len(text) > 100:
         return False
    # Avoid sentences or paragraphs
    if '.' in text and text.count(' ') > 5:
        return False
    # Avoid purely numbers
    if text.isdigit():
        return False
    return True

def get_soup(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return BeautifulSoup(r.text, 'html.parser')
    except Exception as e:
        pass
        # print(f"Error fetching {url}: {e}")
    return None

def extract_shopify_products(base_url):
    """Attempt to extract products from a Shopify store API."""
    products = set()
    page = 1
    max_pages = 5 # Safegaurd
    print(f"  Attempting Shopify extraction for {base_url}...")
    try:
        while page <= max_pages:
            url = f"{base_url.rstrip('/')}/products.json?limit=250&page={page}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                break
                
            data = r.json()
            if 'products' not in data or not data['products']:
                break
                
            for p in data['products']:
                title = clean_text(p.get('title'))
                if is_valid_product_name(title):
                    products.add(title)
            page += 1
    except Exception as e:
         pass
         # print(f"  Shopify extraction failed: {e}")
         
    if products:
         print(f"  [+] Found {len(products)} products via Shopify API")
    return list(products)

def extract_sitemap_products(base_url):
    """Attempt to extract products from XML sitemaps."""
    products = set()
    sitemap_urls = [
         f"{base_url.rstrip('/')}/sitemap_products_1.xml",
         f"{base_url.rstrip('/')}/sitemap.xml",
         f"{base_url.rstrip('/')}/product-sitemap.xml",
         f"{base_url.rstrip('/')}/sitemap-products.xml"
    ]
    
    # We want product names. Often they are in <image:title> or the URL slug itself.
    print(f"  Attempting Sitemap extraction for {base_url}...")
    
    def process_sitemap(url):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                # Namespaces can be tricky, we'll use regex to find URL locs and image titles
                urls = re.findall(r'<loc>(.*?)</loc>', r.text)
                titles = re.findall(r'<[^:]+:title>(.*?)</[^:]+:title>', r.text)
                
                for t in titles:
                    # Clean up titles, sometimes they contain CDATA
                    t_clean = t.replace('<![CDATA[', '').replace(']]>', '')
                    t_clean = clean_text(t_clean)
                    if is_valid_product_name(t_clean):
                        products.add(t_clean)
                        
                for u in urls:
                    if '/product/' in u or '/p/' in u or '/item/' in u or '/products/' in u:
                       # Extract from slug if no titles were found
                       # e.g., site.com/products/fresh-apple-juice -> Fresh Apple Juice
                       slug = u.rstrip('/').split('/')[-1]
                       name = clean_text(slug.replace('-', ' ').title())
                       if is_valid_product_name(name):
                           products.add(name)
        except Exception:
            pass
            
    for s_url in sitemap_urls:
         process_sitemap(s_url)
         if len(products) > 0:
             break # If we found products, we don't need to check other common sitemap paths

    # Filter out common false positives from slugs
    filtered = set()
    for p in products:
         if not any(x in p.lower() for x in ['category', 'collection', 'page', 'about', 'contact']):
             filtered.add(p)

    if filtered:
         print(f"  [+] Found {len(filtered)} products via Sitemap")
    return list(filtered)

def get_domain(url):
    return urlparse(url).netloc

def extract_html_products(base_url, max_pages=15):
    """Fallback: Crawl a limited number of pages to find products."""
    products = set()
    visited = set()
    to_visit = [base_url]
    
    base_domain = get_domain(base_url)
    print(f"  Attempting HTML crawling for {base_url} (max {max_pages} pages)")
    
    def process_page(url):
        soup = get_soup(url)
        if not soup:
            return set(), set()
            
        page_products = set()
        page_links = set()
        
        # Extract products via Schema.org JSON-LD (high accuracy)
        import json
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                # Data can be a dict or a list
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    # Look for @type == Product or @graph containing Product
                    if item.get('@type') == 'Product' and 'name' in item:
                        name = clean_text(item.get('name'))
                        if is_valid_product_name(name):
                            page_products.add(name)
                    if '@graph' in item:
                         for node in item['@graph']:
                              if node.get('@type') == 'Product' and 'name' in node:
                                  name = clean_text(node.get('name'))
                                  if is_valid_product_name(name):
                                      page_products.add(name)
            except:
                pass

        # Extract by looking at tags with 'product' or 'title' classes
        for tag in soup.find_all(['h1', 'h2', 'h3', 'span', 'div', 'a']):
            classes = tag.get('class', [])
            if classes and any('product' in c.lower() or 'title' in c.lower() for c in classes):
                text = clean_text(tag.get_text())
                if is_valid_product_name(text):
                    page_products.add(text)
                    
        # Fallback: check for food terms in general tags (old method, enhanced)
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'li', 'strong']):
            text = clean_text(tag.get_text())
            if 3 < len(text) < 80:
                text_lower = text.lower()
                for term in COMMON_FOOD_TERMS:
                    if re.search(r'\b' + re.escape(term) + r'\b', text_lower):
                        page_products.add(text)
                        break
                        
        # Find links for further crawling
        for a in soup.find_all('a', href=True):
            href = a['href']
            url_full = urljoin(base_url, href).split('#')[0] # ignore fragments
            
            # Stay on the same domain
            if get_domain(url_full) == base_domain:
                # Prioritize product/category links
                href_lower = href.lower()
                if any(x in href_lower for x in ['product', 'category', 'collection', 'item', 'shop', 'brand']):
                    page_links.add(url_full)
                    
        return page_products, page_links

    pages_crawled = 0
    while to_visit and pages_crawled < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
            
        visited.add(url)
        pages_crawled += 1
        
        # print(f"    Crawling: {url}")
        new_prods, new_links = process_page(url)
        products.update(new_prods)
        
        for link in new_links:
            if link not in visited and link not in to_visit:
                to_visit.append(link)
                
    if products:
         print(f"  [+] Found {len(products)} products via HTML Crawling ({pages_crawled} pages checked)")
    return list(products)


def extract_products_from_url(url):
    """
    Enhanced extraction logic relying on:
    1. Shopify API
    2. Sitemaps
    3. HTML BFS Crawling (with schema.org and DOM class parsing)
    """
    if not url or str(url).strip() == '' or str(url).lower() == 'not available':
        return []
        
    if not url.startswith('http'):
        url = 'https://' + url
        
    products = []
    
    # Strategy 1: Shopify
    products = extract_shopify_products(url)
    if products: return products
    
    # Strategy 2: Sitemaps
    products = extract_sitemap_products(url)
    if products: return products
    
    # Strategy 3: HTML Crawl
    products = extract_html_products(url)
    return products

def extract_products_from_text(text):
    """Extract products from the Excel 'Products name' and 'Category' columns"""
    if not text or str(text).strip() == '' or str(text).lower() == 'not available':
        return []
        
    text = str(text)
    
    # Split by common delimiters
    for char in ['/', ',', '+', '&', '-', '|']:
        text = text.replace(char, '|||')
        
    parts = [p.strip() for p in text.split('|||') if p.strip()]
    
    found = []
    for part in parts:
        if len(part) > 2:
            found.append(part)
            
    # If we found nothing by splitting, try the old keyword method as fallback
    if not found:
        text_lower = str(text).lower()
        for term in COMMON_FOOD_TERMS:
             if re.search(r'\b' + re.escape(term) + r'\b', text_lower):
                 found.append(term)

    return list(set(found))

if __name__ == "__main__":
    test_urls = [
        "https://abbarfoods.com/",
        "https://www.alshalan.com/en"
    ]
    for test_url in test_urls:
         print(f"\nTesting: {test_url}")
         prods = extract_products_from_url(test_url)
         for p in prods[:10]: # Print first 10
             print(f" - {p}")
         if len(prods) > 10:
             print(f" ... and {len(prods) - 10} more.")
