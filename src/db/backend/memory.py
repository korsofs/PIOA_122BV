from copy import deepcopy
from typing import Any

from src.db.backend.errors import (
    DuplicateKeyError,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
)
from src.db.backend.table import Table


class MemoryTable(Table):
    pass


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
