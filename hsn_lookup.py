"""
HSN Code Lookup Tool for Saudi Arabia
======================================
Given a product name, looks up the best-matching HS/HSN code from
taxprice.org Saudi Arabia tariff data and returns structured JSON.

Confidence bands:
  0.95–1.00 → Exact product name found in taxprice description
  0.85–0.94 → Product named in HS heading/subheading text
  0.60–0.84 → Matched by ingredient / product form / synonym
  0.30–0.59 → Brand-only or very ambiguous (notes attached)
  < 0.30    → No match reported

Usage:
    python hsn_lookup.py "Chocolate Cupcake"
    python hsn_lookup.py "Ketchup"
    python hsn_lookup.py --rebuild-cache "Olive Oil"
"""

import json
import sys
import os
import re
import argparse
from datetime import datetime, timezone

from fuzzywuzzy import fuzz

from hsn_tree_builder import build_hs_tree
from synonyms import PRODUCT_SYNONYMS, BRAND_NAMES, HS_CHAPTER_HINTS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HS_CACHE_FILE = "hs_codes_sa.json"
BASE_URL = "https://taxprice.org/hs-customs-tarif/saudi-arabia/"
DETAIL_URL_TEMPLATE = "https://taxprice.org/hs-customs-tarif/saudi-arabia/{code}/"

# Confidence band thresholds
CONF_EXACT    = (0.95, 1.00)   # exact product name in taxprice
CONF_HEADING  = (0.85, 0.94)   # product named in HS heading/subheading
CONF_FORM     = (0.60, 0.84)   # matched via ingredient / product form
CONF_AMBIG    = (0.30, 0.59)   # brand-only or ambiguous
CONF_NONE     = 0.0

# Processed-meat keywords that steer toward Ch. 16 vs Ch. 02
PROCESSED_KEYWORDS = {
    "canned", "tinned", "sausage", "sausages", "nugget", "nuggets",
    "salami", "mortadella", "pepperoni", "jerky", "ham", "bacon",
    "corned", "luncheon", "hot dog", "hotdog", "patty", "patties",
    "processed", "cooked", "smoked", "cured", "preserved", "prepared",
    "paste", "pate", "pâté", "extract",
}
FRESH_FROZEN_KEYWORDS = {
    "fresh", "frozen", "chilled", "raw", "whole", "bone-in", "boneless",
    "live",
}
MEAT_POULTRY_KEYWORDS = {
    "meat", "chicken", "beef", "lamb", "mutton", "veal", "pork",
    "poultry", "turkey", "duck", "goose", "offal", "liver", "kidney",
}


# ---------------------------------------------------------------------------
# Product name normalization
# ---------------------------------------------------------------------------
def normalize_product(raw_name: str) -> str:
    """Strip brand names, normalize whitespace, lowercase."""
    name = raw_name.strip().lower()

    # Remove known brand names
    for brand in sorted(BRAND_NAMES, key=len, reverse=True):
        name = re.sub(r'\b' + re.escape(brand) + r'\b', '', name)

    # Remove excess whitespace and punctuation debris
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def _is_brand_only(raw_name: str, normalized: str) -> bool:
    """Return True if the input was *only* brand name(s) with no product words left."""
    return len(normalized) == 0 or all(len(w) <= 2 for w in normalized.split())


