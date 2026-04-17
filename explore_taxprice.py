import requests
from bs4 import BeautifulSoup
import json

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

output = []

def log(msg):
    output.append(str(msg))
    print(msg)

# Explore Saudi Arabia HS code page
url = 'https://taxprice.org/hs-customs-tarif/saudi-arabia/'
r = requests.get(url, headers=headers)
log(f'Status: {r.status_code}')
soup = BeautifulSoup(r.text, 'html.parser')

# Find all links that go deeper
links = soup.find_all('a', href=True)
sa_links = []
for a in links:
    href = a.get('href', '')
    text = a.get_text(strip=True)
    if 'saudi-arabia/' in href and href.count('/') > href.index('saudi-arabia/') // len('saudi-arabia/') + 3 and text:
        sa_links.append((href, text))

# Deduplicate
seen = set()
unique_links = []
for href, text in sa_links:
    if href not in seen:
        seen.add(href)
        unique_links.append((href, text))

log(f'Found {len(unique_links)} unique sub-links from Saudi Arabia page:')
for href, text in unique_links[:50]:
    log(f'  {href} -> {text[:120]}')

# Also save the full HTML to a file so we can inspect it
with open('saudi_page.html', 'w', encoding='utf-8') as f:
    f.write(r.text)

# Try to navigate into a sub-link
if unique_links:
    first_href = unique_links[0][0]
    if not first_href.startswith('http'):
        first_href = 'https://taxprice.org' + first_href
    log(f'\n--- Exploring: {first_href} ---')
    r2 = requests.get(first_href, headers=headers)
    log(f'Status: {r2.status_code}')
    
    with open('sub_page.html', 'w', encoding='utf-8') as f:
        f.write(r2.text)
    
    soup2 = BeautifulSoup(r2.text, 'html.parser')
    text = soup2.get_text(separator='\n', strip=True)
    log(f'Page text (first 3000 chars):\n{text[:3000]}')
else:
    log('No sub-links found. Dumping page text...')
    text = soup.get_text(separator='\n', strip=True)
    log(f'Full page text (first 5000 chars):\n{text[:5000]}')

# Write all output to file
with open('explore_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))
