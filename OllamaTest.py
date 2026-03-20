import os
import cv2
import numpy as np
import pytesseract
from PIL import Image

DOCUMENTS_FOLDER = "documents"
OUTPUT_FOLDER = "output_text"
SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def preprocess_image(image):
    upscaled = cv2.resize(image, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return enhanced

def extract_text_from_image(image_path):
    img = cv2.imread(image_path)
    if img is None:
        print(f"[ERROR] Could not read image: {image_path}")
        return ""
    processed = preprocess_image(img)
    pil_image = Image.fromarray(processed)
    config = "--psm 6 -l pol+eng"
    text = pytesseract.image_to_string(pil_image, config=config)
    return text.strip()

def main():
    files = [
        f for f in os.listdir(DOCUMENTS_FOLDER)
        if f.lower().endswith(SUPPORTED_FORMATS)
    ]
    if not files:
        print(f"[WARN] No image files found in {DOCUMENTS_FOLDER}")
        return
    print(f"[INFO] Found {len(files)} image(s)")
    for idx, filename in enumerate(files, start=1):
        file_path = os.path.join(DOCUMENTS_FOLDER, filename)
        print(f"[{idx}/{len(files)}] Processing: {filename}")
        text = extract_text_from_image(file_path)
        if not text.strip():
            print("   [WARN] No text extracted")
            continue
        output_file = os.path.join(
            OUTPUT_FOLDER,
            f"{os.path.splitext(filename)[0]}.txt"
        )
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text)
        lines = text.strip().count("\n") + 1
        print(f"   [OK] Saved -> {output_file} ({lines} lines)")
    print("[DONE] All images processed!")

if __name__ == "__main__":
    main()