import requests
import json
from bs4 import BeautifulSoup
import time
import os
from typing import Any
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/x-www-form-urlencoded',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://taxprice.org/hs-customs-tarif/saudi-arabia/'
}
API_URL = 'https://taxprice.org/calculation/tnvedpart/'

def parse_text(html_text):
    if not html_text:
        return "", ""
    soup = BeautifulSoup(html_text, 'html.parser')
    code_span = soup.find('span', class_='code')
    value_span = soup.find('span', class_='value')
    code = code_span.get_text(strip=True) if code_span else ''
    value = value_span.get_text(strip=True) if value_span else ''
    return code, value

def fetch_children(
    session: requests.Session,
    cache: dict[tuple[str, str], Any],
    stats: dict[str, int],
    parent_id,
    root_val,
):
    cache_key = (str(parent_id), str(root_val))
    if cache_key in cache:
        stats["cache_hits"] += 1
        return cache[cache_key]

    stats["api_calls"] += 1
    data = {'parent_id': str(parent_id), 'country_code': 'saudi-arabia', 'root': str(root_val)}
    backoff_s = 1.0
    for _ in range(3):
        try:
            r = session.post(API_URL, headers=HEADERS, data=data, timeout=10)
            if r.status_code == 200:
                try:
                    payload = r.json()
                    if not isinstance(payload, list):
                        raise ValueError("Payload is not a list")
                    cache[cache_key] = payload
                    return payload
                except Exception as e:
                    print(f"Error parsing JSON for {parent_id} (retrying): {e}")
        except Exception as e:
            print(f"Error fetching {parent_id}: {e}")
        time.sleep(backoff_s)
        backoff_s *= 2

    cache[cache_key] = []
    return []

def recursive_crawl(
    session: requests.Session,
    cache: dict[tuple[str, str], Any],
    stats: dict[str, int],
    item,
    root_val,
    section_name,
    chapter_desc,
    parent_desc_path,
    leaf_nodes,
    verbose: bool,
    stop_at_digits: int | None,
):
    """Fetch children to find deepest HS codes (iterative DFS to avoid recursion limits)."""
    stack: list[tuple[Any, str]] = [(item, parent_desc_path)]
    visited: set[tuple[str, str]] = set()

    while stack:
        node, parent_path = stack.pop()
        stats["nodes_seen"] += 1

        node_id = str(node.get("id", ""))
        if node_id:
            visit_key = (node_id, str(root_val))
            if visit_key in visited:
                stats["cycle_skips"] += 1
                continue
            visited.add(visit_key)

        current_code, current_desc = parse_text(node.get("text", ""))
        full_desc = f"{parent_path} {current_desc}".strip()

        if stop_at_digits and current_code:
            digits_only = re.sub(r"\D", "", str(current_code))
            if len(digits_only) >= stop_at_digits:
                if verbose:
                    print(f"    Found leaf (stop_at_digits={stop_at_digits}): {current_code}")
                leaf_nodes.append({
                    'code': current_code,
                    'description': current_desc,
                    'full_text': full_desc,
                    'chapter': chapter_desc,
                    'section': section_name
                })
                continue

        children = fetch_children(session, cache, stats, node_id, 'false')

        if not children:
            if current_code:
                if verbose:
                    print(f"    Found leaf: {current_code}")
                leaf_nodes.append({
                    'code': current_code,
                    'description': current_desc,
                    'full_text': full_desc,
                    'chapter': chapter_desc,
                    'section': section_name
                })
            continue

        # DFS: push children in reverse so original order is processed first
        for child in reversed(children):
            stack.append((child, full_desc))

