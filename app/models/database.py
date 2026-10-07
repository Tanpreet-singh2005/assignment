import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import BASE_DIR

DB_PATH = BASE_DIR / "geospatial.db"
_lock = threading.Lock()


def get_db_connection() -> sqlite3.Connection:
    """Return a new SQLite database connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables for files and measurements."""
    with _lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                feature_count INTEGER DEFAULT 0,
                crs TEXT DEFAULT 'EPSG:4326',
                status TEXT NOT NULL,
                geometry_summary TEXT,
                created_at TEXT NOT NULL,
                error_message TEXT,
                storage_path TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                file_id TEXT PRIMARY KEY,
                summary_data TEXT NOT NULL,
                features_data TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        conn.close()


class FileRepository:
    """Repository for file records and measurement data."""

    @staticmethod
    def create_file_record(
        file_id: str,
        filename: str,
        file_type: str,
        file_size_bytes: int,
        status: str = "PENDING",
        storage_path: Optional[str] = None
    ) -> Dict[str, Any]:
        with _lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO files (id, filename, file_type, file_size_bytes, feature_count, crs, status, geometry_summary, created_at, error_message, storage_path)
                VALUES (?, ?, ?, ?, 0, 'EPSG:4326', ?, '{}', ?, NULL, ?)
                """,
                (file_id, filename, file_type, file_size_bytes, status, now, storage_path)
            )
            conn.commit()
            conn.close()
        return FileRepository.get_file(file_id)

    @staticmethod
    def update_file_record(
        file_id: str,
        status: str,
        feature_count: Optional[int] = None,
        crs: Optional[str] = None,
        geometry_summary: Optional[Dict[str, int]] = None,
        error_message: Optional[str] = None
    ):
        with _lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            updates = ["status = ?"]
            params = [status]

            if feature_count is not None:
                updates.append("feature_count = ?")
                params.append(feature_count)

            if crs is not None:
                updates.append("crs = ?")
                params.append(crs)

            if geometry_summary is not None:
                updates.append("geometry_summary = ?")
                params.append(json.dumps(geometry_summary, default=str))

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            params.append(file_id)
            query = f"UPDATE files SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
            conn.close()

    @staticmethod
    def save_measurements(file_id: str, summary: Dict[str, Any], features: List[Dict[str, Any]]):
        with _lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO measurements (file_id, summary_data, features_data)
                VALUES (?, ?, ?)
                """,
                (file_id, json.dumps(summary, default=str), json.dumps(features, default=str))
            )
            conn.commit()
            conn.close()

    @staticmethod
    def get_file(file_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        data = dict(row)
        try:
            data["geometry_summary"] = json.loads(data["geometry_summary"] or "{}")
        except Exception:
            data["geometry_summary"] = {}
        return data

    @staticmethod
    def list_files(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
        rows = cursor.fetchall()
        conn.close()
        results = []
        for row in rows:
            data = dict(row)
            try:
                data["geometry_summary"] = json.loads(data["geometry_summary"] or "{}")
            except Exception:
                data["geometry_summary"] = {}
            results.append(data)
        return results

    @staticmethod
    def get_measurements(file_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM measurements WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "summary": json.loads(row["summary_data"]),
            "features": json.loads(row["features_data"])
        }

    @staticmethod
    def delete_file(file_id: str) -> bool:
        with _lock:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM measurements WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            conn.close()
            return deleted


# Initialize database on module import
init_db()
