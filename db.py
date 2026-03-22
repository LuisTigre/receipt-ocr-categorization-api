import os
import sqlite3
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
DEFAULT_DB_PATH = BASE_DIR / "receipts.db"
DEFAULT_CATEGORIES = [
    "Food",
    "Hygiene",
    "Household",
    "Transportation",
    "Entertainment",
    "Clothing",
    "Other",
]
DEFAULT_TAGS = [
    "essential",
    "optional",
    "work-related",
    "self development",
]


def get_db_path() -> Path:
    configured = os.environ.get("RECEIPTS_DB_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path(), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _clean_name(name: str, label: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError(f"{label} name cannot be empty")
    return cleaned


def _ensure_category(cursor: sqlite3.Cursor, name: str) -> int:
    cleaned = _clean_name(name, "Category")
    cursor.execute("INSERT OR IGNORE INTO categories (name, is_active) VALUES (?, 1)", (cleaned,))
    cursor.execute("SELECT id FROM categories WHERE name = ?", (cleaned,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Category not found after ensure: {cleaned}")
    return int(row["id"])


def _ensure_tag(cursor: sqlite3.Cursor, name: str) -> int:
    cleaned = _clean_name(name, "Tag")
    cursor.execute("INSERT OR IGNORE INTO tags (name, is_active) VALUES (?, 1)", (cleaned,))
    cursor.execute("SELECT id FROM tags WHERE name = ?", (cleaned,))
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Tag not found after ensure: {cleaned}")
    return int(row["id"])


def _migrate_legacy_products(connection: sqlite3.Connection):
    cursor = connection.cursor()
    columns = {
        row["name"] for row in cursor.execute("PRAGMA table_info(products)").fetchall()
    }
    # If category_id exists, schema is already normalized.
    if "category_id" in columns:
        return

    # Legacy schema expected to have category/tags text columns.
    legacy_rows = cursor.execute("SELECT * FROM products ORDER BY id ASC").fetchall()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            product_pl TEXT,
            product_en TEXT,
            quantity REAL,
            unit_price REAL,
            total REAL,
            discount REAL,
            final_total REAL,
            category_id INTEGER NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE RESTRICT
        )
        """
    )

    tag_links = []
    fallback_category_id = _ensure_category(cursor, "Other")

    for row in legacy_rows:
        category_name = (row["category"] or "").strip() if "category" in row.keys() else ""
        if category_name:
            category_id = _ensure_category(cursor, category_name)
        else:
            category_id = fallback_category_id

        cursor.execute(
            """
            INSERT INTO products_new (
                id,
                job_id,
                product_pl,
                product_en,
                quantity,
                unit_price,
                total,
                discount,
                final_total,
                category_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["job_id"],
                row["product_pl"],
                row["product_en"],
                row["quantity"],
                row["unit_price"],
                row["total"],
                row["discount"],
                row["final_total"],
                category_id,
            ),
        )

        tags_csv = (row["tags"] or "") if "tags" in row.keys() else ""
        tags = [value.strip() for value in tags_csv.split(",") if value and value.strip()]
        for tag_name in tags:
            tag_id = _ensure_tag(cursor, tag_name)
            tag_links.append((row["id"], tag_id))

    cursor.execute("DROP TABLE products")
    cursor.execute("ALTER TABLE products_new RENAME TO products")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS product_tags (
            product_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (product_id, tag_id),
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE RESTRICT
        )
        """
    )

    for product_id, tag_id in tag_links:
        cursor.execute(
            "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
            (product_id, tag_id),
        )


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
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Backward-compatible migration for pre-is_active DBs.
        category_columns = {
            row["name"]
            for row in cursor.execute("PRAGMA table_info(categories)").fetchall()
        }
        if "is_active" not in category_columns:
            cursor.execute(
                "ALTER TABLE categories ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )

        tag_columns = {
            row["name"] for row in cursor.execute("PRAGMA table_info(tags)").fetchall()
        }
        if "is_active" not in tag_columns:
            cursor.execute(
                "ALTER TABLE tags ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
            )

        for category_name in DEFAULT_CATEGORIES:
            cursor.execute(
                "INSERT OR IGNORE INTO categories (name, is_active) VALUES (?, 1)",
                (category_name,),
            )

        for tag_name in DEFAULT_TAGS:
            cursor.execute(
                "INSERT OR IGNORE INTO tags (name, is_active) VALUES (?, 1)",
                (tag_name,),
            )

        # Create normalized products schema if products table does not exist yet.
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
                category_id INTEGER NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
                FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE RESTRICT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS product_tags (
                product_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (product_id, tag_id),
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE RESTRICT
            )
            """
        )

        _migrate_legacy_products(connection)
        connection.commit()


