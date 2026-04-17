# HSN Code Lookup for Saudi Arabian Companies

A Python-based utility for extracting and matching HSN (Harmonized System of Nomenclature) codes for products from Saudi Arabian sources.

## Overview

This project provides tools to:
- Extract product information from web pages and text
- Match products to their corresponding HSN (HS) codes
- Build and cache HS code hierarchies
- Generate Excel reports with HSN codes

## Features

- **Web Scraping**: Extract product information from URLs
- **Text Processing**: Parse product descriptions from raw text
- **Fuzzy Matching**: Intelligently match products to HS codes using string similarity
- **HS Code Hierarchy**: Build and cache HS code trees from Saudi Arabia
- **Excel Integration**: Import products from Excel and export results with matched codes
- **Caching**: Persistent caching of HS code data for performance

## Project Structure

```
├── main.py                    # Main application entry point
├── hsn_matcher.py            # HSN code matching logic
├── hsn_lookup.py             # HS code lookup utilities
├── hsn_tree_builder.py       # Build HS code hierarchy
├── product_extractor.py      # Extract products from URLs/text
├── explore_taxprice.py       # Data exploration tools
├── synonyms.py               # Product name synonyms
├── test_accuracy.py          # Testing and accuracy evaluation
├── hs_codes_sa.json          # Cached HS codes for Saudi Arabia
├── requirements.txt          # Python dependencies
└── Book1.xlsx               # Input Excel file (sample)
```

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`:
  - requests
  - beautifulsoup4
  - fuzzywuzzy
  - python-Levenshtein
  - openpyxl

## Installation

1. Clone the repository:
```bash
git clone https://github.com/ansariamann/hsn.git
cd hsn
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\Activate.ps1
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Run the main application:
```bash
python main.py
```

### Advanced Options

```bash
# Rebuild HS code tree (bypass cache)
python main.py --rebuild-hs-tree

# Verbose output during HS tree crawl
python main.py --verbose-hs-tree

# Stop crawling at specific digit level (e.g., 6 digits)
python main.py --stop-at-digits 6
```

### Input Format

Place your product data in `Book1.xlsx` with the following structure:
- Column A: Product names/descriptions
- The application will match these to HS codes

### Output

Results are saved to `hsn_output.xlsx` with:
- Original product information
- Matched HS codes
- Match confidence scores

## Key Components

### `hsn_matcher.py`
Core matching engine that uses fuzzy string matching to find the best HS code for each product.

### `hsn_tree_builder.py`
Builds and caches the hierarchical structure of HS codes specific to Saudi Arabia.

### `product_extractor.py`
Extracts product information from multiple sources (URLs, Excel files, raw text).

### `hsn_lookup.py`
Provides lookup utilities and helper functions for HS code operations.

## Performance Considerations

- First run will build and cache the HS code tree (`hs_codes_sa.json`)
- Subsequent runs will use the cached data for faster performance
- Use `--rebuild-hs-tree` flag to update the cache if needed

## Testing

Run accuracy tests:
```bash
python test_accuracy.py
```

## License

This project is available on GitHub at https://github.com/ansariamann/hsn

## Contributing

Feel free to submit issues and pull requests to improve this project.
