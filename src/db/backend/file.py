import json
from pathlib import Path
from typing import Any

from src.db.backend.database import Database
from src.db.backend.memory import (
    DuplicateKeyError,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
)
from src.db.backend.table import FileTable, Table


class StorageError(Exception):
    """Ошибка чтения или записи файловой базы данных."""


class FileDatabase(Database):
    def __init__(self, storage_dir: str | Path = "data") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_table(self, name: str, key_field: str, fields: list[str]) -> Table:
        name = name.strip()
        key_field = key_field.strip()
        fields = [field_name.strip() for field_name in fields if field_name.strip()]

        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")
        if not key_field:
            raise ValidationError("Ключевое поле не может быть пустым.")
        if not fields:
            raise ValidationError("Список полей не может быть пустым.")
        if key_field not in fields:
            raise ValidationError("Ключевое поле должно входить в список полей.")
        if self._table_path(name).exists():
            raise DuplicateKeyError(f"Таблица {name} уже существует.")

        columns = [key_field] + [field_name for field_name in fields if field_name != key_field]
        table = FileTable(name=name, key_field=key_field, fields=columns)
        self._attach_autosave(table)
        self._save_table(table)
        return table

    def get_table(self, name: str) -> Table:
        name = name.strip()
        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")

        table_path = self._table_path(name)
        if not table_path.exists():
            raise TableNotFoundError(f"Таблица {name} не найдена.")

        try:
            raw_data = table_path.read_text(encoding="utf-8")
            data = json.loads(raw_data)
        except OSError as error:
            raise StorageError(f"Не удалось прочитать таблицу {name}.") from error
        except json.JSONDecodeError as error:
            raise StorageError(f"Таблица {name} содержит некорректный JSON.") from error

        table = FileTable.from_dict(name=name, data=data)
        self._attach_autosave(table)
        return table

    def list_tables(self) -> list[str]:
        return sorted(path.stem for path in self.storage_dir.glob("*.json"))

    def delete_table(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")

        table_path = self._table_path(name)
        if not table_path.exists():
            raise TableNotFoundError(f"Таблица {name} не найдена.")

        try:
            table_path.unlink()
        except OSError as error:
            raise StorageError(f"Не удалось удалить таблицу {name}.") from error

    def _attach_autosave(self, table: Table) -> None:
        def save_current_table() -> None:
            self._save_table(table)

        table._on_change = save_current_table

    def _table_path(self, name: str) -> Path:
        return self.storage_dir / f"{name}.json"

    def _save_table(self, table: Table) -> None:
        table_path = self._table_path(table.name)
        tmp_path = table_path.with_suffix(".tmp")

        try:
            tmp_path.write_text(
                json.dumps(table.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(table_path)
        except OSError as error:
            raise StorageError(f"Не удалось сохранить таблицу {table.name}.") from error


def build_default_database(storage_dir: str | Path = "data") -> FileDatabase:
    db = FileDatabase(storage_dir=storage_dir)

    if "students" not in db.list_tables():
        db.create_table(
            name="students",
            key_field="student_id",
            fields=["student_id", "first_name", "second_name", "age", "sex"],
        )

    return db


__all__ = [
    "FileDatabase",
    "FileTable",
    "StorageError",
    "build_default_database",
    "DuplicateKeyError",
    "RecordNotFoundError",
    "TableNotFoundError",
    "ValidationError",
]