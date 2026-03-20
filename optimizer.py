import json
import requests
import os
import re
from pathlib import Path

INPUT_FOLDER    = "output_json_translated"
OCR_FOLDER      = "output_text"
OUTPUT_FOLDER   = "output_json_optimized"
OLLAMA_URL      = "http://100.104.103.64:11434/api/generate"
MODEL_NAME      = "llama3.2"
REQUEST_TIMEOUT = 120

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# =========================
# FIND MATCHING OCR FILE
# =========================
def find_ocr_file(json_filename):
    stem = Path(json_filename).stem
    ocr_folder = Path(OCR_FOLDER)

    exact = ocr_folder / f"{stem}.txt"
    if exact.exists():
        return exact.read_text(encoding="utf-8")

    for txt_file in ocr_folder.glob("*.txt"):
        if stem.lower() in txt_file.stem.lower() or txt_file.stem.lower() in stem.lower():
            print(f"   [OCR] Matched -> {txt_file.name}")
            return txt_file.read_text(encoding="utf-8")

    print(f"   [WARN] No OCR text file found for '{stem}'")
    return ""

# =========================
# EXTRACT PRODUCT SECTION
# =========================
def extract_product_section(ocr_text):
    lines     = ocr_text.splitlines()
    start_idx = None
    end_idx   = None

    for idx, line in enumerate(lines):
        if re.search(r'Nazwa', line, re.IGNORECASE):
            start_idx = idx + 1
        if re.search(r'Sprzeda[żz]\s+opodatkowana', line, re.IGNORECASE):
            end_idx = idx
            break

    if start_idx is None:
        for idx, line in enumerate(lines):
            if re.search(r'NIP\s+[\d\-]+', line):
                start_idx = idx + 3
                break

    if start_idx is None:
        start_idx = 0
    if end_idx is None:
        end_idx = len(lines)

    return "\n".join(lines[start_idx:end_idx])