def expand_with_synonyms(normalized: str) -> tuple[list[str], list[str]]:
    """Return (primary_terms, secondary_terms).

    Primary terms = product form/type (last matched phrase).
    Secondary terms = modifiers / ingredients (earlier phrases).
    """
    words = normalized.split()
    if not words:
        return [normalized], []

    primary_terms = [normalized]  # always include full phrase
    secondary_terms = []

    # Find longest matching phrase in the product name
    matched_spans = []  # (start, end, phrase, synonyms)
    for n in range(len(words), 0, -1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            if phrase in PRODUCT_SYNONYMS:
                matched_spans.append((i, i + n, phrase, PRODUCT_SYNONYMS[phrase]))

    # Remove overlapping spans (prefer longer ones)
    used_indices = set()
    for start, end, phrase, syns in sorted(matched_spans, key=lambda x: x[1] - x[0], reverse=True):
        span_indices = set(range(start, end))
        if span_indices & used_indices:
            continue
        used_indices |= span_indices

        if end == len(words):
            # Last word(s) → product form (primary)
            primary_terms.extend(syns)
        else:
            # Earlier word(s) → modifier / ingredient (secondary)
            secondary_terms.extend(syns)

    # If no spans matched, fall back: all words to primary
    if not matched_spans:
        for word in words:
            if word in PRODUCT_SYNONYMS:
                primary_terms.extend(PRODUCT_SYNONYMS[word])

    # Unmatched words → secondary
    for i, word in enumerate(words):
        if i not in used_indices and len(word) > 2:
            secondary_terms.append(word)

    primary_terms = list(dict.fromkeys(primary_terms))
    secondary_terms = list(dict.fromkeys(t for t in secondary_terms if t not in primary_terms))

    return primary_terms, secondary_terms


# ---------------------------------------------------------------------------
# Match-type classification (drives the confidence band)
# ---------------------------------------------------------------------------
_MATCH_EXACT   = "exact"       # 0.95–1.00
_MATCH_HEADING = "heading"     # 0.85–0.94
_MATCH_FORM    = "form"        # 0.60–0.84
_MATCH_FUZZY   = "fuzzy"       # 0.30–0.59


def _classify_match(normalized: str, primary_terms: list[str],
                    item_desc_lower: str, full_text_lower: str) -> tuple[str, float]:
    """Determine the match type and a raw quality score (0-1) for band placement.

    Returns (match_type, quality) where quality positions within the band.
    """
    # --- EXACT: the full normalized product name appears in the HS description ---
    if normalized and normalized in item_desc_lower:
        length_ratio = len(normalized) / max(len(item_desc_lower), 1)
        quality = min(0.5 + length_ratio * 2, 1.0)  # quality within band
        return _MATCH_EXACT, quality

    # --- HEADING: any primary term that IS the product name directly appears ---
    # We check if the original product words (not synonym expansions) appear
    product_words = set(normalized.split())
    desc_words = set(re.findall(r'\b\w+\b', item_desc_lower))
    word_overlap = product_words & desc_words
    if len(word_overlap) >= max(1, len(product_words) * 0.6):
        # Most product words found in description
        quality = len(word_overlap) / max(len(product_words), 1)
        return _MATCH_HEADING, min(quality, 1.0)

    # --- FORM: synonym-expanded terms match the description ---
    best_fuzzy = 0.0
    any_primary_exact = False
    for term in primary_terms:
        if term == normalized:
            continue  # already checked above
        if term in item_desc_lower:
            any_primary_exact = True
            length_ratio = len(term) / max(len(item_desc_lower), 1)
            qual = min(0.4 + length_ratio * 2, 1.0)
            best_fuzzy = max(best_fuzzy, qual)
        elif term in full_text_lower:
            length_ratio = len(term) / max(len(full_text_lower), 1)
            qual = min(0.2 + length_ratio * 3, 0.8)
            best_fuzzy = max(best_fuzzy, qual)
        f = fuzz.token_set_ratio(term, item_desc_lower) / 100.0
        if f >= 0.70:
            best_fuzzy = max(best_fuzzy, f * 0.85)

    if any_primary_exact or best_fuzzy >= 0.60:
        return _MATCH_FORM, min(best_fuzzy, 1.0)

    # --- FUZZY: weak / ambiguous match ---
    if best_fuzzy >= 0.30:
        return _MATCH_FUZZY, min(best_fuzzy, 1.0)

    return _MATCH_FUZZY, best_fuzzy


def _band_score(match_type: str, quality: float) -> float:
    """Map (match_type, quality) into the calibrated confidence band."""
    if match_type == _MATCH_EXACT:
        lo, hi = CONF_EXACT
    elif match_type == _MATCH_HEADING:
        lo, hi = CONF_HEADING
    elif match_type == _MATCH_FORM:
        lo, hi = CONF_FORM
    else:  # fuzzy / ambiguous
        lo, hi = CONF_AMBIG
    return round(lo + quality * (hi - lo), 2)


# ---------------------------------------------------------------------------
# HS code matching engine
# ---------------------------------------------------------------------------
class HSLookup:
    def __init__(self, cache_file: str = HS_CACHE_FILE):
        self.hs_codes: list[dict] = []
        self.descriptions: list[str] = []
        self.item_desc_lower_list: list[str] = []
        self.digits_list: list[str] = []

        # Load HS code tree
        if os.path.exists(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                self.hs_codes = json.load(f)

        if not self.hs_codes:
            print("HS code cache is empty or missing. Building...", file=sys.stderr)
            self.hs_codes = build_hs_tree(force_rebuild=False, stop_at_digits=6)

        # Build searchable descriptions
        for item in self.hs_codes:
            desc = item.get("full_text", "")
            if not desc:
                desc = f"{item.get('chapter', '')} {item.get('description', '')}"
            self.descriptions.append(desc.lower())
            self.item_desc_lower_list.append((item.get("description", "") or "").lower())
            self.digits_list.append(re.sub(r'\D', '', str(item.get("code", ""))))

    # ------------------------------------------------------------------ scoring
    def _score_candidate(self, normalized: str,
                         primary_terms: list[str],
                         secondary_terms: list[str],
                         idx: int) -> tuple[float, str]:
        """Return (calibrated_confidence, match_type) for a single HS entry."""
        item = self.hs_codes[idx]
        item_desc_lower = self.item_desc_lower_list[idx]
        full_text_lower = self.descriptions[idx]

        match_type, quality = _classify_match(
            normalized, primary_terms, item_desc_lower, full_text_lower
        )

        # Secondary-term boost: if secondary terms also match, nudge quality up
        secondary_boost = 0.0
        for term in secondary_terms:
            if term in item_desc_lower:
                secondary_boost = max(secondary_boost, 0.12)
            elif fuzz.token_set_ratio(term, item_desc_lower) / 100.0 >= 0.75:
                # Still doing token set ratio here but it's only on secondary terms, which are few.
                secondary_boost = max(secondary_boost, 0.06)
        quality = min(quality + secondary_boost, 1.0)

        # Specificity bonus: longer HS codes = more specific
        digits = self.digits_list[idx]
        if len(digits) >= 8:
            quality = min(quality + 0.05, 1.0)
        elif len(digits) >= 6:
            quality = min(quality + 0.02, 1.0)

        return _band_score(match_type, quality), match_type

    # ---------------------------------------------------------- meat/poultry logic
    @staticmethod
    def _detect_meat_preference(normalized: str) -> str | None:
        """If the product involves meat/poultry, return preferred chapter."""
        words = set(normalized.split())
        if not (words & MEAT_POULTRY_KEYWORDS):
            return None
        if words & PROCESSED_KEYWORDS:
            return "16"  # processed meat → Ch. 16
        if words & FRESH_FROZEN_KEYWORDS:
            return "02"  # fresh/frozen → Ch. 02
        # Default: if unspecified, lean toward Ch. 02 (whole meat)
        return "02"

    # ---------------------------------------------------------- candidate search
    def find_candidates(self, product: str, top_n: int = 5) -> list[dict]:
        """Find top N HS code candidates for the given product."""
        normalized = normalize_product(product)
        primary_terms, secondary_terms = expand_with_synonyms(normalized)
        meat_chapter = self._detect_meat_preference(normalized)

        scored = []
        for idx in range(len(self.hs_codes)):
            conf, mtype = self._score_candidate(
                normalized, primary_terms, secondary_terms, idx
            )
            if conf < 0.25:
                continue

            item = self.hs_codes[idx]
            code = item.get("code", "")
            code_clean = re.sub(r'\D', '', str(code))
            chapter = code_clean[:2] if len(code_clean) >= 2 else None

            # Meat/poultry chapter preference boost
            if meat_chapter and chapter:
                if chapter == meat_chapter:
                    conf = min(conf + 0.05, 1.0)
                elif chapter in ("02", "16") and chapter != meat_chapter:
                    conf = max(conf - 0.03, 0.0)

            scored.append((idx, conf, mtype))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Deduplicate by code
        seen_codes = set()
        candidates = []
        for idx, conf, mtype in scored:
            item = self.hs_codes[idx]
            code = item.get("code", "")
            if code in seen_codes:
                continue
            seen_codes.add(code)

            code_clean = re.sub(r'\D', '', str(code))
            code_len = len(code_clean) if code_clean else None
            chapter = code_clean[:2] if code_clean and len(code_clean) >= 2 else None
            source_url = (
                DETAIL_URL_TEMPLATE.format(code=code_clean) if code_clean else BASE_URL
            )

            candidates.append({
                "hs_code": code_clean if code_clean else code,
                "code_length": code_len,
                "hs_description": item.get("description", ""),
                "source_url": source_url,
                "confidence": conf,
                "match_type": mtype,
                "reason": self._build_reason(normalized, item, conf, mtype),
                "_chapter": chapter,
            })

            if len(candidates) >= top_n:
                break

        return candidates

    # ---------------------------------------------------------- reason text
    @staticmethod
    def _build_reason(normalized: str, item: dict, conf: float, mtype: str) -> str:
        desc = item.get("description", "")
        code = item.get("code", "")
        section = item.get("section", "")

        if mtype == _MATCH_EXACT:
            return (
                f"Exact taxprice match: '{normalized}' directly found in "
                f"HS {code} description — {desc}."
            )
        elif mtype == _MATCH_HEADING:
            return (
                f"Heading match: product words appear in HS {code} — {desc}."
            )
        elif mtype == _MATCH_FORM:
            return (
                f"Product-form match: '{normalized}' classified via primary "
                f"ingredient/form to HS {code} — {desc} (Section: {section})."
            )
        else:
            return (
                f"Partial/ambiguous match: '{normalized}' may relate to "
                f"HS {code} — {desc}. Manual verification recommended."
            )

    # ---------------------------------------------------------- main lookup
    def lookup(self, product: str) -> dict:
        """Main lookup: returns the full JSON response object."""
        normalized = normalize_product(product)
        brand_only = _is_brand_only(product, normalized)
        candidates = self.find_candidates(product, top_n=3)

        top = candidates[0] if candidates else None

        # Build notes
        notes = None
        if not top or top["confidence"] < 0.30:
            notes = (
                "No relevant HS entry found on taxprice.org for this product. "
                "Try providing more specific details (e.g., ingredient, "
                "processing method, packaging)."
            )
            if brand_only:
                notes = (
                    f"Input '{product}' appears to be a brand name only. "
                    "Please include the actual product type (e.g., "
                    "'Brand XYZ Chocolate Milk')."
                )
        elif top["confidence"] < 0.60:
            notes = (
                f"Low confidence ({top['confidence']}). "
                f"The product '{product}' is ambiguous. "
                "Specify: fresh/frozen/canned/dried? "
                "Primary ingredient? Processing method?"
            )
            if brand_only:
                notes += (
                    f" Input appears to be mostly a brand name. "
                    "Include the product type for better accuracy."
                )
        elif (
            len(candidates) > 1
            and candidates[1]["confidence"] >= candidates[0]["confidence"] - 0.08
        ):
            notes = (
                f"Multiple plausible matches. Top: HS {top['hs_code']} "
                f"(conf {top['confidence']}). "
                f"Runner-up: HS {candidates[1]['hs_code']} "
                f"(conf {candidates[1]['confidence']}). "
                "Provide more detail to disambiguate."
            )

        # Detect meat/poultry and add a note if relevant
        meat_ch = self._detect_meat_preference(normalized)
        if meat_ch and top:
            ch = top.get("_chapter", "")
            if ch in ("02", "16"):
                meat_note = (
                    f"Meat/poultry detected → preferring Ch. {meat_ch} "
                    f"({'processed/prepared' if meat_ch == '16' else 'fresh/frozen'})."
                )
                notes = f"{notes} {meat_note}" if notes else meat_note

        # Source URLs
        source_urls = [BASE_URL]
        for c in candidates:
            if c["source_url"] not in source_urls:
                source_urls.append(c["source_url"])

        # Clean candidates for output
        clean_candidates = []
        for c in candidates:
            clean_candidates.append({
                "hs_code": c["hs_code"],
                "code_length": c["code_length"],
                "hs_description": c["hs_description"],
                "source_url": c["source_url"],
                "confidence": c["confidence"],
                "match_type": c["match_type"],
                "reason": c["reason"],
            })

        chapter = top["_chapter"] if top else None

        result = {
            "product": product,
            "normalized_product": normalized,
            "hs_code": top["hs_code"] if top and top["confidence"] >= 0.30 else None,
            "code_length": top["code_length"] if top and top["confidence"] >= 0.30 else None,
            "hs_description": top["hs_description"] if top and top["confidence"] >= 0.30 else None,
            "chapter": chapter if top and top["confidence"] >= 0.30 else None,
            "candidates": clean_candidates,
            "confidence": top["confidence"] if top else 0.0,
            "match_type": top["match_type"] if top else None,
            "notes": notes,
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_urls": source_urls,
        }

        return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Lookup HS/HSN code for a product from taxprice.org Saudi Arabia tariff."
    )
    parser.add_argument(
        "product",
        nargs="?",
        help="Product name to classify (e.g., 'Chocolate Cupcake', 'Ketchup')",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="Force rebuild the HS code cache from taxprice.org",
    )
    parser.add_argument(
        "--stop-at-digits",
        type=int,
        default=6,
        help="Stop crawling at N-digit codes (default: 6)",
    )
    args = parser.parse_args()

    if args.rebuild_cache:
        print("Rebuilding HS code cache...", file=sys.stderr)
        build_hs_tree(force_rebuild=True, stop_at_digits=args.stop_at_digits)
        if not args.product:
            print("Cache rebuilt. Provide a product name to look up.", file=sys.stderr)
            return

    if not args.product:
        parser.print_help()
        sys.exit(1)

    lookup = HSLookup()
    result = lookup.lookup(args.product)

    # Output ONLY the JSON object
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
