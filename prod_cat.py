import json
import requests
import os
from pathlib import Path

INPUT_FOLDER    = "output_json_translated"
OUTPUT_FOLDER   = "output_json_translated"
OLLAMA_URL      = "http://100.104.103.64:11434/api/generate"
MODEL_NAME      = "llama3.2"
REQUEST_TIMEOUT = 120

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# =========================
# CATEGORIES & TAGS
# =========================
CATEGORIES = [
    "Food",
    "Hygiene",
    "Housing",
    "Transportation",
    "Media",
    "Clothing",
    "Other"
]

TAGS = [
    "personal care",
    "home care",
    "home rental",
    "workwork-related",
    "delivery",
    "bicycle",
    "entertainment",
    "self development",
    "essential",
    "optional"
]

# =========================
# GET CATEGORY & TAGS
# =========================
def get_category_and_tags(product_name, product_en):
    name = product_en if product_en else product_name

    prompt = (
        f"You are a supermarket product categorizer.\n\n"
        f"Product: '{name}'\n\n"
        f"Task 1 — Assign exactly ONE category from this list:\n"
        f"{chr(10).join(f'- {c}' for c in CATEGORIES)}\n\n"
        f"Task 2 — Assign one or more relevant tags from this list:\n"
        f"{chr(10).join(f'- {t}' for t in TAGS)}\n\n"
        f"Rules:\n"
        f"- Category must be exactly one from the list above\n"
        f"- Tags can be one or more from the list above\n"
        f"- If category is unclear use 'Other'\n"
        f"- If no tag fits use 'personal'\n\n"
        f"Examples:\n"
        f"- 'Coca-Cola Zero' -> category: Food, tags: personal, optional\n"
        f"- 'Garbage bags 35L' -> category: Housing, tags: home, essential\n"
        f"- 'Shower gel Nivea' -> category: Hygiene, tags: personal, essential\n"
        f"- 'Paper towel roll' -> category: Housing, tags: home, essential\n\n"
        f"Reply in this exact format and nothing else:\n"
        f"category: <category>\n"
        f"tags: <tag1>, <tag2>"
    )

    data = {
        "model":   MODEL_NAME,
        "prompt":  prompt,
        "stream":  False,
        "options": {"temperature": 0.1}
    }

    try:
        response = requests.post(OLLAMA_URL, json=data, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        raw = response.json().get("response", "").strip()

        # Parse category
        category = "Other"
        tags     = ["personal"]

        for line in raw.splitlines():
            line = line.strip().lower()

            if line.startswith("category:"):
                value = line.replace("category:", "").strip()
                for c in CATEGORIES:
                    if c.lower() in value:
                        category = c
                        break

            if line.startswith("tags:"):
                value = line.replace("tags:", "").strip()
                found = []
                for t in TAGS:
                    if t.lower() in value:
                        found.append(t)
                if found:
                    tags = found

        return category, tags

    except Exception as e:
        print(f"   [ERROR] {name}: {e}")
        return "Other", ["personal"]

# =========================
# PROCESS FILE
# =========================
def process_file(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    if not items:
        print(f"   [WARN] No items in {input_path.name}")
        return

    for idx, item in enumerate(items):
        product_name = item.get("product", "").strip()
        product_en   = item.get("product_en", "").strip()

        if not product_name and not product_en:
            item["category"] = "Other"
            item["tags"]     = ["personal"]
            continue

        category, tags = get_category_and_tags(product_name, product_en)

        item["category"] = category
        item["tags"]     = tags

        print(
            f"   [{idx+1}/{len(items)}] "
            f"{product_en or product_name}\n"
            f"              -> {category} | {', '.join(tags)}"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    categorized = sum(1 for i in items if i.get("category") != "Other")
    other       = sum(1 for i in items if i.get("category") == "Other")
    print(f"\n   [OK] {categorized} categorized, {other} as Other")

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
        print(f"[{idx}/{len(files)}] Categorizing: {input_file.name}")
        try:
            process_file(input_file, output_file)
        except Exception as e:
            print(f"   [ERROR] {e}")
        print()

    print("[DONE] All files processed!")
    print(f"       Results saved to: {OUTPUT_FOLDER}/")

if __name__ == "__main__":
    main()