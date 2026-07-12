"""core.database.actress — Actress 資料模型與 ActressRepository（spec-87 子模組）。"""
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from . import connection


@dataclass
class Actress:
    """女優資料模型"""
    name: str = ""
    name_en: Optional[str] = None
    birth: Optional[str] = None
    height: Optional[str] = None
    cup: Optional[str] = None
    bust: Optional[int] = None
    waist: Optional[int] = None
    hip: Optional[int] = None
    hometown: Optional[str] = None
    hobby: Optional[str] = None
    aliases: List[str] = field(default_factory=list)  # JSON
    agency: Optional[str] = None
    debut_work: Optional[str] = None
    tags: List[str] = field(default_factory=list)  # JSON
    nickname: Optional[str] = None
    blog_url: Optional[str] = None
    official_url: Optional[str] = None
    photo_source: Optional[str] = None
    primary_text_source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """轉為字典（JSON 欄位序列化）"""
        data = asdict(self)
        data['aliases'] = json.dumps(self.aliases, ensure_ascii=False)
        data['tags'] = json.dumps(self.tags, ensure_ascii=False)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'Actress':
        """從資料庫 row 建立"""
        data = dict(zip(columns, row, strict=True))

        if 'aliases' in data and data['aliases']:
            try:
                data['aliases'] = json.loads(data['aliases'])
            except json.JSONDecodeError:
                data['aliases'] = []
        else:
            data['aliases'] = []

        if 'tags' in data and data['tags']:
            try:
                data['tags'] = json.loads(data['tags'])
            except json.JSONDecodeError:
                data['tags'] = []
        else:
            data['tags'] = []

        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])

        if 'updated_at' in data and data['updated_at']:
            if isinstance(data['updated_at'], str):
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])

        return cls(**data)


class ActressRepository:
    """女優資料存取層"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or connection.get_db_path()

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線"""
        return connection.get_connection(self.db_path)

    def _get_columns(self) -> List[str]:
        """取得欄位名稱列表"""
        return [
            'name', 'name_en', 'birth', 'height', 'cup',
            'bust', 'waist', 'hip', 'hometown', 'hobby',
            'aliases', 'agency', 'debut_work', 'tags', 'nickname',
            'blog_url', 'official_url', 'photo_source', 'primary_text_source',
            'created_at', 'updated_at',
        ]

    def save(self, actress: Actress) -> None:
        """新增或更新女優（根據 name 判斷）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            actress_dict = actress.to_dict()
            actress_dict.pop('created_at', None)
            actress_dict.pop('updated_at', None)

            columns = list(actress_dict.keys())
            placeholders = ', '.join(['?'] * len(columns))
            update_parts = [
                f"{col} = excluded.{col}"
                for col in columns
                if col != 'name'
            ]
            update_clause = ', '.join(update_parts)

            sql = f"""
                INSERT INTO actresses ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(name) DO UPDATE SET
                    {update_clause},
                    updated_at = CURRENT_TIMESTAMP
            """

            cursor.execute(sql, list(actress_dict.values()))
            conn.commit()
        finally:
            conn.close()

    def get_by_name(self, name: str) -> Optional[Actress]:
        """根據 name 查詢"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM actresses WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return Actress.from_row(row, self._get_columns())
            return None
        finally:
            conn.close()

    def delete_by_name(self, name: str) -> bool:
        """刪除女優資料

        Returns:
            bool: 是否成功刪除（不存在則回 False）
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM actresses WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_all(self) -> List[Actress]:
        """取得所有女優"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM actresses ORDER BY name")
            rows = cursor.fetchall()
            return [Actress.from_row(row, self._get_columns()) for row in rows]
        finally:
            conn.close()

    def exists(self, name: str) -> bool:
        """檢查女優是否存在"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM actresses WHERE name = ?", (name,))
            row = cursor.fetchone()
            return bool(row and row[0] > 0)
        finally:
            conn.close()

    def count_videos_for_actress_names(self, names: set) -> int:
        """Count videos where any actress name in `names` appears in the actresses JSON array.

        Uses COUNT(DISTINCT videos.rowid) to avoid double-counting a video that
        lists multiple aliases of the same actress.
        """
        if not names:
            return 0
        placeholders = ",".join("?" * len(names))
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"""SELECT COUNT(DISTINCT videos.rowid) FROM videos, json_each(videos.actresses)
                   WHERE json_valid(videos.actresses) AND json_each.value IN ({placeholders})""",
                tuple(names),
            )
            return cursor.fetchone()[0]
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()

    def count_videos_for_actress(self, name: str) -> int:
        """Count videos featuring this actress (backward-compatible single-name wrapper)."""
        return self.count_videos_for_actress_names({name})
