from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any

from src.db.backend.errors import (
    DuplicateRecordError,
    DuplicateTableError,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
)


def _normalize_text(value: Any) -> str:
    return str(value).strip().lower()


def _is_date_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value.strip(), "%d.%m.%Y")
        return True
    except ValueError:
        return False


def _sort_key(value: Any) -> tuple[int, Any]:
    if value is None:
        return (3, "")
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, str) and _is_date_string(value):
        return (1, datetime.strptime(value.strip(), "%d.%m.%Y").date())
    return (2, _normalize_text(value))


@dataclass
class Table:
    name: str
    key_field: str
    fields: list[str]
    records: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.key_field = self.key_field.strip()
        self.fields = [field_name.strip() for field_name in self.fields if field_name.strip()]

        if not self.name:
            raise ValidationError("Имя таблицы не может быть пустым.")
        if not self.key_field:
            raise ValidationError("Ключевое поле не может быть пустым.")
        if not self.fields:
            raise ValidationError("Список полей не может быть пустым.")
        if len(set(self.fields)) != len(self.fields):
            raise ValidationError("Имена полей таблицы должны быть уникальными.")
        if self.key_field not in self.fields:
            raise ValidationError("Ключевое поле должно входить в список полей.")

    def _validate_record(self, record: dict[str, Any]) -> None:
        if not isinstance(record, dict):
            raise ValidationError("Запись должна быть словарём.")

        unknown_fields = [name for name in record if name not in self.fields]
        if unknown_fields:
            raise ValidationError(f"Неизвестные поля записи: {', '.join(unknown_fields)}")

        missing_fields = [name for name in self.fields if name not in record]
        if missing_fields:
            raise ValidationError(f"Не хватает полей: {', '.join(missing_fields)}")

        if record.get(self.key_field) in (None, ""):
            raise ValidationError(f"Поле {self.key_field} обязательно.")

    def _validate_filters(self, filters: dict[str, Any]) -> None:
        unknown_fields = [name for name in filters if name not in self.fields]
        if unknown_fields:
            raise ValidationError(f"Неизвестные поля фильтра: {', '.join(unknown_fields)}")

    def _matches(self, record: dict[str, Any], filters: dict[str, Any]) -> bool:
        for field_name, expected in filters.items():
            actual = record.get(field_name)

            if expected in (None, ""):
                continue

            if isinstance(actual, str) and isinstance(expected, str):
                if _normalize_text(actual) != _normalize_text(expected):
                    return False
            else:
                if actual != expected:
                    return False

        return True

    def create_record(self, record: dict[str, Any]) -> dict[str, Any]:
        self._validate_record(record)

        key_value = record[self.key_field]
        if any(existing[self.key_field] == key_value for existing in self.records):
            raise DuplicateRecordError(
                f"Запись с {self.key_field}={key_value} уже существует."
            )

        normalized = {field_name: record[field_name] for field_name in self.fields}
        self.records.append(normalized)
        return normalized.copy()

    def select_records(
        self,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        self._validate_filters(filters)

        selected = [record.copy() for record in self.records if self._matches(record, filters)]

        if sort_by:
            sort_by = sort_by.strip()
            if sort_by not in self.fields:
                raise ValidationError(f"Неизвестное поле сортировки: {sort_by}")
            selected.sort(key=lambda record: _sort_key(record.get(sort_by)), reverse=descending)

        return selected

    def get_by_key(self, key_value: Any) -> dict[str, Any]:
        for record in self.records:
            if record[self.key_field] == key_value:
                return record
        raise RecordNotFoundError(f"Запись с {self.key_field}={key_value} не найдена.")

    def update_record(self, key_value: Any, updates: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(updates, dict):
            raise ValidationError("Изменения должны быть словарём.")
        if not updates:
            raise ValidationError("Нет данных для обновления.")

        unknown_fields = [name for name in updates if name not in self.fields]
        if unknown_fields:
            raise ValidationError(f"Неизвестные поля обновления: {', '.join(unknown_fields)}")

        if self.key_field in updates and updates[self.key_field] != key_value:
            raise ValidationError("Изменение ключевого поля запрещено.")

        record = self.get_by_key(key_value)
        for field_name, value in updates.items():
            if field_name != self.key_field:
                record[field_name] = value

        return record.copy()

    def delete_record(self, key_value: Any) -> dict[str, Any]:
        for index, record in enumerate(self.records):
            if record[self.key_field] == key_value:
                removed = self.records.pop(index)
                return removed.copy()

        raise RecordNotFoundError(f"Запись с {self.key_field}={key_value} не найдена.")

    def sort_records(self, field_name: str, descending: bool = False) -> list[dict[str, Any]]:
        return self.select_records(sort_by=field_name, descending=descending)


class MemoryDatabase:
    def __init__(self) -> None:
        self.tables: dict[str, Table] = {}

    def create_table(self, name: str, key_field: str, fields: list[str]) -> Table:
        name = name.strip()
        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")
        if name in self.tables:
            raise DuplicateTableError(f"Таблица {name} уже существует.")

        table = Table(name=name, key_field=key_field, fields=fields)
        self.tables[name] = table
        return table

    def get_table(self, name: str) -> Table:
        name = name.strip()
        if name not in self.tables:
            raise TableNotFoundError(f"Таблица {name} не найдена.")
        return self.tables[name]

    def delete_table(self, name: str) -> None:
        name = name.strip()
        if name not in self.tables:
            raise TableNotFoundError(f"Таблица {name} не найдена.")
        del self.tables[name]

    def list_tables(self) -> list[str]:
        return sorted(self.tables.keys())


def build_default_database() -> MemoryDatabase:
    db = MemoryDatabase()

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