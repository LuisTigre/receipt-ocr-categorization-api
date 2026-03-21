"""
Uncategorize Helper Script
Removes category and tags from all products in output_json folder
"""

import json
from pathlib import Path

# =========================
# CONFIGURATION
# =========================
BASE_DIR = Path(__file__).parent
OUTPUT_JSON_FOLDER = BASE_DIR / "output_json"

# =========================
# UNCATEGORIZE JSON FILE
# =========================
def remove_categories_from_file(file_path):
    """Remove category, tags, and categorization flags from all items in a JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        modified = False
        
        # Process each item in the items array
        if 'items' in data and isinstance(data['items'], list):
            for item in data['items']:
                # Remove category and tags
                if 'category' in item:
                    del item['category']
                    modified = True
                if 'tags' in item:
                    del item['tags']
                    modified = True
                # Remove categorization flags
                if '_item_categorized' in item:
                    del item['_item_categorized']
                    modified = True
        
        # Remove file-level categorization flags
        if '_categorized' in data:
            del data['_categorized']
            modified = True
        if '_file_categorized' in data:
            del data['_file_categorized']
            modified = True
        
        if modified:
            # Write back to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        
        return False
    except Exception as e:
        print(f"  ✗ Error processing {file_path.name}: {e}")
        return False

# =========================
# UNCATEGORIZE ALL FILES
# =========================
def uncategorize_all():
    """Remove categories from all JSON files in output_json/"""
    if not OUTPUT_JSON_FOLDER.exists():
        print(f"[ERROR] {OUTPUT_JSON_FOLDER} does not exist")
        return
    
    json_files = list(OUTPUT_JSON_FOLDER.glob("*.json"))
    
    if not json_files:
        print(f"[INFO] No JSON files found in {OUTPUT_JSON_FOLDER}")
        return
    
    print(f"[INFO] Found {len(json_files)} JSON file(s)")
    print(f"[INFO] Removing categories and tags...\n")
    
    modified_count = 0
    
    for json_file in json_files:
        print(f"Processing: {json_file.name}")
        if remove_categories_from_file(json_file):
            print(f"  ✓ Categories and tags removed")
            modified_count += 1
        else:
            print(f"  - No categories/tags found (or no changes made)")
    
    print(f"\n[SUCCESS] Modified {modified_count}/{len(json_files)} file(s)")
    print(f"[DONE] All products in {OUTPUT_JSON_FOLDER} are now uncategorized")

# =========================
# MAIN
# =========================
def main():
    print("=" * 60)
    print("UNCATEGORIZE HELPER - Receipt AI")
    print("=" * 60)
    print()
    
    uncategorize_all()
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    main()
