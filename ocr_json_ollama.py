import json
import requests
import os
from pathlib import Path

INPUT_FOLDER    = "output_json"
OUTPUT_FOLDER   = "output_json_translated"
OLLAMA_URL      = "http://100.104.103.64:11434/api/generate"
MODEL_NAME      = "llama3.2"
REQUEST_TIMEOUT = 120

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def translate_single(name):
    prompt = (
        f"This is a product name from a Polish supermarket receipt: '{name}'\n"
        f"It may contain OCR errors and abbreviations.\n"
        f"Reply with ONLY the English translation or best guess. "
        f"No explanation. No punctuation. Just the product name in English."
    )

    data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1}
    }

    try:
        response = requests.post(OLLAMA_URL, json=data, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        print(f"   [ERROR] {name}: {e}")
        return ""

def process_file(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print(f"   [WARN] No items in {input_path.name}")
        return

    for idx, item in enumerate(items):
        name = item.get("product", "").strip()
        if not name:
            item["product_en"] = ""
            continue

        translation = translate_single(name)
        item["product_en"] = translation
        print(f"   [{idx+1}/{len(items)}] {name} -> {translation}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    translated = sum(1 for i in items if i.get("product_en"))
    print(f"   [OK] {translated}/{len(items)} items translated")

def main():
    files = sorted(Path(INPUT_FOLDER).glob("*.json"))

    if not files:
        print(f"[WARN] No JSON files found in {INPUT_FOLDER}")
        return

    print(f"[INFO] Found {len(files)} file(s)\n")

    for idx, input_file in enumerate(files, start=1):
        output_file = Path(OUTPUT_FOLDER) / input_file.name
        print(f"[{idx}/{len(files)}] Processing: {input_file.name}")
        try:
            process_file(input_file, output_file)
        except Exception as e:
            print(f"   [ERROR] {e}")
        print()

    print("[DONE] All files processed!")
    print(f"       Results saved to: {OUTPUT_FOLDER}/")

if __name__ == "__main__":
    main()