import os
import json
import re

# Configuration
OCR_TEXT_FOLDER = "output_text"
OUTPUT_JSON_FOLDER = "output_json"
os.makedirs(OUTPUT_JSON_FOLDER, exist_ok=True)

# =========================
# HELPERS
# =========================
def to_float(s, is_price=False):
    if not s: return 0.0
    clean_s = str(s).strip().lower()
    
    # Biedronka OCR Hallucination Dictionary
    # Added '1,9000' and '1.9000' specifically for this missing item
    hallucinations = ['ono', 'ooo', '0oo', 'o.oo', 'o,oo', '0.00', '1,9000', '1.9000', '1,0000', '1.0000', '1000']
    if clean_s in hallucinations:
        return 1.0
        
    clean_s = re.sub(r'[^\d.,]', '', clean_s)
    if ',' in clean_s:
        if '.' in clean_s: clean_s = clean_s.replace('.', '')
        clean_s = clean_s.replace(',', '.')
    
    try:
        val = float(clean_s)
        if is_price and val > 100.0 and '.' not in str(s) and ',' not in str(s):
            val = val / 100.0
        return round(val, 2)
    except:
        return 0.0

def normalize_line(line):
    # 1. Strip leading junk (Fixes lowercase 'n' starts)
    line = re.sub(r'^[^\w\d]+', '', line)
    
    # 2. TREAT QUOTES AS SEPARATORS
    # Turn " and „ into a pipe '|' so the regex has a clear wall
    line = re.sub(r'["„]+', '|', line)
    
    # 3. Clean dashes and standardized tax markers
    line = re.sub(r'[—–_]', ' ', line)
    line = re.sub(r'[\(=/.]\s*([ABCabc])\b', r' \1 ', line)
    line = re.sub(r'[©€G]', ' C ', line)
    
    # 4. Standardize quantity separators (x, %, *)
    line = re.sub(r'[%\*xX]{1,2}', ' x ', line)
    
    return re.sub(r'\s+', ' ', line).strip()

# =========================
# PARSER
# =========================
def parse_items(text):
    lines = [l.strip() for l in text.splitlines()]
    raw_items = []
    total_paid = 0.0

    # NEW AGGRESSIVE PATTERN:
    # 1. Name captures everything until a Pipe (|) or a Tax Letter (A,B,C)
    # 2. Tax is now optional (defaults to 'A' if missing, which is common for cleaning supplies)
    item_pattern = re.compile(
        r"^(?P<name>.+?)"               # Capture name
        r"(?:\s+|\|)"                   # Separator (space or our pipe)
        r"(?P<tax>[ABCabc]|brak|)\s*"   # Tax (now allows empty match)
        r"(?P<qty>[a-zA-Z\d.,]+)\s*"    # Quantity
        r"(?:x|X|%|)\s*"                # Optional separator
        r"(?P<unit>[\d.,]+)\s+"         # Unit Price
        r"(?P<total>[\d.,]+)$"          # Total Price
    )

    i = 0
    while i < len(lines):
        line = normalize_line(lines[i])
        
        if "Suma PLN" in line:
            total_paid = to_float(line.split()[-1], is_price=True)
            i += 1
            continue

        match = item_pattern.search(line)
        if match:
            # If tax was missing in OCR, we assume 'A' for industrial/cleaning items
            tax_val = match.group("tax").strip().upper() or "A"
            
            raw_items.append({
                "name_original": match.group("name").strip(),
                "quantity": to_float(match.group("qty"), is_price=False),
                "unit_price": to_float(match.group("unit"), is_price=True),
                "total": to_float(match.group("total"), is_price=True),
                "tax": tax_val
            })
        i += 1
    return raw_items, total_paid

# =========================
# MAIN
# =========================
def main():
    if not os.path.exists(OCR_TEXT_FOLDER): return
    files = [f for f in os.listdir(OCR_TEXT_FOLDER) if f.endswith(".txt")]
    for filename in files:
        with open(os.path.join(OCR_TEXT_FOLDER, filename), "r", encoding="utf-8") as f:
            content = f.read()
        items, total = parse_items(content)
        output_data = {"items": items, "total_paid": total}
        output_path = os.path.join(OUTPUT_JSON_FOLDER, filename.replace(".txt", ".json"))
        with open(output_path, "w", encoding="utf-8") as out_f:
            json.dump(output_data, out_f, indent=2, ensure_ascii=False)
        print(f"✅ {filename}: Found {len(items)} items.")

if __name__ == "__main__":
    main()