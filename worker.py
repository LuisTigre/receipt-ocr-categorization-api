import os
import time
from pathlib import Path

from db import claim_next_queued_job, init_db, replace_products, set_job_done, set_job_error
from receipt_core import categorize_receipt_data, extract_receipt_from_image, save_receipt_json

BASE_DIR = Path(__file__).parent
OUTPUT_JSON_DIR = BASE_DIR / "output_json"
POLL_INTERVAL_SECONDS = int(os.environ.get("WORKER_POLL_INTERVAL", "5"))


def process_job(job):
    job_id = int(job["id"])
    image_path = Path(job["image_path"])

    if not image_path.exists():
        set_job_error(job_id, f"Image not found: {image_path}")
        return

    print(f"[WORKER] Processing job {job_id} ({image_path.name})")

    extracted = extract_receipt_from_image(image_path)
    if not extracted:
        set_job_error(job_id, "Failed to extract receipt data")
        return

    categorized = categorize_receipt_data(extracted)
    output_path = OUTPUT_JSON_DIR / f"job_{job_id}_{image_path.stem}.json"
    save_receipt_json(categorized, output_path)

    items = categorized.get("items", [])
    replace_products(job_id, items)

    set_job_done(
        job_id=job_id,
        result_path=str(output_path),
        retailer=categorized.get("retailer") or "",
        receipt_date=categorized.get("date") or "",
        total_paid=float(categorized.get("total_paid") or 0),
    )

    print(f"[WORKER] Job {job_id} completed")


def main():
    OUTPUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
    init_db()

    print("[WORKER] Started")
    while True:
        try:
            job = claim_next_queued_job()
            if not job:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            process_job(job)
        except Exception as error:
            print(f"[WORKER] Unexpected error: {error}")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
