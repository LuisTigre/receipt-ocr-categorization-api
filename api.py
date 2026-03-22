import shutil
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from db import (
    add_category,
    add_tag,
    activate_category,
    activate_tag,
    create_job,
    deactivate_category,
    deactivate_tag,
    delete_category,
    delete_tag,
    get_job,
    get_products_for_job,
    init_db,
    list_categories,
    list_jobs,
    list_tags,
    replace_products,
    rename_category,
    rename_tag,
)
from receipt_core import get_category_and_tags

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


class NameRequest(BaseModel):
    name: str


class CategoryResponse(BaseModel):
    id: int
    name: str
    is_active: bool


class TagResponse(BaseModel):
    id: int
    name: str
    is_active: bool


class RecategorizeReceiptResponse(BaseModel):
    receipt_id: int
    updated_items: int
    status: str


class ManualItemRecategorizeRequest(BaseModel):
    item_name: str
    category: str
    tags: List[str] = Field(default_factory=list)


class ManualItemRecategorizeResponse(BaseModel):
    receipt_id: int
    item_name: str
    updated_items: int
    category: str
    tags: List[str] = Field(default_factory=list)
    status: str


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


@app.post("/receipts/{receipt_id}/recategorize", response_model=RecategorizeReceiptResponse)
def recategorize_receipt(receipt_id: int):
    row = get_job(receipt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")

    products = get_products_for_job(receipt_id)
    if not products:
        raise HTTPException(status_code=400, detail="Receipt has no items to recategorize")

    updated_items = []
    for product in products:
        product_pl = (product["product_pl"] or "").strip()
        product_en = (product["product_en"] or "").strip()
        category, tags = get_category_and_tags(product_pl, product_en)

        updated_items.append(
            {
                "product_pl": product["product_pl"],
                "product_en": product["product_en"],
                "quantity": product["quantity"],
                "unit_price": product["unit_price"],
                "total": product["total"],
                "discount": product["discount"],
                "final_total": product["final_total"],
                "category": category,
                "tags": tags,
            }
        )

    replace_products(receipt_id, updated_items)

    return RecategorizeReceiptResponse(
        receipt_id=receipt_id,
        updated_items=len(updated_items),
        status="recategorized",
    )


@app.post(
    "/receipts/{receipt_id}/items/recategorize",
    response_model=ManualItemRecategorizeResponse,
)
def recategorize_receipt_item(receipt_id: int, request: ManualItemRecategorizeRequest):
    row = get_job(receipt_id)
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")

    item_name = (request.item_name or "").strip()
    category = (request.category or "").strip()
    tags = [tag.strip() for tag in request.tags if tag and tag.strip()]

    if not item_name:
        raise HTTPException(status_code=400, detail="item_name is required")
    if not category:
        raise HTTPException(status_code=400, detail="category is required")
    if not tags:
        raise HTTPException(status_code=400, detail="At least one tag is required")

    available_categories = {entry["name"] for entry in list_categories()}
    available_tags = {entry["name"] for entry in list_tags()}

    if category not in available_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category}'. Use GET /categories.",
        )

    invalid_tags = [tag for tag in tags if tag not in available_tags]
    if invalid_tags:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tags: {', '.join(invalid_tags)}. Use GET /tags.",
        )

    products = get_products_for_job(receipt_id)
    if not products:
        raise HTTPException(status_code=400, detail="Receipt has no items")

    updated_items = []
    updated_count = 0
    target_name = item_name.lower()

    for product in products:
        product_pl = (product["product_pl"] or "").strip()
        product_en = (product["product_en"] or "").strip()

        if product_pl.lower() == target_name or product_en.lower() == target_name:
            current_category = category
            current_tags = tags
            updated_count += 1
        else:
            current_category = product["category"]
            current_tags = [tag for tag in (product["tags"] or "").split(",") if tag]

        updated_items.append(
            {
                "product_pl": product["product_pl"],
                "product_en": product["product_en"],
                "quantity": product["quantity"],
                "unit_price": product["unit_price"],
                "total": product["total"],
                "discount": product["discount"],
                "final_total": product["final_total"],
                "category": current_category,
                "tags": current_tags,
            }
        )

    if updated_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No item named '{item_name}' found in this receipt",
        )

    replace_products(receipt_id, updated_items)

    return ManualItemRecategorizeResponse(
        receipt_id=receipt_id,
        item_name=item_name,
        updated_items=updated_count,
        category=category,
        tags=tags,
        status="manually_recategorized",
    )

@app.get("/categories", response_model=List[CategoryResponse])
def get_categories(include_inactive: bool = Query(default=False)):
    rows = list_categories(include_inactive=include_inactive)
    return [
        CategoryResponse(
            id=row["id"],
            name=row["name"],
            is_active=bool(row["is_active"]),
        )
        for row in rows
    ]


@app.post("/categories", response_model=CategoryResponse, status_code=201)
def create_category(request: NameRequest):
    try:
        row = add_category(request.name)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return CategoryResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.put("/categories/{category_name}", response_model=CategoryResponse)
def update_category(category_name: str, request: NameRequest):
    try:
        row = rename_category(category_name, request.name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return CategoryResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.patch("/categories/{category_name}/deactivate", response_model=CategoryResponse)
def deactivate_category_endpoint(category_name: str):
    try:
        row = deactivate_category(category_name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return CategoryResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.patch("/categories/{category_name}/activate", response_model=CategoryResponse)
def activate_category_endpoint(category_name: str):
    try:
        row = activate_category(category_name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return CategoryResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.delete("/categories/{category_name}")
def remove_category(category_name: str):
    try:
        delete_category(category_name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"deleted": category_name}


@app.get("/tags", response_model=List[TagResponse])
def get_tags(include_inactive: bool = Query(default=False)):
    rows = list_tags(include_inactive=include_inactive)
    return [
        TagResponse(
            id=row["id"],
            name=row["name"],
            is_active=bool(row["is_active"]),
        )
        for row in rows
    ]


@app.post("/tags", response_model=TagResponse, status_code=201)
def create_tag(request: NameRequest):
    try:
        row = add_tag(request.name)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return TagResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.put("/tags/{tag_name}", response_model=TagResponse)
def update_tag(tag_name: str, request: NameRequest):
    try:
        row = rename_tag(tag_name, request.name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return TagResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.patch("/tags/{tag_name}/deactivate", response_model=TagResponse)
def deactivate_tag_endpoint(tag_name: str):
    try:
        row = deactivate_tag(tag_name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return TagResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.patch("/tags/{tag_name}/activate", response_model=TagResponse)
def activate_tag_endpoint(tag_name: str):
    try:
        row = activate_tag(tag_name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return TagResponse(
        id=row["id"],
        name=row["name"],
        is_active=bool(row["is_active"]),
    )


@app.delete("/tags/{tag_name}")
def remove_tag(tag_name: str):
    try:
        delete_tag(tag_name)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {"deleted": tag_name}


