import json
import os
import time
from pathlib import Path

from ollama import Client

from db import list_categories, list_tags

MODEL_NAME = "gemini-3-flash-preview"

EXTRACTION_PROMPT = """You are a precise receipt data extractor.

This is a Polish supermarket receipt image.

Instructions:
- Read EVERY line of the receipt carefully
- Extract EVERY product listed - do not skip any
- For each product read the exact quantity, unit price and total from the receipt
- The quantity column is labeled \"Ilosc\", unit price is \"Cena\", total is \"Wartosc\"
- Some products have a discount line \"Rabat\" below them - subtract it and store as final_total
- The grand total is labeled \"Suma PLN\" - read it exactly
- Translate each product name to English in product_en
- Do NOT invent or hallucinate products - only extract what is visibly printed

Return ONLY this JSON structure, no explanation, no markdown:
{
  \"retailer\": \"store name from receipt\",
  \"date\": \"YYYY-MM-DD\",
  \"total_paid\": 0.00,
  \"items\": [
    {
      \"product_pl\": \"exact Polish name from receipt\",
      \"product_en\": \"English translation\",
      \"quantity\": 1.0,
      \"unit_price\": 0.00,
      \"total\": 0.00,
      \"discount\": 0.00,
      \"final_total\": 0.00
    }
  ]
}"""

DEFAULT_FALLBACK_CATEGORY = "Other"
DEFAULT_FALLBACK_TAG = "optional"


def get_ollama_client() -> Client:
    api_key = os.environ.get("OLLAMA_API_KEY", "")
    return Client(
        host="https://ollama.com",
        headers={"Authorization": f"Bearer {api_key}"},
    )


def extract_receipt_from_image(image_path: Path, retries: int = 3):
    client = get_ollama_client()

    for attempt in range(retries):
        try:
            print(f"   [ATTEMPT {attempt + 1}/{retries}]", end=" ", flush=True)

            response = client.chat(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT,
                        "images": [str(image_path)],
                    }
                ],
            )

            content = response.message.content.strip()

            if "```" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]

            result = json.loads(content)
            items = result.get("items", [])
            total = result.get("total_paid", 0)

            if not items:
                print("EMPTY - no items extracted, retrying...")
                time.sleep(2)
                continue

            if total <= 0:
                print("WARN - total_paid is 0, retrying...")
                time.sleep(2)
                continue

            print(f"OK - {len(items)} items, {total} PLN")
            return result

        except json.JSONDecodeError as error:
            print(f"JSON ERROR: {error}")
            time.sleep(2)
        except Exception as error:
            print(f"ERROR: {error}")
            time.sleep(2)

    return None


def _get_available_categories():
    rows = list_categories()
    names = [row["name"] for row in rows]
    return names or [DEFAULT_FALLBACK_CATEGORY]


def _get_available_tags():
    rows = list_tags()
    names = [row["name"] for row in rows]
    return names or [DEFAULT_FALLBACK_TAG]


def _fallback_category(categories):
    return DEFAULT_FALLBACK_CATEGORY if DEFAULT_FALLBACK_CATEGORY in categories else categories[0]


def _fallback_tag(tags):
    return DEFAULT_FALLBACK_TAG if DEFAULT_FALLBACK_TAG in tags else tags[0]


def get_category_and_tags(product_name: str, product_en: str, categories=None, tags=None):
    name = product_en if product_en else product_name
    valid_categories = categories or _get_available_categories()
    valid_tags = tags or _get_available_tags()

    prompt = (
        f"You are a supermarket product categorizer.\\n\\n"
        f"Product: '{name}'\\n\\n"
        f"Step 1 - Identify the TYPE of product (e.g., staple food, snack, cleaning product, hygiene product, beverage, etc.)\\n"
        f"Step 2 - Assign exactly ONE category from this list:\\n"
        f"{chr(10).join(f'- {category}' for category in valid_categories)}\\n\\n"
        f"Step 3 - Assign exactly ONE tag from this list:\\n"
        f"{chr(10).join(f'- {tag}' for tag in valid_tags)}\\n\\n"
        f"Rules for tags:\\n"
        f"- 'essential' = basic needs (staple foods, hygiene, cleaning, basic household)\\n"
        f"- 'optional' = snacks, sweets, desserts, sugary drinks, luxury or non-essential items\\n"
        f"- Decide based on the TYPE of product, not the specific brand\\n"
        f"- Never assign both tags\\n"
        f"- If unsure, default to 'essential'\\n\\n"
        f"Reply ONLY in this format:\\n"
        f"category: <category>\\n"
        f"tags: <tag>"
    )

    try:
        response = get_ollama_client().chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.message.content.strip()

        category = _fallback_category(valid_categories)
        parsed_tags = [_fallback_tag(valid_tags)]

        for line in raw.splitlines():
            line_lower = line.strip().lower()

            if line_lower.startswith("category:"):
                value = line_lower.replace("category:", "").strip()
                for valid_category in valid_categories:
                    if valid_category.lower() in value:
                        category = valid_category
                        break

            if line_lower.startswith("tags:"):
                value = line_lower.replace("tags:", "").strip()
                found = []
                for valid_tag in valid_tags:
                    if valid_tag.lower() in value:
                        found.append(valid_tag)
                if found:
                    parsed_tags = found

        return category, parsed_tags

    except Exception as error:
        print(f"   [ERROR] {name}: {error}")
        return _fallback_category(valid_categories), [_fallback_tag(valid_tags)]


def categorize_receipt_data(data: dict):
    items = data.get("items", [])
    if not items:
        return data

    valid_categories = _get_available_categories()
    valid_tags = _get_available_tags()
    fallback_category = _fallback_category(valid_categories)
    fallback_tag = _fallback_tag(valid_tags)

    for item in items:
        if item.get("_item_categorized"):
            continue

        product_name = item.get("product", "").strip()
        product_en = item.get("product_en", "").strip()

        if not product_name and not product_en:
            item["category"] = fallback_category
            item["tags"] = [fallback_tag]
            item["_item_categorized"] = True
            continue

        category, tags = get_category_and_tags(
            product_name,
            product_en,
            categories=valid_categories,
            tags=valid_tags,
        )
        item["category"] = category
        item["tags"] = tags
        item["_item_categorized"] = True

    all_done = all(entry.get("_item_categorized") for entry in items)
    data["_categorized"] = "done" if all_done else "in_progress"
    return data


def save_receipt_json(data: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file_handle:
        json.dump(data, file_handle, indent=2, ensure_ascii=False)
