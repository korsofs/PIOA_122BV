from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from src.db.backend.errors import (
    ValidationError,
    DuplicateKeyError,
    RecordNotFoundError,
    TableNotFoundError,
)


@dataclass
class MemoryTable:
    name: str
    key_field: str
    fields: list[str]
    records: list[dict[str, Any]] = field(default_factory=list)

    def _validate_record_shape(self, record: dict[str, Any]) -> None:
        if not isinstance(record, dict):
            raise ValidationError("Запись должна быть словарём.")

        unknown_fields = [field_name for field_name in record if field_name not in self.fields]
        if unknown_fields:
            raise ValidationError(
                f"Неизвестные поля записи: {', '.join(unknown_fields)}"
            )

        missing_fields = [field_name for field_name in self.fields if field_name not in record]
        if missing_fields:
            raise ValidationError(
                f"Отсутствуют поля записи: {', '.join(missing_fields)}"
            )

        if record.get(self.key_field) in (None, ""):
            raise ValidationError(f"Поле {self.key_field} обязательно.")

    def _validate_filters(self, filters: dict[str, Any]) -> None:
        unknown_fields = [field_name for field_name in filters if field_name not in self.fields]
        if unknown_fields:
            raise ValidationError(
                f"Неизвестные поля фильтра: {', '.join(unknown_fields)}"
            )

    def _matches(self, record: dict[str, Any], filters: dict[str, Any]) -> bool:
        for field_name, expected_value in filters.items():
            if expected_value in (None, ""):
                continue

            actual_value = record.get(field_name)
            if str(actual_value).lower() != str(expected_value).lower():
                return False

        return True

    def create_record(self, record: dict[str, Any]) -> dict[str, Any]:
        self._validate_record_shape(record)

        key_value = record[self.key_field]
        if any(existing[self.key_field] == key_value for existing in self.records):
            raise DuplicateKeyError(
                f"Запись с {self.key_field}={key_value} уже существует."
            )

        normalized = {field_name: record[field_name] for field_name in self.fields}
        self.records.append(normalized)

        return deepcopy(normalized)

    def select_records(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        self._validate_filters(filters)

        result: list[dict[str, Any]] = []
        for record in self.records:
            if self._matches(record, filters):
                result.append(deepcopy(record))  # deepcopy
        return result

    def get_by_key(self, key_value: Any) -> dict[str, Any]:
        for record in self.records:
            if record[self.key_field] == key_value:
                return deepcopy(record)
        raise RecordNotFoundError(
            f"Запись с {self.key_field}={key_value} не найдена."
        )

    def update_record(self, key_value: Any, updates: dict[str, Any]) -> dict[str, Any]:
        if not updates:
            raise ValidationError("Нет данных для обновления.")

        unknown_fields = [field_name for field_name in updates if field_name not in self.fields]
        if unknown_fields:
            raise ValidationError(
                f"Неизвестные поля обновления: {', '.join(unknown_fields)}"
            )

        if self.key_field in updates and updates[self.key_field] != key_value:
            raise ValidationError("Изменение ключевого поля запрещено.")

        for record in self.records:
            if record[self.key_field] == key_value:
                for field_name, value in updates.items():
                    if field_name != self.key_field:
                        record[field_name] = value
                return deepcopy(record)

        raise RecordNotFoundError(
            f"Запись с {self.key_field}={key_value} не найдена."
        )

    def delete_record(self, key_value: Any) -> dict[str, Any]:
        for index, record in enumerate(self.records):
            if record[self.key_field] == key_value:
                removed = self.records.pop(index)
                return deepcopy(removed)

        raise RecordNotFoundError(
            f"Запись с {self.key_field}={key_value} не найдена."
        )

    def sort_records(self, field_name: str, descending: bool = False) -> list[dict[str, Any]]:
        if field_name not in self.fields:
            raise ValidationError(f"Поле {field_name} не существует в таблице.")

        return sorted(
            (deepcopy(record) for record in self.records),
            key=lambda x: x.get(field_name),
            reverse=descending
        )


class InMemoryDatabase:
    def __init__(self) -> None:
        self.tables: dict[str, MemoryTable] = {}

    def create_table(self, name: str, key_field: str, fields: list[str]) -> MemoryTable:
        name = name.strip()
        key_field = key_field.strip()
        fields = [field_name.strip() for field_name in fields if field_name.strip()]

        if not name:
            raise ValidationError("Имя таблицы не может быть пустым.")
        if not key_field:
            raise ValidationError("Ключевое поле не может быть пустым.")
        if not fields:
            raise ValidationError("Список полей не может быть пустым.")
        if name in self.tables:
            raise DuplicateKeyError(f"Таблица {name} уже существует.")
        if len(set(fields)) != len(fields):
            raise ValidationError("Имена полей таблицы должны быть уникальными.")
        if key_field not in fields:
            raise ValidationError("Ключевое поле должно входить в список полей.")

        table = MemoryTable(name=name, key_field=key_field, fields=fields)
        self.tables[name] = table
        return table

    def get_table(self, name: str) -> MemoryTable:
        name = name.strip()
        if name not in self.tables:
            raise TableNotFoundError(f"Таблица {name} не найдена.")
        return self.tables[name]

    def list_tables(self) -> list[str]:
        return sorted(self.tables.keys())

    def delete_table(self, name: str) -> None:
        name = name.strip()
        if name not in self.tables:
            raise TableNotFoundError(f"Таблица {name} не найдена.")
        del self.tables[name]


def build_default_database() -> InMemoryDatabase:
    db = InMemoryDatabase()

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
