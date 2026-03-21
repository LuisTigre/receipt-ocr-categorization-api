# Project Refactoring Guide

## Current Architecture Analysis

Your project is transitioning from **local OCR + local Ollama** to **cloud-based vision + cloud-based LLM**.

---

## 🗑️ **FOLDERS TO REMOVE**

### ❌ `output_json_translated/`
- **Status:** DEPRECATED
- **Reason:** Used by old `prod_cat.py` which reads from local Ollama
- **Action:** DELETE this folder and its contents

### ❌ `output_text/`
- **Status:** DEPRECATED  
- **Reason:** Created by tesseract OCR pipeline; no longer used since moving to cloud vision
- **Action:** DELETE this folder and its contents

### ❌ `output_json_optimized/`
- **Status:** DEPRECATED
- **Reason:** Output from `optimizer.py` which depends on `output_text/` (deprecated pipeline)
- **Action:** DELETE this folder
- **Question:** Do you need `optimizer.py` functionality? If yes, refactor it to work with cloud pipeline

### ❌ `output/`
- **Status:** EMPTY
- **Action:** DELETE this folder

---

## 📁 **FOLDERS TO KEEP**

### ✅ `receipt_images/`
- Input folder for image processing
- Used by: `image-json-converter.py`

### ✅ `documents/`
- Source document storage
- May be used for reference/backup

### ✅ `output_json/`
- **Current:** Primary output from `image-json-converter.py`
- **Used by:** `prod_cat_cloud.py` (for categorization)
- **Keep this!**

### ✅ `processed_images/`
- Output of processed/analyzed images
- Keep unless you don't need to save processed images

### ✅ `__pycache__/`
- Python cache (can be ignored in git, deletes automatically)

---

## 📄 **PYTHON FILES ANALYSIS**

### ✅ **KEEP - Core Production Files**

#### `image-json-converter.py`
- **Status:** ACTIVE - Cloud vision model (gemini-3-flash-preview)
- **Input:** `receipt_images/`
- **Output:** `output_json/`
- **Keep:** YES

#### `prod_cat_cloud.py`
- **Status:** ACTIVE - Cloud-based categorization (gemini-3-flash-preview)
- **Input:** `output_json/`
- **Keep:** YES

---

### ❌ **DEPRECATED - Remove These Files**

#### `prod_cat.py`
- **Status:** OLD LOCAL VERSION
- **Issues:** 
  - Uses `output_json_translated/` (deprecated source folder)
  - Uses local Ollama at `http://100.104.103.64:11434`
  - Uses `MODEL_NAME = "llama3.2"` (local model)
- **Action:** DELETE this file

#### `optimizer.py`
- **Status:** CONDITIONAL DEPRECATION
- **Issues:**
  - Depends on `output_text/` (tesseract OCR output - deprecated)
  - Depends on `output_json_translated/` (old pipeline)
  - Uses local Ollama
- **Decision Needed:**
  - DO YOU NEED: JSON optimization/cleanup functionality? 
    - If YES → Refactor to work with cloud pipeline (use `output_json/` instead)
    - If NO → DELETE this file

#### `ocr_converter.py`
- **Status:** OLD OCR PIPELINE
- **Reason:** No longer using local Tesseract OCR; moved to cloud vision
- **Action:** DELETE this file

#### `ocr_json_conv.py`
- **Status:** OLD OCR PIPELINE
- **Reason:** Converts Tesseract output; not needed with cloud vision
- **Action:** DELETE this file

#### `ocr_json_ollama.py`
- **Status:** TRANSLATOR (Cloud-based)
- **Purpose:** Translates Polish product names → English using Ollama cloud
- **Input:** `output_json/` (extracted receipt data)
- **Output:** `output_json_translated/` (with English product names)
- **Decision Needed:**
  - **Keep IF:** You want product names translated to English
  - **Delete IF:** You don't need translation (working with Polish names is fine)
- **Note:** Uses cloud Ollama (good!), but outputs to deprecated folder

---

## 🐳 **Docker & Requirements Fix**

### Dockerfile Issues
```dockerfile
# CURRENT (❌ WRONG)
RUN apt-get install -y \
    tesseract-ocr \          # ❌ NOT NEEDED - using cloud vision
    tesseract-ocr-pol \      # ❌ NOT NEEDED
    tesseract-ocr-eng \      # ❌ NOT NEEDED
```

**Action:** Remove tesseract dependencies. New Dockerfile should:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY image-json-converter.py .
COPY prod_cat_cloud.py .
RUN mkdir -p receipt_images output_json processed_images
```

### requirements.txt Issues
**Current packages are incomplete:**
- Missing: `ollama` (required by both Python scripts!)
- Missing: Modern async HTTP client options

**Action:** Update requirements.txt:
```
pytesseract==0.3.10          # ❌ REMOVE if deleting OCR files
opencv-python-headless==4.9.0.80  # ❓ Keep or remove?
numpy==1.26.4                # ✅ Keep (dependency)
Pillow                       # ✅ Keep (dependency)
pandas                       # ❌ Only used in ocr_converter.py
ollama                       # ✅ ADD THIS
requests==2.31.0             # ✅ Keep (if used)
```

### docker-compose.yml Issues
**Current references non-existent files:**
```yaml
command: python OllamaTest.py      # ❌ File doesn't exist
command: python send_to_ollama.py  # ❌ File doesn't exist
```

**Action:** Update to match actual pipeline:
```yaml
services:
  image-extractor:
    build: .
    volumes:
      - ./receipt_images:/app/receipt_images
      - ./output_json:/app/output_json
      - ./processed_images:/app/processed_images
    command: python image-json-converter.py
    environment:
      - OLLAMA_API_KEY=${OLLAMA_API_KEY}

  categorizer:
    build: .
    volumes:
      - ./output_json:/app/output_json
    command: python prod_cat_cloud.py
    environment:
      - OLLAMA_API_KEY=${OLLAMA_API_KEY}
