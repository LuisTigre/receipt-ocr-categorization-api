# Receipt AI - Cloud-Based Pipeline

## 📋 Overview

A clean, cloud-based receipt processing pipeline that:
1. **Extracts** receipt data from images using cloud vision AI (Ollama cloud - Gemini 3 Flash)
2. **Categorizes** products using cloud LLM (Ollama cloud)

No local OCR, no local Ollama server needed. Just cloud APIs!

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (optional)
- `OLLAMA_API_KEY` environment variable set

### Local Execution
```bash
# Set your API key
export OLLAMA_API_KEY=your_key_here

# Run the full pipeline
python run_pipeline.py
```

### Docker Execution
```bash
# Set your API key
export OLLAMA_API_KEY=your_key_here

# Run with Docker
docker-compose up

# Or rebuild
docker-compose up --build
```

---

## 📁 Project Structure

```
.
├── image-json-converter.py    # Step 1: Extract receipt images → JSON
├── prod_cat_cloud.py          # Step 2: Categorize products
├── run_pipeline.py            # Orchestrator: Runs both sequentially
├── cleanup_helper.py          # Utility: Clean output & organize files
│
├── Dockerfile                 # Docker image
├── docker-compose.yml         # Docker Compose config
├── requirements.txt           # Python dependencies (just ollama!)
├── REFACTORING_GUIDE.md       # Migration guide
├── .instructions.md           # Agent instructions
│
├── receipt_images/            # INPUT: Place receipt images here
├── output_json/               # OUTPUT: Extracted + categorized data
└── processed_images/          # Working folder
```

---

## 🔄 Pipeline Flow

```
                  ┌─────────────────────┐
                  │   receipt_images/   │
                  │   (your images)     │
                  └──────────┬──────────┘
                             │
                     ┌───────▼────────┐
                     │  STEP 1         │
                     │  Extraction     │
                     │  (cloud vision) │
                     └───────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   output_json/  │
                    │ (raw JSON data) │
                    └────────┬────────┘
                             │
                     ┌───────▼────────┐
                     │  STEP 2         │
                     │  Categorization │
                     │  (cloud LLM)    │
                     └───────┬────────┘
                             │
            ┌────────────────▼────────────────┐
            │     Final Categorized Data      │
            │    (with categories & tags)     │
            └─────────────────────────────────┘
```

---

## 🛠️ Available Scripts

### 1. **run_pipeline.py** — Full Pipeline (Recommended)
Runs extraction → categorization sequentially with error handling.
```bash
python run_pipeline.py
```

### 2. **image-json-converter.py** — Extract Only
Processes receipt images and outputs JSON.
```bash
python image-json-converter.py
```

### 3. **prod_cat_cloud.py** — Categorize Only
Reads JSON and categorizes products.
```bash
python prod_cat_cloud.py
```

### 4. **cleanup_helper.py** — Cleanup Utility
- Cleans output_json/
- Moves processed_images/ → receipt_images/
```bash
python cleanup_helper.py
```

---

## 📊 Data Format

### Input
Place receipt images in `receipt_images/`:
- `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.webp`

### Output (output_json/)
```json
{
  "retailer": "store name",
  "date": "2025-03-21",
  "total_paid": 125.50,
  "items": [
    {
      "product_pl": "Coca-Cola",
      "product_en": "Coca-Cola",
      "quantity": 1,
      "unit_price": 8.50,
      "total": 8.50,
      "discount": 0,
      "final_total": 8.50,
      "category": "Food",
      "tags": ["personal care", "optional"]
    }
  ]
}
```

---

## 🔑 Environment Variables

```bash
# Required
OLLAMA_API_KEY=your_api_key_here

# Optional (Docker only)
# None currently needed
```

---

## 📝 Configuration

### Models Used
- **Vision Model**: `gemini-3-flash-preview` (cloud)
- **LLM Model**: `gemini-3-flash-preview` (cloud)
- **Host**: `https://ollama.com` (Ollama cloud)

### Categories
Food, Hygiene, Housing, Transportation, Media, Clothing, Other

### Tags
personal care, home care, home rental, work-related, delivery, bicycle, entertainment, self development, essential, optional

---

## 🐛 Troubleshooting

### Missing API Key
```
ERROR: OLLAMA_API_KEY environment variable not set
```
**Fix**: 
```bash
export OLLAMA_API_KEY=your_key
```

### No Images to Process
```
[WARN] No image files found in receipt_images/
```
**Fix**: Place image files in `receipt_images/` folder

### Extraction Timeout
The extraction can take 10-30 seconds per receipt (cloud API latency).
Check `output_json/` for partial results.

---

## 📦 Dependencies

Only one dependency:
```
ollama>=0.3.0
```

Install with:
```bash
pip install -r requirements.txt
```

---

## 🎯 Next Steps

1. **Set API key**:
   ```bash
   export OLLAMA_API_KEY=your_key_here
   ```

2. **Add receipt images** to `receipt_images/`

3. **Run pipeline**:
   ```bash
   python run_pipeline.py
   ```
   
   Or with Docker:
   ```bash
   docker-compose up
   ```

4. **Check results** in `output_json/`

5. **Clean up** (optional):
   ```bash
   python cleanup_helper.py
   ```

---

## 📖 Documentation Files

- **REFACTORING_GUIDE.md** — What was cleaned up & why
- **.instructions.md** — Agent refactoring instructions
- **README.md** (this file) — Quick start guide

---

## ✨ Features

✅ Cloud-based (no local dependencies)  
✅ Minimal dependencies (1 package!)  
✅ Sequential pipeline with error handling  
✅ Docker support  
✅ Product categorization included  
✅ Clean project structure  
✅ Easy to extend  

---

**Happy processing! 🚀**
