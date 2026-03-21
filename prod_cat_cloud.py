import json
import os
from pathlib import Path
from ollama import Client

INPUT_FOLDER = "output_json"  # changed from output_json_translated
MODEL_NAME   = "gemini-3-flash-preview"
# MODEL_NAME   = "gemma3:4b"

os.makedirs(INPUT_FOLDER, exist_ok=True)

# =========================
# OLLAMA CLOUD CLIENT
# =========================
OLLAMA_CLIENT = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {os.environ.get('OLLAMA_API_KEY', '')}"}
)

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
    "work-related",
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
        f"- If no tag fits use 'personal care'\n\n"
        f"Examples:\n"
        f"- 'Coca-Cola Zero' -> category: Food, tags: personal care, optional\n"
        f"- 'Garbage bags 35L' -> category: Housing, tags: home care, essential\n"
        f"- 'Shower gel Nivea' -> category: Hygiene, tags: personal care, essential\n"
        f"- 'Paper towel roll' -> category: Housing, tags: home care, essential\n"
        f"- 'Shopping Bag' -> category: Other, tags: home care, optional\n\n"
        f"Reply in this exact format and nothing else:\n"
        f"category: <category>\n"
        f"tags: <tag1>, <tag2>"
    )

    try:
        response = OLLAMA_CLIENT.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.message.content.strip()

        category = "Other"
        tags     = ["personal care"]

        for line in raw.splitlines():
            line_lower = line.strip().lower()

            if line_lower.startswith("category:"):
                value = line_lower.replace("category:", "").strip()
                for c in CATEGORIES:
                    if c.lower() in value:
                        category = c
                        break

            if line_lower.startswith("tags:"):
                value = line_lower.replace("tags:", "").strip()
                found = []
                for t in TAGS:
                    if t.lower() in value:
                        found.append(t)
                if found:
                    tags = found

        return category, tags

    except Exception as e:
        print(f"   [ERROR] {name}: {e}")
        return "Other", ["personal care"]

# =========================
# PROCESS FILE
# =========================
def process_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Skip if already fully categorized
    if data.get("_categorized") == "done":
        print(f"   [SKIP] Already fully categorized")
        return

    items = data.get("items", [])
    if not items:
        print(f"   [WARN] No items found")
        return

    changed = False
    for idx, item in enumerate(items):
        # Skip already categorized items
        if item.get("_item_categorized"):
            print(f"   [{idx+1}/{len(items)}] [SKIP] {item.get('product_en') or item.get('product', '')}")
            continue

        product_name = item.get("product", "").strip()
        product_en   = item.get("product_en", "").strip()

        if not product_name and not product_en:
            item["category"]          = "Other"
            item["tags"]              = ["personal care"]
            item["_item_categorized"] = True
            changed = True
            continue

        category, tags = get_category_and_tags(product_name, product_en)

        item["category"]          = category
        item["tags"]              = tags
        item["_item_categorized"] = True
        changed = True

        print(
            f"   [{idx+1}/{len(items)}] "
            f"{product_en or product_name}\n"
            f"              -> {category} | {', '.join(tags)}"
        )

    if changed:
        all_done = all(i.get("_item_categorized") for i in items)
        data["_categorized"] = "done" if all_done else "in_progress"

        categorized = sum(1 for i in items if i.get("_item_categorized"))
        print(f"\n   [STATUS] {categorized}/{len(items)} items categorized")
        print(f"   [STATUS] File: {data['_categorized']}")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"   [OK] Updated in place: {file_path.name}")

# =========================
# MAIN
# =========================
def main():
    api_key = os.environ.get("OLLAMA_API_KEY", "")
    if not api_key:
        print("[ERROR] OLLAMA_API_KEY not set.")
        print("        Run: $env:OLLAMA_API_KEY = 'your_key_here'")
        return

    files = sorted(Path(INPUT_FOLDER).glob("*.json"))

    if not files:
        print(f"[WARN] No JSON files found in {INPUT_FOLDER}")
        return

    print(f"[INFO] Found {len(files)} file(s)")
    print(f"[INFO] Model: {MODEL_NAME}")
    print(f"[INFO] Folder: {INPUT_FOLDER}\n")

    for idx, file_path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Categorizing: {file_path.name}")
        try:
            process_file(file_path)
        except Exception as e:
            print(f"   [ERROR] {e}")
        print()

    print("[DONE] All files processed!")
    print(f"       Files updated in place in: {INPUT_FOLDER}/")

if __name__ == "__main__":
    main()