import argparse
import json
import re
from pathlib import Path

# =========================
# CONFIGURATION
# =========================
DEFAULT_OCR_TEXT_FOLDER   = Path("output_text")
DEFAULT_OUTPUT_JSON_FOLDER = Path("output_json")

RETAILER_MAP = {
    "7791011327":             "Biedronka",
    "5260210288":             "McDonald's",
    "5260001222":             "Lidl",
    "6762464543":             "Uber Eats",
    "5270203393":             "KFC / Burger King",
    "CODZIENNIE NISKIE CENY": "Biedronka",
    "RESTAURACJA":            "Restaurant",
}

MAX_ITEM_PRICE = 200.0

# =========================
# LINE CLEANER
# =========================
def clean_line(line):
    """
    Strip OCR noise before regex matching.
    Fixes tax letters, quantity separators, stray characters.
    """
    # Remove stray quote/dash noise
    line = re.sub(r'[„"""—–]', ' ', line)
    # Normalize tax letter noise: © € -> C
    line = re.sub(r'\b[©€]\b', 'C', line)
    # Fix (A =A [A {A -> A
    line = re.sub(r'[(=\[{\\]([AaBbCc])\b', r'\1', line)
    line = re.sub(r'[(=\[{\\]a\b', 'A', line)
    # Fix Cc -> C
    line = re.sub(r'\bCc\b', 'C', line)
    # Normalize quantity separator: 1000% 1000x 1000* -> 1000 x
    line = re.sub(r'(\d)\s*[%\*xX]\s*(\d)', r'\1 x \2', line)
    line = re.sub(r'(\d)\s*[%\*xX]+\s+', r'\1 x ', line)
    # Fix "ono" OCR noise for 1.000
    line = re.sub(r'\bono\b', '1.000', line, flags=re.IGNORECASE)
    # Remove stray pipe characters
    line = re.sub(r'\|\s*', ' ', line)
    # Collapse multiple spaces
    line = re.sub(r'  +', ' ', line).strip()
    return line

# =========================
# PRICE FIXING RULES
# =========================
def fix_decimal(value):
    """
    Fix values where OCR dropped the decimal point.
    079 -> 0.79, 245 -> 2.45, 2649 -> 26.49, 1399 -> 13.99
    """
    if value is None:
        return value
    if value > MAX_ITEM_PRICE and value == int(value):
        return round(value / 100, 2)
    if value > 20 and value == int(value) and value <= MAX_ITEM_PRICE * 10:
        return round(value / 100, 2)
    return value

def fix_quantity(qty):
    """
    Fix quantities where dot is a thousands separator.
    1734 -> 1.734, 1701 -> 1.701, 1000 -> 1.000
    """
    if qty is None:
        return qty
    if qty > 100:
        return round(qty / 1000, 3)
    return qty

def verify_and_fix(qty, unit_price, total):
    """
    Main price verification:
    1. Fix decimal errors on all three values
    2. Try all combinations to find which makes qty x unit_price = total
    3. No supermarket item costs > MAX_ITEM_PRICE PLN
    4. Swap unit_price and total if needed
    """
    qty_fixed  = fix_quantity(qty)
    unit_fixed = fix_decimal(unit_price) if unit_price else unit_price
    total_fixed = fix_decimal(total)

    def close(a, b):
        if a is None or b is None:
            return False
        return abs(a - b) < 0.02

    # Already correct after fixing decimals
    if unit_fixed and total_fixed:
        if close(round(qty_fixed * unit_fixed, 2), total_fixed):
            return qty_fixed, unit_fixed, total_fixed

    # Try original qty with fixed prices
    if unit_price and close(round(qty * unit_fixed, 2), total_fixed):
        return qty, unit_fixed, total_fixed

    # Try swapping unit_price and total
    if unit_fixed and total_fixed:
        if close(round(qty_fixed * total_fixed, 2), unit_fixed):
            return qty_fixed, total_fixed, unit_fixed

    # Try fixing total decimal with correct unit_price
    if unit_price:
        for t in [total, total * 100, total / 100]:
            t = round(t, 2)
            if close(round(qty_fixed * unit_fixed, 2), t):
                return qty_fixed, unit_fixed, t

    # Try fixing unit_price decimal
    if unit_price:
        for u in [unit_price, unit_price / 10, unit_price / 100]:
            u = round(u, 2)
            if close(round(qty_fixed * u, 2), total_fixed):
                return qty_fixed, u, total_fixed

    # Best effort
    return qty_fixed, unit_fixed, total_fixed

# =========================
# HELPERS
# =========================
def to_float(s):
    if s is None or str(s).strip() == "":
        return 0.0
    clean = re.sub(r"[^\d.,-]", "", str(s)).replace(",", ".")
    try:
        return round(float(clean), 2)
    except ValueError:
        return 0.0

def identify_retailer(text):
    text_upper = text.upper()

    nip_match = re.search(r"NIP\s*[:\s]*([\d\-]+)", text_upper)
    if nip_match:
        nip_clean = re.sub(r"\D", "", nip_match.group(1))
        if nip_clean in RETAILER_MAP:
            return RETAILER_MAP[nip_clean], nip_clean

    for key, name in RETAILER_MAP.items():
        if key.upper() in text_upper:
            return name, "KeywordMatch"

    return "Generic Retailer", "Unknown"

