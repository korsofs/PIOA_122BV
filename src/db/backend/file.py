import json
from pathlib import Path

from .database import Database
from .errors import (
    DatabaseError,
    DuplicateKeyError,
    TableNotFoundError,
    ValidationError,
)
from .table import FileTable, Table


class StorageError(DatabaseError):
    pass


class FileDatabase(Database):
    def __init__(self, storage_dir: str | Path = "data") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _table_path(self, name: str) -> Path:
        return self.storage_dir / f"{name}.json"

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

        path = self._table_path(name)
        if path.exists():
            raise DuplicateKeyError(f"Таблица {name} уже существует.")

        table = FileTable(name=name, key_field=key_field, fields=fields)
        self._attach_autosave(table)
        self._save_table(table)
        return table

    def get_table(self, name: str) -> Table:
        name = name.strip()
        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")

        path = self._table_path(name)
        if not path.exists():
            raise TableNotFoundError(f"Таблица {name} не найдена.")

        try:
            raw_data = path.read_text(encoding="utf-8")
        except OSError as error:
            raise StorageError(f"Не удалось прочитать таблицу {name}.") from error

        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as error:
            raise StorageError(f"Таблица {name} содержит некорректный JSON.") from error

        try:
            table = FileTable.from_dict(name, data)
        except ValidationError as error:
            raise StorageError(f"Таблица {name} имеет некорректную структуру.") from error

        self._attach_autosave(table)
        return table

    def list_tables(self) -> list[str]:
        return sorted(path.stem for path in self.storage_dir.glob("*.json"))

    def delete_table(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")

        path = self._table_path(name)
        if not path.exists():
            raise TableNotFoundError(f"Таблица {name} не найдена.")

        try:
            path.unlink()
        except OSError as error:
            raise StorageError(f"Не удалось удалить таблицу {name}.") from error

    def _attach_autosave(self, table: Table) -> None:
        def save_current_table() -> None:
            self._save_table(table)

        table._on_change = save_current_table

    def _save_table(self, table: Table) -> None:
        path = self._table_path(table.name)
        tmp_path = path.with_suffix(".tmp")

        try:
            tmp_path.write_text(
                json.dumps(table.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(path)
        except OSError as error:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise StorageError(f"Не удалось сохранить таблицу {table.name}.") from error


def build_default_database(storage_dir: str | Path = "data") -> FileDatabase:
    db = FileDatabase(storage_dir=storage_dir)

    if "patients" not in db.list_tables():
        db.create_table(
            name="patients",
            key_field="PatientID",
            fields=[
                "PatientID",
                "FullName",
                "Gender",
                "BirthDate",
                "Email",
                "Phone",
                "Address",
                "PolicyNumber",
                "InsuranceCompany",
                "Passport",
                "EmergencyContact",
            ],
        )

    return db
