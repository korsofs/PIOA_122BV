import json
from pathlib import Path
from typing import Any

from .database import Database
from .errors import DuplicateTableError, StorageError, TableNotFoundError, ValidationError
from .table import Table


class FileDatabase(Database):
    def __init__(self, storage_dir: str | Path = "data") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_table(self, name: str, key_field: str, fields: list[str]) -> Table:
        name = name.strip()
        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")

        table_path = self._table_path(name)
        if table_path.exists():
            raise DuplicateTableError(f"Таблица {name} уже существует.")

        table = Table(name=name, key_field=key_field, fields=list(fields))
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

        table = Table.from_dict(data)
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