# =========================
# RECEIPT PARSER
# =========================
def parse_receipt(content):
    store_name, store_id = identify_retailer(content)
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    item_regex = re.compile(
        r"(?P<name>.+?)\s+"
        r"(?P<qty>[\d.,]+)"
        r"(?:\s*[xX*%]\s*(?P<unit>[\d.,]+))?\s+"
        r"(?P<total>[\d.,-]+)$"
    )

    skip_keywords = {
        "SUMA", "TOTAL", "RAZEM", "KARTA", "NIP", "SKLEP",
        "PTU", "PARAGON", "SPRZEDAZ", "SPRZEDAŻ", "STRONA",
        "JERONIMO", "KASJER", "KASA", "NUMER", "TRANSAKCJI",
        "NIEFISKALNY", "FISKALNY", "NAZWA"
    }

    skip_patterns = [
        re.compile(r"^\d{2}\.\d{2}\.\d{4}"),
        re.compile(r"^\d{10,}"),
        re.compile(r"^\d{4}/\d+/"),
        re.compile(r"^[O0]\s*$"),
    ]

    extracted_items = []
    grand_total     = 0.0
    discount_next   = False
    last_item_idx   = None

    for raw_line in lines:
        # Clean OCR noise first
        line  = clean_line(raw_line)
        upper = line.upper()

        # Capture grand total
        if any(k in upper for k in ["SUMA PLN", "TOTAL", "RAZEM"]):
            candidates = re.findall(r"[\d.,]+", line)
            if candidates:
                val = to_float(candidates[-1])
                if val > grand_total:
                    grand_total = val
            continue

        # Skip header/footer lines
        if any(k in upper for k in skip_keywords):
            continue
        if any(p.match(line) for p in skip_patterns):
            continue

        # Handle Rabat discount line
        rabat_match = re.search(r"Rabat\s+(-?[\d.,]+)", line, re.IGNORECASE)
        if rabat_match and last_item_idx is not None:
            discount = abs(to_float(rabat_match.group(1)))
            if discount > 50:
                discount = round(discount / 100, 2)
            extracted_items[last_item_idx]["discount"]    = -discount
            extracted_items[last_item_idx]["final_total"] = round(
                extracted_items[last_item_idx]["total"] - discount, 2
            )
            discount_next = True
            continue

        # Line after Rabat is the confirmed final price
        if discount_next and last_item_idx is not None:
            final = to_float(line)
            if final > 0:
                extracted_items[last_item_idx]["final_total"] = final
            discount_next = False
            continue

        # Try to match product line
        match = item_regex.search(line)
        if not match:
            continue

        name = match.group("name").strip()
        if any(k in name.upper() for k in skip_keywords):
            continue

        qty        = to_float(match.group("qty"))
        unit_price = to_float(match.group("unit")) if match.group("unit") else None
        total      = to_float(match.group("total"))

        # Apply full price verification and fixing
        qty, unit_price, total = verify_and_fix(qty, unit_price, total)

        item = {
            "product":     name,
            "quantity":    qty,
            "unit_price":  unit_price,
            "total":       total,
            "discount":    0.0,
            "final_total": total
        }

        extracted_items.append(item)
        last_item_idx = len(extracted_items) - 1

    return {
        "retailer":    store_name,
        "retailer_id": store_id,
        "items":       extracted_items,
        "total_paid":  round(grand_total, 2),
    }

# =========================
# FOLDER PROCESSOR
# =========================
def convert_folder_to_json(ocr_text_folder: Path, output_json_folder: Path):
    ocr_text_folder    = Path(ocr_text_folder)
    output_json_folder = Path(output_json_folder)
    output_json_folder.mkdir(parents=True, exist_ok=True)

    if not ocr_text_folder.exists() or not ocr_text_folder.is_dir():
        raise FileNotFoundError(f"OCR text folder not found: {ocr_text_folder}")

    processed = 0
    for path in sorted(ocr_text_folder.glob("*.txt")):
        content = path.read_text(encoding="utf-8")
        result  = parse_receipt(content)

        output_file = output_json_folder / f"{path.stem}.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print(f"[OK] {path.name} -> {result['retailer']} ({len(result['items'])} items)")
        processed += 1

    if processed == 0:
        print(f"[WARN] No .txt files found in {ocr_text_folder}")
    else:
        print(f"[DONE] Converted {processed} receipt(s)")

    return processed

# =========================
# MAIN
# =========================
def main():
    parser = argparse.ArgumentParser(description="Convert OCR text receipts to structured JSON")
    parser.add_argument("--input",  default=DEFAULT_OCR_TEXT_FOLDER,     help="Input folder for OCR text files")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_JSON_FOLDER,   help="Output folder for JSON files")
    args = parser.parse_args()

    convert_folder_to_json(Path(args.input), Path(args.output))

if __name__ == "__main__":
    main()