def build_hs_tree(
    force_rebuild: bool = False,
    verbose: bool = False,
    output_file: str = "hs_codes_sa.json",
    stop_at_digits: int | None = None,
):
    print("Starting HS Code tree builder for Saudi Arabia...")
    start = time.perf_counter()
    
    if os.path.exists(output_file) and not force_rebuild:
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached:  # non-empty list = valid cache
                elapsed = time.perf_counter() - start
                print(f"Using cached HS codes from {output_file} ({len(cached)} leaf codes, {elapsed:.2f}s).")
                return cached
            else:
                print(f"Cache file {output_file} is empty. Rebuilding...")
        except Exception as e:
            print(f"Cache read failed ({output_file}): {e}. Rebuilding...")

    if os.path.exists(output_file) and force_rebuild:
        print(f"{output_file} exists; rebuilding (force_rebuild=True).")
        pass

    # All 21 HS sections for comprehensive product coverage
    target_sections = [
        {'id': '0_1', 'root': '1', 'name': 'Live Animals; Animal Products'},
        {'id': '0_2', 'root': '2', 'name': 'Vegetable Products'},
        {'id': '0_3', 'root': '3', 'name': 'Animal/Vegetable Fats and Oils'},
        {'id': '0_4', 'root': '4', 'name': 'Prepared Foodstuffs; Beverages; Tobacco'},
        {'id': '0_5', 'root': '5', 'name': 'Mineral Products'},
        {'id': '0_6', 'root': '6', 'name': 'Chemical Products'},
        {'id': '0_7', 'root': '7', 'name': 'Plastics and Rubber'},
        {'id': '0_8', 'root': '8', 'name': 'Raw Hides, Skins, Leather'},
        {'id': '0_9', 'root': '9', 'name': 'Wood; Cork; Basketware'},
        {'id': '0_10', 'root': '10', 'name': 'Pulp; Paper; Paperboard'},
        {'id': '0_11', 'root': '11', 'name': 'Textiles and Textile Articles'},
        {'id': '0_12', 'root': '12', 'name': 'Footwear; Headgear; Umbrellas'},
        {'id': '0_13', 'root': '13', 'name': 'Stone; Plaster; Cement; Ceramics; Glass'},
        {'id': '0_14', 'root': '14', 'name': 'Pearls; Precious Metals and Stones'},
        {'id': '0_15', 'root': '15', 'name': 'Base Metals and Articles'},
        {'id': '0_16', 'root': '16', 'name': 'Machinery and Mechanical Appliances'},
        {'id': '0_17', 'root': '17', 'name': 'Vehicles; Aircraft; Vessels'},
        {'id': '0_18', 'root': '18', 'name': 'Optical; Medical; Musical Instruments'},
        {'id': '0_19', 'root': '19', 'name': 'Arms and Ammunition'},
        {'id': '0_20', 'root': '20', 'name': 'Miscellaneous Manufactured Articles'},
        {'id': '0_21', 'root': '21', 'name': 'Works of Art; Antiques'},
    ]
    
    leaf_nodes = []
    session = requests.Session()
    cache: dict[tuple[str, str], Any] = {}
    stats = {"api_calls": 0, "cache_hits": 0, "nodes_seen": 0, "cycle_skips": 0}
    
    for section in target_sections:
        print(f"Fetching Section: {section['name']}")
        chapters = fetch_children(session, cache, stats, section['id'], section['root'])
        
        for chapter in chapters:
            ch_code, ch_desc = parse_text(chapter['text'])
            print(f"  Chapter {ch_code}: {ch_desc[:50]}...")
            
            # Pass 'false' as root for sub-chapter calls (discovered via browser network capture).
            # The jstree uses section root only for section→chapter; deeper levels use root='false'.
            recursive_crawl(
                session,
                cache,
                stats,
                chapter,
                'false',
                section['name'],
                ch_desc,
                "",
                leaf_nodes,
                verbose,
                stop_at_digits,
            )
                                 
    elapsed = time.perf_counter() - start
    print(
        f"Completed! Found {len(leaf_nodes)} leaf HS codes "
        f"({elapsed:.1f}s, api_calls={stats['api_calls']}, cache_hits={stats['cache_hits']}, "
        f"nodes_seen={stats['nodes_seen']}, cycle_skips={stats['cycle_skips']})."
    )
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(leaf_nodes, f, indent=2, ensure_ascii=False)
    return leaf_nodes

if __name__ == "__main__":
    build_hs_tree()
