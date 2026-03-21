"""
Cleanup Helper Script
Cleans output_json folder and moves processed images back to receipt_images
"""

import os
import shutil
from pathlib import Path

# =========================
# CONFIGURATION
# =========================
BASE_DIR = Path(__file__).parent
OUTPUT_JSON_FOLDER = BASE_DIR / "output_json"
PROCESSED_IMAGES_FOLDER = BASE_DIR / "processed_images"
RECEIPT_IMAGES_FOLDER = BASE_DIR / "receipt_images"

# =========================
# CLEAN OUTPUT JSON
# =========================
def clean_output_json():
    """Delete all files in output_json folder"""
    if not OUTPUT_JSON_FOLDER.exists():
        print(f"[INFO] {OUTPUT_JSON_FOLDER} does not exist")
        return
    
    files = list(OUTPUT_JSON_FOLDER.glob("*"))
    if not files:
        print(f"[INFO] {OUTPUT_JSON_FOLDER} is already empty")
        return
    
    print(f"[INFO] Cleaning {OUTPUT_JSON_FOLDER}...")
    for file in files:
        try:
            if file.is_file():
                file.unlink()
                print(f"  ✓ Deleted: {file.name}")
            elif file.is_dir():
                shutil.rmtree(file)
                print(f"  ✓ Deleted: {file.name}/ (folder)")
        except Exception as e:
            print(f"  ✗ Error deleting {file.name}: {e}")
    
    print(f"[SUCCESS] {OUTPUT_JSON_FOLDER} cleaned!\n")

# =========================
# MOVE PROCESSED TO RECEIPT
# =========================
def move_processed_to_receipt():
    """Move all files from processed_images back to receipt_images"""
    if not PROCESSED_IMAGES_FOLDER.exists():
        print(f"[INFO] {PROCESSED_IMAGES_FOLDER} does not exist")
        return
    
    files = list(PROCESSED_IMAGES_FOLDER.glob("*"))
    if not files:
        print(f"[INFO] {PROCESSED_IMAGES_FOLDER} is already empty")
        return
    
    # Create receipt_images if it doesn't exist
    RECEIPT_IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)
    
    print(f"[INFO] Moving files from {PROCESSED_IMAGES_FOLDER} to {RECEIPT_IMAGES_FOLDER}...")
    
    moved_count = 0
    for file in files:
        try:
            if file.is_file():
                dest = RECEIPT_IMAGES_FOLDER / file.name
                shutil.move(str(file), str(dest))
                print(f"  ✓ Moved: {file.name}")
                moved_count += 1
        except Exception as e:
            print(f"  ✗ Error moving {file.name}: {e}")
    
    # Try to remove empty processed_images folder
    try:
        if not any(PROCESSED_IMAGES_FOLDER.iterdir()):
            shutil.rmtree(PROCESSED_IMAGES_FOLDER)
            print(f"  ✓ Removed empty {PROCESSED_IMAGES_FOLDER} folder")
            # Recreate it for Docker
            PROCESSED_IMAGES_FOLDER.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ Recreated {PROCESSED_IMAGES_FOLDER} folder (for Docker)")
    except Exception as e:
        print(f"  [WARN] Could not remove {PROCESSED_IMAGES_FOLDER}: {e}")
    
    print(f"[SUCCESS] Moved {moved_count} file(s)!\n")

# =========================
# MAIN
# =========================
def main():
    print("=" * 60)
    print("CLEANUP HELPER - Recipe AI Project")
    print("=" * 60)
    print()
    
    # Step 1: Clean output_json
    print("[STEP 1] Cleaning output_json/")
    print("-" * 60)
    clean_output_json()
    
    # Step 2: Move processed images
    print("[STEP 2] Moving processed_images/ → receipt_images/")
    print("-" * 60)
    move_processed_to_receipt()
    
    print("=" * 60)
    print("[DONE] Cleanup complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
