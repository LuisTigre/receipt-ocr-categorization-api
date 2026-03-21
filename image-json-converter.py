import os
import json
import shutil
import time
from pathlib import Path
from ollama import Client

# =========================
# CONFIGURATION
# =========================
BASE_DIR            = Path(__file__).parent
INPUT_IMAGES_FOLDER = BASE_DIR / "receipt_images"
OUTPUT_JSON_FOLDER  = BASE_DIR / "output_json"
PROCESSED_FOLDER    = BASE_DIR / "processed_images"

# Best vision model available on Ollama cloud for document reading
MODEL_NAME = "gemini-3-flash-preview"

for folder in [INPUT_IMAGES_FOLDER, OUTPUT_JSON_FOLDER, PROCESSED_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)

OLLAMA_CLIENT = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {os.environ.get('OLLAMA_API_KEY', '')}"}
)

# =========================
# PROMPT
# =========================
PROMPT = """You are a precise receipt data extractor.

This is a Polish supermarket receipt image.

Instructions:
- Read EVERY line of the receipt carefully
- Extract EVERY product listed — do not skip any
- For each product read the exact quantity, unit price and total from the receipt
- The quantity column is labeled "Ilość", unit price is "Cena", total is "Wartość"
- Some products have a discount line "Rabat" below them — subtract it and store as final_total
- The grand total is labeled "Suma PLN" — read it exactly
- Translate each product name to English in product_en
- Do NOT invent or hallucinate products — only extract what is visibly printed

Return ONLY this JSON structure, no explanation, no markdown:
{
  "retailer": "store name from receipt",
  "date": "YYYY-MM-DD",
  "total_paid": 0.00,
  "items": [
    {
      "product_pl": "exact Polish name from receipt",
      "product_en": "English translation",
      "quantity": 1.0,
      "unit_price": 0.00,
      "total": 0.00,
      "discount": 0.00,
      "final_total": 0.00
    }
  ]
}"""

# =========================
# PROCESS RECEIPT
# =========================
def process_receipt_with_retry(image_path, retries=3):
    for attempt in range(retries):
        try:
            print(f"   [ATTEMPT {attempt+1}/{retries}]", end=" ", flush=True)

            response = OLLAMA_CLIENT.chat(
                model=MODEL_NAME,
                messages=[{
                    "role":    "user",
                    "content": PROMPT,
                    "images":  [str(image_path)]
                }]
            )

            content = response.message.content.strip()

            # Strip markdown code blocks if present
            if "```" in content:
                start   = content.find("{")
                end     = content.rfind("}") + 1
                content = content[start:end]

            result = json.loads(content)

            # Basic sanity check
            items = result.get("items", [])
            total = result.get("total_paid", 0)

            if not items:
                print(f"EMPTY — no items extracted, retrying...")
                time.sleep(2)
                continue

            if total <= 0:
                print(f"WARN — total_paid is 0, retrying...")
                time.sleep(2)
                continue

            print(f"OK — {len(items)} items, {total} PLN")
            return result

        except json.JSONDecodeError as e:
            print(f"JSON ERROR: {e}")
            time.sleep(2)
        except Exception as e:
            print(f"ERROR: {e}")
            time.sleep(2)

    return None

# =========================
# MAIN
# =========================
def main():
    api_key = os.environ.get("OLLAMA_API_KEY", "")
    if not api_key:
        print("[ERROR] OLLAMA_API_KEY not set.")
        print("        Run: $env:OLLAMA_API_KEY = 'your_key_here'")
        return

    image_files = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.JPG", "*.PNG"]:
        image_files.extend(INPUT_IMAGES_FOLDER.glob(ext))

    if not image_files:
        print(f"[WARN] No images found in {INPUT_IMAGES_FOLDER.absolute()}")
        return

    print(f"[INFO] Found {len(image_files)} image(s)")
    print(f"[INFO] Using model: {MODEL_NAME}\n")

    for img_path in sorted(image_files):
        print(f"[*] Processing: {img_path.name}")
        result = process_receipt_with_retry(img_path)

        if result:
            output_file = OUTPUT_JSON_FOLDER / f"{img_path.stem}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            shutil.move(str(img_path), str(PROCESSED_FOLDER / img_path.name))

            print(f"   [OK] Saved -> {output_file.name}")
        else:
            print(f"   [FAIL] Could not process {img_path.name}")

    print("\n[DONE] Results saved to output_json/")

if __name__ == "__main__":
    main()