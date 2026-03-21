import os
import sqlite3
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
DEFAULT_DB_PATH = BASE_DIR / "receipts.db"


def get_db_path() -> Path:
    configured = os.environ.get("RECEIPTS_DB_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_filename TEXT NOT NULL,
                image_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                retailer TEXT,
                receipt_date TEXT,
                total_paid REAL,
                result_path TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                product_pl TEXT,
                product_en TEXT,
                quantity REAL,
                unit_price REAL,
                total REAL,
                discount REAL,
                final_total REAL,
                category TEXT,
                tags TEXT,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            )
            """
        )
        connection.commit()


def create_job(image_filename: str, image_path: str) -> int:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO jobs (image_filename, image_path, status)
            VALUES (?, ?, 'queued')
            """,
            (image_filename, image_path),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_job(job_id: int):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return cursor.fetchone()


def list_jobs(status: Optional[str] = None):
    with get_connection() as connection:
        cursor = connection.cursor()
        if status:
            cursor.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY id DESC",
                (status,),
            )
        else:
            cursor.execute("SELECT * FROM jobs ORDER BY id DESC")
        return cursor.fetchall()


def claim_next_queued_job():
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT * FROM jobs WHERE status = 'queued' ORDER BY id ASC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute(
            """
            UPDATE jobs
            SET status = 'processing', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'queued'
            """,
            (row["id"],),
        )
        if cursor.rowcount != 1:
            return None

        connection.commit()
        cursor.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],))
        return cursor.fetchone()


def set_job_done(job_id: int, result_path: str, retailer: str, receipt_date: str, total_paid: float):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'done',
                result_path = ?,
                retailer = ?,
                receipt_date = ?,
                total_paid = ?,
                error_message = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (result_path, retailer, receipt_date, total_paid, job_id),
        )
        connection.commit()


def set_job_error(job_id: int, error_message: str):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'error',
                error_message = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (error_message, job_id),
        )
        connection.commit()


def replace_products(job_id: int, items):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM products WHERE job_id = ?", (job_id,))

        for item in items:
            cursor.execute(
                """
                INSERT INTO products (
                    job_id,
                    product_pl,
                    product_en,
                    quantity,
                    unit_price,
                    total,
                    discount,
                    final_total,
                    category,
                    tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    item.get("product_pl"),
                    item.get("product_en"),
                    item.get("quantity"),
                    item.get("unit_price"),
                    item.get("total"),
                    item.get("discount"),
                    item.get("final_total"),
                    item.get("category"),
                    ",".join(item.get("tags", [])),
                ),
            )

        connection.commit()


def get_products_for_job(job_id: int):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM products WHERE job_id = ? ORDER BY id ASC", (job_id,))
        return cursor.fetchall()
