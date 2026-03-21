
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY image-json-converter.py .
COPY prod_cat_cloud.py .

RUN mkdir -p receipt_images output_json processed_images