def list_categories(include_inactive: bool = False):
    with get_connection() as connection:
        cursor = connection.cursor()
        if include_inactive:
            cursor.execute(
                "SELECT id, name, is_active FROM categories ORDER BY name COLLATE NOCASE"
            )
        else:
            cursor.execute(
                "SELECT id, name, is_active FROM categories WHERE is_active = 1 ORDER BY name COLLATE NOCASE"
            )
        return cursor.fetchall()


def add_category(name: str):
    cleaned = _clean_name(name, "Category")
    with get_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO categories (name, is_active) VALUES (?, 1)",
                (cleaned,),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError("Category already exists") from error

        cursor.execute(
            "SELECT id, name, is_active FROM categories WHERE id = ?",
            (cursor.lastrowid,),
        )
        return cursor.fetchone()


def rename_category(current_name: str, new_name: str):
    current_clean = _clean_name(current_name, "Category")
    new_clean = _clean_name(new_name, "Category")
    with get_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "UPDATE categories SET name = ? WHERE name = ?",
                (new_clean, current_clean),
            )
            if cursor.rowcount != 1:
                raise LookupError("Category not found")
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError("Category already exists") from error

        cursor.execute(
            "SELECT id, name, is_active FROM categories WHERE name = ?",
            (new_clean,),
        )
        return cursor.fetchone()


def deactivate_category(name: str):
    cleaned = _clean_name(name, "Category")
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE categories SET is_active = 0 WHERE name = ?",
            (cleaned,),
        )
        if cursor.rowcount != 1:
            raise LookupError("Category not found")
        connection.commit()

        cursor.execute(
            "SELECT id, name, is_active FROM categories WHERE name = ?",
            (cleaned,),
        )
        return cursor.fetchone()


def activate_category(name: str):
    cleaned = _clean_name(name, "Category")
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE categories SET is_active = 1 WHERE name = ?",
            (cleaned,),
        )
        if cursor.rowcount != 1:
            raise LookupError("Category not found")
        connection.commit()

        cursor.execute(
            "SELECT id, name, is_active FROM categories WHERE name = ?",
            (cleaned,),
        )
        return cursor.fetchone()


