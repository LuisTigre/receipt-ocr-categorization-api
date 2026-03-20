import argparse
from pathlib import Path
import cv2
import numpy as np
import pytesseract
import pandas as pd
from PIL import Image

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

def preprocess_image(image):
    upscaled = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return enhanced

def extract_dataframe(image_path: Path, lang: str = "pol+eng") -> pd.DataFrame:
    """
    Use Tesseract TSV output to get word-level bounding boxes.
    Returns a clean DataFrame with one row per word including
    its position on the page.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Could not read: {image_path}")

    processed  = preprocess_image(img)
    pil_image  = Image.fromarray(processed)

    # image_to_data returns TSV with columns:
    # level, page_num, block_num, par_num, line_num, word_num,
    # left, top, width, height, conf, text
    tsv = pytesseract.image_to_data(
        pil_image,
        lang=lang,
        config="--psm 6",
        output_type=pytesseract.Output.DATAFRAME
    )

    # Clean up — remove empty words and low confidence
    df = tsv[tsv["conf"] > 30].copy()
    df = df[df["text"].notna()]
    df = df[df["text"].str.strip() != ""]
    df = df.reset_index(drop=True)

    return df

def reconstruct_lines(df: pd.DataFrame) -> list[dict]:
    """
    Group words by line_num and reconstruct each line as a dict with:
    - text: full line text
    - words: list of individual words
    - y_pos: vertical position on page
    - x_positions: list of x positions per word
    """
    lines = []
    for (block, par, line), group in df.groupby(["block_num", "par_num", "line_num"]):
        group = group.sort_values("left")
        words = group["text"].tolist()
        x_pos = group["left"].tolist()
        y_pos = group["top"].mean()

        lines.append({
            "text":       " ".join(str(w) for w in words),
            "words":      words,
            "x_positions": x_pos,
            "y_pos":      y_pos
        })

    # Sort top to bottom
    lines.sort(key=lambda l: l["y_pos"])
    return lines

def detect_receipt_columns(lines: list[dict]) -> pd.DataFrame:
    """
    Detect the table structure of the receipt.
    Receipt columns are: Nazwa | PTU | Ilość | Cena | Wartość
    We detect column boundaries by finding the header line
    then use x positions to assign each word to a column.
    """
    # Find header line
    header_idx  = None
    col_anchors = {}

    for idx, line in enumerate(lines):
        text = line["text"]
        if re.search(r'Nazwa', text, re.IGNORECASE):
            header_idx = idx
            words  = line["words"]
            x_pos  = line["x_positions"]
            for word, x in zip(words, x_pos):
                w = word.strip().lower()
                if "nazwa"   in w: col_anchors["name"]     = x
                if "ptu"     in w: col_anchors["tax"]      = x
                if "ilo"     in w: col_anchors["quantity"]  = x
                if "cena"    in w: col_anchors["unit_price"] = x
                if "warto"   in w: col_anchors["total"]    = x
            break

    if not col_anchors or header_idx is None:
        print("   [WARN] Could not detect receipt columns — falling back to raw text")
        return None

    print(f"   [COLS] Detected column anchors: {col_anchors}")

    # Find footer boundary
    footer_idx = len(lines)
    for idx, line in enumerate(lines):
        if re.search(r'Sprzeda[żz]', line["text"], re.IGNORECASE):
            footer_idx = idx
            break

    # Process product lines
    product_lines = lines[header_idx + 1 : footer_idx]
    records = []

    def nearest_col(x, anchors):
        """Assign a word to the nearest column anchor."""
        return min(anchors, key=lambda col: abs(anchors[col] - x))

    for line in product_lines:
        if not line["words"]:
            continue

        # Build a dict of col -> words for this line
        row = {col: [] for col in col_anchors}
        for word, x in zip(line["words"], line["x_positions"]):
            col = nearest_col(x, col_anchors)
            row[col].append(word)

        record = {col: " ".join(words).strip() for col, words in row.items()}
        record["raw_line"] = line["text"]
        records.append(record)

    return pd.DataFrame(records)

def to_float(s):
    if not s:
        return None
    s = re.sub(r'[^\d.,]', '', str(s))
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        val = float(s)
        if val > 100 and val == int(val):
            return round(val / 100, 2)
        return val
    except:
        return None

def clean_structured_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply pandas operations to clean and validate the structured receipt data.
    """
    import re

    # Convert numeric columns
    for col in ["quantity", "unit_price", "total"]:
        if col in df.columns:
            df[col] = df[col].apply(to_float)

    # Fix quantity — values > 100 are almost certainly misread decimals
    if "quantity" in df.columns:
        df["quantity"] = df["quantity"].apply(
            lambda q: round(q / 1000, 3) if q and q > 100 else q
        )

    # Verify total = quantity x unit_price
    if all(c in df.columns for c in ["quantity", "unit_price", "total"]):
        df["expected_total"] = (df["quantity"] * df["unit_price"]).round(2)
        df["total_ok"]       = df.apply(
            lambda r: abs((r["expected_total"] or 0) - (r["total"] or 0)) < 0.02,
            axis=1
        )
        mismatches = df[~df["total_ok"] & df["quantity"].notna()]
        if not mismatches.empty:
            print(f"\n   [AUDIT] {len(mismatches)} total mismatch(es) detected:")
            for _, row in mismatches.iterrows():
                print(
                    f"      {row.get('name','?')} | "
                    f"qty={row['quantity']} x price={row['unit_price']} "
                    f"= {row['expected_total']} but got {row['total']}"
                )

    # Remove header/noise rows — rows where name looks like a header word
    if "name" in df.columns:
        noise = {"nazwa", "ptu", "ilosc", "cena", "wartosc", "", "niefiskalny"}
        df = df[~df["name"].str.lower().str.strip().isin(noise)]

    return df.reset_index(drop=True)