# =========================
# SMART OCR CHUNKER
# =========================
def smart_chunk_ocr(ocr_text, n_products):
    product_section = extract_product_section(ocr_text)
    lines = [l for l in product_section.splitlines() if l.strip()]

    # Looser pattern — any line with text followed by number and x or %
    product_line_pattern = re.compile(
        r'^.{2,}\s+[\d.,]+\s*[xX%]',
        re.IGNORECASE
    )

    block_starts = []
    for idx, line in enumerate(lines):
        if product_line_pattern.match(line.strip()):
            block_starts.append(idx)

    if len(block_starts) == n_products:
        chunks = []
        for i, start in enumerate(block_starts):
            end = block_starts[i + 1] if i + 1 < len(block_starts) else len(lines)
            chunks.append("\n".join(lines[start:end]))
        print(f"   [CHUNK] Smart chunking OK — {len(chunks)} blocks detected")
        return chunks

    print(f"   [WARN] Smart chunking found {len(block_starts)} blocks, "
          f"expected {n_products} — falling back to equal split")
    chunk_size = max(1, len(lines) // n_products)
    chunks = []
    for i in range(n_products):
        start = i * chunk_size
        end   = start + chunk_size if i < n_products - 1 else len(lines)
        chunks.append("\n".join(lines[start:end]))
    return chunks

# =========================
# OPTIMIZE SINGLE ITEM
# =========================
def optimize_single_item(item, ocr_chunk, item_index, total_items):
    prompt = f"""You are a receipt data quality checker for a Polish supermarket receipt.

Below is the RAW OCR text section for ONE product:
---
{ocr_chunk}
---

Extracted product data:
- product name: {item.get('product', '')}
- product_en (English translation): {item.get('product_en', '')}
- quantity: {item.get('quantity', '')}
- unit_price: {item.get('unit_price', '')}
- total: {item.get('total', '')}

Your tasks:

1. Fix the product name — remove OCR noise, tax letters, percentage signs
2. Fix product_en — correct or improve the English translation
3. Verify and fix quantity, unit_price and total using this logic:
   - quantity x unit_price MUST equal total
   - Use common sense — a plastic bag cannot cost 100 PLN, water cannot cost 1000 PLN
   - If unit_price and total are swapped, swap them back
   - If unit_price is missing a decimal point (e.g. 079 instead of 0.79), fix it
   - If quantity looks like 1000 but product is sold as 1 unit, correct it to 1.0
   - If quantity looks like 1734 but 1.734 x unit_price = total, correct to 1.734
   - Always verify: quantity x unit_price = total — if not, find which is wrong and fix it
   - Maximum realistic price for a single supermarket item is 200 PLN
   - If a value exceeds 200 PLN and seems wrong, divide by 100 to fix missing decimal

4. Return ONLY a JSON object with these exact fields:
product, product_en, quantity, unit_price, total

No explanation. No markdown. Just the JSON object."""

    data = {
        "model":   MODEL_NAME,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.1}
    }

    try:
        print(
            f"   [{item_index}/{total_items}] "
            f"Checking: {item.get('product', '')}...",
            end=" ", flush=True
        )

        response = requests.post(OLLAMA_URL, json=data, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        raw = response.json().get("response", "").strip()

        start = raw.find("{")
        end   = raw.rfind("}")
        if start != -1 and end != -1:
            result = json.loads(raw[start:end+1])

            # Local sanity check — verify and fix after Ollama responds
            try:
                qty   = float(result.get("quantity",   0) or 0)
                price = float(result.get("unit_price", 0) or 0)
                total = float(result.get("total",      0) or 0)

                calculated = round(qty * price, 2)

                if total > 0 and abs(calculated - total) > 0.05:

                    # Try swapping unit_price and total
                    if abs(round(qty * total, 2) - price) < 0.05:
                        print(f"\n   [SWAP] unit_price <-> total swapped", end=" ")
                        result["unit_price"] = total
                        result["total"]      = price

                    # Fix missing decimal on unit_price
                    elif price > 100 and price == int(price):
                        fixed = round(price / 100, 2)
                        if abs(round(qty * fixed, 2) - total) < 0.05:
                            print(f"\n   [FIX] unit_price: {price} -> {fixed}", end=" ")
                            result["unit_price"] = fixed

                    # Fix missing decimal on quantity
                    elif qty > 100 and qty == int(qty):
                        fixed = round(qty / 1000, 3)
                        if abs(round(fixed * price, 2) - total) < 0.05:
                            print(f"\n   [FIX] quantity: {qty} -> {fixed}", end=" ")
                            result["quantity"] = fixed

                    # Fix missing decimal on total
                    elif total > 200 and total == int(total):
                        fixed = round(total / 100, 2)
                        if abs(round(qty * price, 2) - fixed) < 0.05:
                            print(f"\n   [FIX] total: {total} -> {fixed}", end=" ")
                            result["total"] = fixed

            except (TypeError, ValueError):
                pass

            print("OK")
            return result

        print("PARSE FAILED")
        return None

    except Exception as e:
        print(f"ERROR: {e}")
        return None

# =========================
# PROCESS FILE
# =========================
def optimize_file(input_path, output_path):
    source_path = output_path if output_path.exists() else input_path

    with open(source_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print(f"   [WARN] No items in {input_path.name}")
        return

    # Find first unverified item
    first_unverified_idx = None
    for idx, item in enumerate(items):
        if not item.get("_verified", False):
            first_unverified_idx = idx
            break

    if first_unverified_idx is None:
        print(f"   [COMPLETE] All items already verified in {input_path.name}")
        return

    # Load OCR text
    ocr_text = find_ocr_file(input_path.name)
    if not ocr_text:
        print(f"   [WARN] No OCR source — cannot verify")
        return

    # Smart chunk OCR by number of products
    n_products = len(items)
    chunks     = smart_chunk_ocr(ocr_text, n_products)

    ocr_chunk = (
        chunks[first_unverified_idx]
        if first_unverified_idx < len(chunks)
        else ocr_text
    )

    item = items[first_unverified_idx]

    print(f"\n   Item {first_unverified_idx + 1}/{n_products}: "
          f"'{item.get('product', '')}'")
    print(f"   OCR chunk:")
    for line in ocr_chunk.splitlines():
        print(f"      | {line}")
    print()

    result = optimize_single_item(
        item,
        ocr_chunk,
        first_unverified_idx + 1,
        n_products
    )

    changes = []
    if result:
        for field in ["product", "product_en", "quantity", "unit_price", "total"]:
            old_val = str(item.get(field, ""))
            new_val = str(result.get(field, ""))
            if old_val != new_val:
                changes.append(
                    f"Item {first_unverified_idx+1} '{field}': "
                    f"'{old_val}' -> '{new_val}'"
                )
        result["_verified"] = True
        items[first_unverified_idx] = result
    else:
        items[first_unverified_idx]["_verified"] = True

    data["items"] = items

    existing_changes        = data.get("_optimizer_changes", [])
    data["_optimizer_changes"] = existing_changes + changes

    verified_count = sum(1 for i in items if i.get("_verified", False))
    remaining      = n_products - verified_count
    all_verified   = remaining == 0
    data["_optimizer"] = "complete" if all_verified else "in_progress"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if changes:
        print(f"   [CHANGED]")
        for c in changes:
            print(f"        - {c}")
    else:
        print(f"   [NO CHANGES]")

    print(f"   Progress: {verified_count}/{n_products} verified, "
          f"{remaining} remaining")

    if all_verified:
        print(f"   [COMPLETE] All items verified!")

# =========================
# MAIN
# =========================
def main():
    files = sorted(Path(INPUT_FOLDER).glob("*.json"))

    if not files:
        print(f"[WARN] No JSON files found in {INPUT_FOLDER}")
        return

    print(f"[INFO] Found {len(files)} file(s)\n")

    for idx, input_file in enumerate(files, start=1):
        output_file = Path(OUTPUT_FOLDER) / input_file.name
        print(f"[{idx}/{len(files)}] Optimizing: {input_file.name}")
        try:
            optimize_file(input_file, output_file)
        except Exception as e:
            print(f"   [ERROR] {e}")
        print()

    print("[DONE] Run complete!")
    print(f"       Run again to process the next product in each file.")
    print(f"       Results saved to: {OUTPUT_FOLDER}/")

if __name__ == "__main__":
    main()