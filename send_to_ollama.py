import os
import json
import re

OCR_TEXT_FOLDER = "output_text"
OUTPUT_JSON_FOLDER = "output_json"
SUSPECT_NAME_LENGTH = 25

os.makedirs(OUTPUT_JSON_FOLDER, exist_ok=True)

# =========================
# HELPERS
# =========================
def to_float(s):
    """
    Handles Polish decimals (comma) and cleans OCR noise.
    Prevents '1.000' from being treated as 1000.0.
    """
    if not s:
        return 0.0
    # Remove everything except digits, commas, and dots
    s = re.sub(r'[^\d.,]', '', s)
    
    # Standardize: If there's a dot followed by 3 digits at the end, 
    # it's likely a Polish decimal separator mistaken for a thousands separator,
    # or vice versa. In receipts, we usually want the last 2 or 3 digits as decimals.
    if ',' in s and '.' in s:
        s = s.replace('.', '') # Remove thousands dot
        s = s.replace(',', '.') # Convert decimal comma
    elif ',' in s:
        s = s.replace(',', '.')
    
    try:
        val = float(s)
        # Heuristic: If quantity is 1000.0, it's almost certainly 1.000 (1 unit)
        if val == 1000.0: 
            return 1.0
        return val
    except:
        return 0.0

def normalize_line(line):
    # Standardize separators and OCR artifacts
    line = re.sub(r'\bCc\b', 'C', line)
    line = re.sub(r'[©€G©|]', 'C', line) # Common OCR errors for Tax C
    line = re.sub(r'(\d)\s*[%\*xX©|]\s*(\d)', r'\1 x \2', line)
    line = re.sub(r'(\d)\s*[%\*]\s+', r'\1 x ', line)
    line = re.sub(r'[„"""—–]', ' ', line)
    line = re.sub(r'  +', ' ', line).strip()
    return line

def parse_date(text):
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    return ""

def parse_time(text):
    match = re.search(r"\d{2}\.\d{2}\.\d{4}\s+(\d{2}):(\d{2})", text)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return ""

# =========================
# STORE & TRANSACTION PARSERS
# =========================
def parse_store(text):
    store = {"name": "Biedronka", "location": "", "address": "", "tax_id": ""}
    nip = re.search(r"NIP\s+([\d\-]+)", text)
    if nip: store["tax_id"] = nip.group(1)
    
    address = re.search(r"ul\.\s+.+", text)
    if address:
        store["address"] = re.sub(r"\s*NIP.+", "", address.group(0)).strip()

    location = re.search(r"Sklep\s+\d+\s+([\w/\u0104-\u017b ]+?)(?:\d{2,}|Jeronimo)", text)
    if location:
        store["location"] = location.group(1).strip()
    return store

def parse_transaction(text):
    for line in text.splitlines():
        if re.search(r"\d{2}\.\d{2}\.\d{4}", line):
            return {
                "date": parse_date(line),
                "time": parse_time(line),
                "type": "NIEFISKALNY" if "NIEFISKALNY" in text else "FISKALNY"
            }
    return {"date": "", "time": "", "type": ""}

# =========================
# ITEMS PARSER
# =========================
def parse_items(text):
    lines = [l.strip() for l in text.splitlines()]
    total_paid = 0.0
    raw_items = []

    # This pattern captures: Name | Tax | Qty | separator | UnitPrice | Total
    item_pattern = re.compile(
        r"^(?P<name>.+?)\s+"
        r"(?P<tax>[ABCabc]|brak)\s+"
        r"(?P<qty>[\d.,]+)\s*[xX%*]\s*"
        r"(?P<unit>[\d.,]+)\s+"
        r"(?P<total>[\d.,]+)$"
    )

    discount_pattern = re.compile(r"Rabat\s+(-?[\d,\.]+)")

    i = 0
    while i < len(lines):
        line = normalize_line(lines[i])
        
        # Capture Total Paid
        m_total = re.search(r"Suma\s+PLN\s+([\d,.]+)", line, re.IGNORECASE)
        if m_total:
            total_paid = to_float(m_total.group(1))
            i += 1
            continue

        match = item_pattern.search(line)
        if match:
            name = match.group("name").strip()
            qty = to_float(match.group("qty"))
            unit = to_float(match.group("unit"))
            total = to_float(match.group("total"))
            
            # Check next line for Rabat
            discount = 0.0
            final_total = total
            if i + 1 < len(lines):
                next_line = normalize_line(lines[i+1])
                d_match = discount_pattern.search(next_line)
                if d_match:
                    discount = abs(to_float(d_match.group(1)))
                    # Check for a final price after discount line
                    if i + 2 < len(lines):
                        after_discount = to_float(lines[i+2])
                        if after_discount > 0:
                            final_total = after_discount
                            i += 2
                        else:
                            final_total = total - discount
                            i += 1
                    else:
                        final_total = total - discount
                        i += 1

            raw_items.append({
                "name_original": name,
                "name_en": "",
                "quantity": qty,
                "unit_price": unit,
                "total": total,
                "tax": match.group("tax").upper(),
                "discount": discount,
                "final_total": final_total
            })
        i += 1

    return raw_items, total_paid

# =========================
# MAIN EXECUTION
# =========================
def parse_receipt(text):
    store = parse_store(text)
    transaction = parse_transaction(text)
    raw_items, total = parse_items(text)
    
    return {
        "store": store,
        "transaction": transaction,
        "items": raw_items,
        "total_paid": total
    }

def main():
    # Example processing logic
    if not os.path.exists(OCR_TEXT_FOLDER):
        print(f"Directory {OCR_TEXT_FOLDER} not found.")
        return

    for filename in os.listdir(OCR_TEXT_FOLDER):
        if filename.endswith(".txt"):
            with open(os.path.join(OCR_TEXT_FOLDER, filename), "r", encoding="utf-8") as f:
                content = f.read()
                result = parse_receipt(content)
                
                output_path = os.path.join(OUTPUT_JSON_FOLDER, filename.replace(".txt", ".json"))
                with open(output_path, "w", encoding="utf-8") as out:
                    json.dump(result, out, indent=2, ensure_ascii=False)
                print(f"Processed: {filename} -> Total: {result['total_paid']} PLN")

if __name__ == "__main__":
    main()