def dataframe_to_json_items(df: pd.DataFrame) -> list[dict]:
    """Convert structured DataFrame to the JSON items format."""
    items = []
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        items.append({
            "product":    name,
            "tax":        str(row.get("tax", "")).strip(),
            "quantity":   row.get("quantity"),
            "unit_price": row.get("unit_price"),
            "total":      row.get("total"),
            "product_en": ""
        })
    return items

import re

def get_input_files(documents_folder: Path):
    documents_folder = Path(documents_folder)
    if not documents_folder.exists() or not documents_folder.is_dir():
        raise FileNotFoundError(f"Input folder not found: {documents_folder}")
    return sorted(
        [p for p in documents_folder.iterdir()
         if p.suffix.lower() in SUPPORTED_FORMATS]
    )

def convert_images_to_text(documents_folder: Path, output_folder: Path):
    output_folder.mkdir(parents=True, exist_ok=True)
    files = get_input_files(documents_folder)

    if not files:
        print(f"[WARN] No image files found in {documents_folder}")
        return 0

    print(f"[INFO] Found {len(files)} image(s) in {documents_folder}")

    processed_count = 0
    for idx, image_file in enumerate(files, start=1):
        print(f"\n[{idx}/{len(files)}] Processing: {image_file.name}")
        try:
            # Step 1 — get word-level dataframe from Tesseract
            df_raw = extract_dataframe(image_file)
            print(f"   [OCR] {len(df_raw)} words detected")

            # Step 2 — reconstruct lines from word positions
            lines = reconstruct_lines(df_raw)
            print(f"   [OCR] {len(lines)} lines reconstructed")

            # Step 3 — detect table columns and build structured DataFrame
            df_structured = detect_receipt_columns(lines)

            if df_structured is not None and not df_structured.empty:
                # Step 4 — clean and validate with pandas
                df_clean = clean_structured_df(df_structured)
                print(f"   [OK] {len(df_clean)} product rows detected")

                # Step 5 — save as JSON
                items = dataframe_to_json_items(df_clean)
                output_json = output_folder / f"{image_file.stem}.json"
                import json
                output_json.write_text(
                    json.dumps(
                        {"items": items, "source": image_file.name},
                        ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8"
                )
                print(f"   [OK] Saved -> {output_json}")

                # Also save raw text for optimizer reference
                output_txt = output_folder / f"{image_file.stem}.txt"
                raw_text = "\n".join(l["text"] for l in lines)
                output_txt.write_text(raw_text, encoding="utf-8")
                print(f"   [OK] Raw text -> {output_txt}")

            else:
                # Fallback to raw text if column detection fails
                print("   [FALLBACK] Using raw text output")
                text = pytesseract.image_to_string(
                    Image.fromarray(
                        preprocess_image(cv2.imread(str(image_file)))
                    ),
                    lang="pol+eng",
                    config="--psm 6"
                )
                output_txt = output_folder / f"{image_file.stem}.txt"
                output_txt.write_text(text.strip(), encoding="utf-8")
                print(f"   [OK] Saved -> {output_txt}")

            processed_count += 1

        except Exception as e:
            print(f"   [ERROR] {e}")
            continue

    print("\n[DONE] All images processed!")
    return processed_count

def main():
    parser = argparse.ArgumentParser(description="OCR image files into structured JSON")
    parser.add_argument("--input",  default="documents",   help="Input folder with image files")
    parser.add_argument("--output", default="output_text", help="Output folder for results")
    args = parser.parse_args()

    convert_images_to_text(Path(args.input), Path(args.output))

if __name__ == "__main__":
    main()
