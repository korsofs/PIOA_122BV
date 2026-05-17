from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .database import Database
from .errors import DatabaseError, DuplicateKeyError, TableNotFoundError, ValidationError
from .table import Table

CSV_MAGIC = "__csvdb__"


class StorageError(DatabaseError):
    """Ошибки чтения и записи CSV-хранилища."""


CSVTable = Table


class CSVDatabase(Database):
    def __init__(self, storage_dir: str | Path = "data") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _table_path(self, name: str) -> Path:
        return self.storage_dir / f"{name}.csv"

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

        table = CSVTable(name=name, key_field=key_field, fields=fields)
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
            with path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
        except OSError as error:
            raise StorageError(f"Не удалось прочитать таблицу {name}.") from error

        table = self._table_from_rows(name, rows)
        self._attach_autosave(table)
        return table

    def list_tables(self) -> list[str]:
        return sorted(path.stem for path in self.storage_dir.glob("*.csv"))

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
            with tmp_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        CSV_MAGIC,
                        table.name,
                        table.key_field,
                        json.dumps(table.fields, ensure_ascii=False),
                        json.dumps(table.list_indexes(), ensure_ascii=False),
                    ]
                )
                for record in table.records:
                    writer.writerow(
                        [self._encode_cell(record[field_name]) for field_name in table.fields]
                    )
            tmp_path.replace(path)
        except (OSError, TypeError, ValueError) as error:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            raise StorageError(f"Не удалось сохранить таблицу {table.name}.") from error

    def _table_from_rows(self, requested_name: str, rows: list[list[str]]) -> Table:
        if not rows:
            raise StorageError(f"Таблица {requested_name} имеет пустой CSV-файл.")

        header = rows[0]
        if len(header) < 4 or header[0] != CSV_MAGIC:
            raise StorageError(f"Таблица {requested_name} имеет некорректный CSV-заголовок.")

        stored_name = header[1].strip()
        key_field = header[2].strip()

        if not stored_name:
            raise StorageError(f"Таблица {requested_name} имеет пустое имя в CSV-заголовке.")
        if stored_name != requested_name:
            raise StorageError(
                f"Имя таблицы в CSV-файле ({stored_name}) не совпадает с ожидаемым ({requested_name})."
            )
        if not key_field:
            raise StorageError(f"Таблица {requested_name} имеет пустое ключевое поле в CSV-заголовке.")

        fields: list[str]
        indexes: list[list[str]]

        if len(header) >= 5:
            try:
                parsed_fields = json.loads(header[3])
                parsed_indexes = json.loads(header[4])
                if (
                    isinstance(parsed_fields, list)
                    and parsed_fields
                    and all(isinstance(item, str) for item in parsed_fields)
                    and isinstance(parsed_indexes, list)
                ):
                    fields = [item.strip() for item in parsed_fields if item.strip()]
                    indexes = parsed_indexes
                else:
                    raise ValueError
            except (json.JSONDecodeError, ValueError, TypeError):
                fields = [field_name.strip() for field_name in header[3:] if field_name.strip()]
                indexes = []
        else:
            fields = [field_name.strip() for field_name in header[3:] if field_name.strip()]
            indexes = []

        if not fields:
            raise StorageError(f"Таблица {requested_name} не содержит списка полей.")

        records: list[dict[str, Any]] = []
        for row_index, row in enumerate(rows[1:], start=2):
            if not row:
                continue
            if len(row) != len(fields):
                raise StorageError(
                    f"Строка {row_index} таблицы {requested_name} имеет неверное число столбцов."
                )

            record: dict[str, Any] = {}
            for field_name, raw_value in zip(fields, row):
                try:
                    record[field_name] = self._decode_cell(raw_value)
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    raise StorageError(
                        f"Не удалось прочитать значение поля {field_name} в таблице {requested_name}."
                    ) from error
            records.append(record)

        try:
            return CSVTable.from_dict(
                requested_name,
                {
                    "key_field": key_field,
                    "columns": fields,
                    "records": records,
                    "indexes": indexes,
                },
            )
        except ValidationError as error:
            raise StorageError(f"Таблица {requested_name} имеет некорректную структуру.") from error

    @staticmethod
    def _encode_cell(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _decode_cell(raw_value: str) -> Any:
        return json.loads(raw_value)


def build_default_database(storage_dir: str | Path = "data") -> CSVDatabase:
    db = CSVDatabase(storage_dir=storage_dir)
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
