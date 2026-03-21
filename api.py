import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from db import create_job, get_job, get_products_for_job, init_db, list_jobs

BASE_DIR = Path(__file__).parent
RECEIPT_IMAGES_DIR = BASE_DIR / "receipt_images"


class ReceiptJobResponse(BaseModel):
    receipt_id: int
    status: str


class ReceiptStatusResponse(BaseModel):
    id: int
    image_filename: str
    status: str
    retailer: Optional[str] = None
    receipt_date: Optional[str] = None
    total_paid: Optional[float] = None
    result_path: Optional[str] = None
    error_message: Optional[str] = None


class ProductResponse(BaseModel):
    product_pl: Optional[str] = None
    product_en: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None
    discount: Optional[float] = None
    final_total: Optional[float] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


app = FastAPI(title="Receipt AI API", version="1.0.0")


@app.on_event("startup")
def startup_event():
    RECEIPT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/receipts", response_model=ReceiptJobResponse)
def submit_receipt(file: UploadFile = File(...)):
    suffix = Path(file.filename or "receipt.jpg").suffix or ".jpg"
    unique_name = f"{uuid.uuid4().hex}{suffix}"
    destination = RECEIPT_IMAGES_DIR / unique_name

    with destination.open("wb") as output_file:
        shutil.copyfileobj(file.file, output_file)

    job_id = create_job(image_filename=file.filename or unique_name, image_path=str(destination))
    return ReceiptJobResponse(receipt_id=job_id, status="queued")


@app.get("/receipts", response_model=List[ReceiptStatusResponse])
def get_receipts(status: Optional[str] = Query(default=None)):
    rows = list_jobs(status=status)
    return [
        ReceiptStatusResponse(
            id=row["id"],
            image_filename=row["image_filename"],
            status=row["status"],
            retailer=row["retailer"],
            receipt_date=row["receipt_date"],
            total_paid=row["total_paid"],
            result_path=row["result_path"],
            error_message=row["error_message"],
        )
        for row in rows
    ]


@app.get("/receipts/{receipt_id}", response_model=ReceiptStatusResponse)
def get_receipt(receipt_id: int):
    row = get_job(receipt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return ReceiptStatusResponse(
        id=row["id"],
        image_filename=row["image_filename"],
        status=row["status"],
        retailer=row["retailer"],
        receipt_date=row["receipt_date"],
        total_paid=row["total_paid"],
        result_path=row["result_path"],
        error_message=row["error_message"],
    )


@app.get("/receipts/{receipt_id}/items", response_model=List[ProductResponse])
def get_receipt_items(receipt_id: int):
    row = get_job(receipt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")

    products = get_products_for_job(receipt_id)
    return [
        ProductResponse(
            product_pl=product["product_pl"],
            product_en=product["product_en"],
            quantity=product["quantity"],
            unit_price=product["unit_price"],
            total=product["total"],
            discount=product["discount"],
            final_total=product["final_total"],
            category=product["category"],
            tags=[tag for tag in (product["tags"] or "").split(",") if tag],
        )
        for product in products
    ]