def delete_category(name: str):
    cleaned = _clean_name(name, "Category")
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM categories")
        total = int(cursor.fetchone()["count"])
        if total <= 1:
            raise ValueError("At least one category must remain")

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM products p
            JOIN categories c ON c.id = p.category_id
            WHERE c.name = ?
            """,
            (cleaned,),
        )
        usage = int(cursor.fetchone()["count"])
        if usage > 0:
            raise ValueError("Category is in use by receipt items; deactivate instead")

        cursor.execute("DELETE FROM categories WHERE name = ?", (cleaned,))
        if cursor.rowcount != 1:
            raise LookupError("Category not found")
        connection.commit()


def list_tags(include_inactive: bool = False):
    with get_connection() as connection:
        cursor = connection.cursor()
        if include_inactive:
            cursor.execute("SELECT id, name, is_active FROM tags ORDER BY name COLLATE NOCASE")
        else:
            cursor.execute(
                "SELECT id, name, is_active FROM tags WHERE is_active = 1 ORDER BY name COLLATE NOCASE"
            )
        return cursor.fetchall()


def add_tag(name: str):
    cleaned = _clean_name(name, "Tag")
    with get_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("INSERT INTO tags (name, is_active) VALUES (?, 1)", (cleaned,))
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError("Tag already exists") from error

        cursor.execute(
            "SELECT id, name, is_active FROM tags WHERE id = ?",
            (cursor.lastrowid,),
        )
        return cursor.fetchone()


def rename_tag(current_name: str, new_name: str):
    current_clean = _clean_name(current_name, "Tag")
    new_clean = _clean_name(new_name, "Tag")
    with get_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "UPDATE tags SET name = ? WHERE name = ?",
                (new_clean, current_clean),
            )
            if cursor.rowcount != 1:
                raise LookupError("Tag not found")
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise ValueError("Tag already exists") from error

        cursor.execute("SELECT id, name, is_active FROM tags WHERE name = ?", (new_clean,))
        return cursor.fetchone()


def deactivate_tag(name: str):
    cleaned = _clean_name(name, "Tag")
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE tags SET is_active = 0 WHERE name = ?", (cleaned,))
        if cursor.rowcount != 1:
            raise LookupError("Tag not found")
        connection.commit()

        cursor.execute("SELECT id, name, is_active FROM tags WHERE name = ?", (cleaned,))
        return cursor.fetchone()


def activate_tag(name: str):
    cleaned = _clean_name(name, "Tag")
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("UPDATE tags SET is_active = 1 WHERE name = ?", (cleaned,))
        if cursor.rowcount != 1:
            raise LookupError("Tag not found")
        connection.commit()

        cursor.execute("SELECT id, name, is_active FROM tags WHERE name = ?", (cleaned,))
        return cursor.fetchone()


def delete_tag(name: str):
    cleaned = _clean_name(name, "Tag")
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM tags")
        total = int(cursor.fetchone()["count"])
        if total <= 1:
            raise ValueError("At least one tag must remain")

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM product_tags pt
            JOIN tags t ON t.id = pt.tag_id
            WHERE t.name = ?
            """,
            (cleaned,),
        )
        usage = int(cursor.fetchone()["count"])
        if usage > 0:
            raise ValueError("Tag is in use by receipt items; deactivate instead")

        cursor.execute("DELETE FROM tags WHERE name = ?", (cleaned,))
        if cursor.rowcount != 1:
            raise LookupError("Tag not found")
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

        fallback_category_id = _ensure_category(cursor, "Other")

        for item in items:
            category_name = (item.get("category") or "").strip()
            if category_name:
                cursor.execute("SELECT id FROM categories WHERE name = ?", (category_name,))
                category_row = cursor.fetchone()
                category_id = int(category_row["id"]) if category_row else fallback_category_id
            else:
                category_id = fallback_category_id

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
                    category_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    category_id,
                ),
            )
            product_id = int(cursor.lastrowid)

            for tag_name in item.get("tags", []):
                cleaned_tag = (tag_name or "").strip()
                if not cleaned_tag:
                    continue
                tag_id = _ensure_tag(cursor, cleaned_tag)
                cursor.execute(
                    "INSERT OR IGNORE INTO product_tags (product_id, tag_id) VALUES (?, ?)",
                    (product_id, tag_id),
                )

        connection.commit()


def get_products_for_job(job_id: int):
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
                p.id,
                p.job_id,
                p.product_pl,
                p.product_en,
                p.quantity,
                p.unit_price,
                p.total,
                p.discount,
                p.final_total,
                c.name AS category,
                COALESCE(GROUP_CONCAT(t.name, ','), '') AS tags
            FROM products p
            LEFT JOIN categories c ON c.id = p.category_id
            LEFT JOIN product_tags pt ON pt.product_id = p.id
            LEFT JOIN tags t ON t.id = pt.tag_id
            WHERE p.job_id = ?
            GROUP BY
                p.id,
                p.job_id,
                p.product_pl,
                p.product_en,
                p.quantity,
                p.unit_price,
                p.total,
                p.discount,
                p.final_total,
                c.name
            ORDER BY p.id ASC
            """,
            (job_id,),
        )
        return cursor.fetchall()