```

---

## � **Pipeline Options**

Your refactored pipeline can be one of these:

### Option A: Minimal/Fast Pipeline (Recommended)
```
receipt_images/ 
    → image-json-converter.py 
    → output_json/ 
    → prod_cat_cloud.py 
    → [output with categories/tags]
```
- **Delete:** `optimizer.py`, `ocr_json_ollama.py`, all translate/optimize folders
- **Best for:** Just extracting & categorizing receipts quickly

### Option B: With Translation
```
receipt_images/ 
    → image-json-converter.py 
    → output_json/ 
    → ocr_json_ollama.py 
    → output_json_translated/ 
    → prod_cat_cloud.py 
    → [output with categories/tags]
```
- **Keep:** `ocr_json_ollama.py`
- **Delete:** `optimizer.py`, `output_json_optimized/`
- **Best for:** Polish receipts that need English translation

### Option C: Full Pipeline (With Optimization)
```
receipt_images/ 
    → image-json-converter.py 
    → output_json/ 
    → ocr_json_ollama.py 
    → output_json_translated/ 
    → optimizer.py 
    → output_json_optimized/
    → prod_cat_cloud.py
```
- **Keep:** All files, all folders
- **Best for:** Maximum data cleaning/deduplication before categorization

---

## �🔍 **Pre-Cleanup Checklist**

**Before deleting any files, please verify:**

- [ ] Do you need product name **translation** (Polish → English)?
  - [ ] YES → Keep `ocr_json_ollama.py` and `output_json_translated/`
  - [ ] NO → Delete them
  
- [ ] Do you need **JSON optimization** (deduplication/cleaning)?
  - [ ] YES → Keep `optimizer.py` and `output_json_optimized/`
  - [ ] NO → Delete them
  
- [ ] Are you definitely not using local OCR anymore?
  - [ ] YES → Delete `ocr_converter.py`, `ocr_json_conv.py`
  - [ ] NO → Keep them

- [ ] Have you confirmed `prod_cat_cloud.py` is your active file?
  - [ ] YES → Delete `prod_cat.py` (old local version)

- [ ] Have you backed up any important data in these folders?
  - `output_text/`
  - `output_json_translated/`
  - `output_json_optimized/`

---

## 📋 **Cleanup Execution Order**

1. **Update requirements.txt** (add `ollama`, remove OCR if unneeded)
2. **Update Dockerfile** (remove tesseract, update COPY directives)
3. **Update docker-compose.yml** (fix commands and services)
4. **Delete deprecated files** (after confirmation):
   - `prod_cat.py`
   - `ocr_converter.py`
   - `ocr_json_conv.py`
5. **Delete deprecated folders** (backup first):
   - `output_text/`
   - `output_json_translated/`
   - `output_json_optimized/`
   - `output/`
6. **Test:** Verify all scripts still work with cloud pipeline

---

## ✨ **Final Project Structure** (After Cleanup)

### After Option A (Minimal - RECOMMENDED)
```
.
├── image-json-converter.py    # Cloud vision: images → JSON
├── prod_cat_cloud.py          # Cloud LLM: categorize products
├── Dockerfile                 # Updated for cloud pipeline
├── docker-compose.yml         # Updated services
├── requirements.txt           # Updated deps
├── documents/                 # Source docs
├── receipt_images/            # Input images
└── output_json/               # Extracted data
```

### After Option B (With Translation)
```
.
├── image-json-converter.py    # Cloud vision
├── ocr_json_ollama.py         # Translate Polish → English
├── prod_cat_cloud.py          # Categorize products
├── Dockerfile, docker-compose.yml, requirements.txt
├── documents/
├── receipt_images/
├── output_json/               # Raw extracted data
└── output_json_translated/    # English product names
```

### After Option C (Full with Optimization)
```
.
├── image-json-converter.py
├── ocr_json_ollama.py
├── optimizer.py               # Clean/deduplicate
├── prod_cat_cloud.py
├── Dockerfile, docker-compose.yml, requirements.txt
├── documents/
├── receipt_images/
├── output_json/               # Raw
├── output_json_translated/    # Translated
└── output_json_optimized/     # Optimized
```

---

## 📝 **Next Steps for Agent**

To complete refactoring:
1. Review `ocr_json_ollama.py` - determine if needed
2. Decide on `optimizer.py` - keep with refactor or delete?
3. Confirm you don't need `prod_cat.py` (old local version)
4. Execute cleanup following the checklist above
