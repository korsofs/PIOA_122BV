from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import DuplicateKeyError, RecordNotFoundError, ValidationError

SaveCallback = Callable[[], None] | None


@dataclass
class Table:
    name: str
    key_field: str
    fields: list[str]
    records: list[dict[str, Any]] = field(default_factory=list)
    _on_change: SaveCallback = field(default=None, repr=False, compare=False)

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

        original_records = list(self.records)
        self.records = []
        for record in original_records:
            self._append_record_without_touch(record)

        self._ensure_unique_keys()

    def _touch(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _append_record_without_touch(self, record: dict[str, Any]) -> dict[str, Any]:
        self._validate_record_shape(record)
        normalized = {field_name: record[field_name] for field_name in self.fields}
        self.records.append(normalized)
        return normalized

    def _ensure_unique_keys(self) -> None:
        seen: set[Any] = set()
        for record in self.records:
            key_value = record[self.key_field]
            if key_value in seen:
                raise ValidationError(
                    f"Запись с {self.key_field}={key_value} уже существует."
                )
            seen.add(key_value)

    def _validate_record_shape(self, record: dict[str, Any]) -> None:
        if not isinstance(record, dict):
            raise ValidationError("Запись должна быть словарём.")

        unknown_fields = [field_name for field_name in record if field_name not in self.fields]
        if unknown_fields:
            raise ValidationError(f"Неизвестные поля записи: {', '.join(unknown_fields)}")

        missing_fields = [field_name for field_name in self.fields if field_name not in record]
        if missing_fields:
            raise ValidationError(f"Отсутствуют поля записи: {', '.join(missing_fields)}")

        if record.get(self.key_field) in (None, ""):
            raise ValidationError(f"Поле {self.key_field} обязательно.")

    def _validate_filters(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        if filters is None:
            return {}
        if not isinstance(filters, dict):
            raise ValidationError("Фильтры должны быть словарём.")

        unknown_fields = [field_name for field_name in filters if field_name not in self.fields]
        if unknown_fields:
            raise ValidationError(f"Неизвестные поля фильтра: {', '.join(unknown_fields)}")

        return filters

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

        normalized = self._append_record_without_touch(record)
        self._touch()
        return deepcopy(normalized)

    def select_records(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = self._validate_filters(filters)

        if not filters:
            return [deepcopy(record) for record in self.records]

        result: list[dict[str, Any]] = []
        for record in self.records:
            if self._matches(record, filters):
                result.append(deepcopy(record))
        return result

    def get_by_key(self, key_value: Any) -> dict[str, Any]:
        for record in self.records:
            if record[self.key_field] == key_value:
                return deepcopy(record)
        raise RecordNotFoundError(
            f"Запись с {self.key_field}={key_value} не найдена."
        )

    def update_record(self, key_value: Any, updates: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(updates, dict):
            raise ValidationError("Обновления должны быть словарём.")
        if not updates:
            raise ValidationError("Нет данных для обновления.")

        unknown_fields = [field_name for field_name in updates if field_name not in self.fields]
        if unknown_fields:
            raise ValidationError(f"Неизвестные поля обновления: {', '.join(unknown_fields)}")

        if self.key_field in updates and updates[self.key_field] != key_value:
            raise ValidationError("Изменение ключевого поля запрещено.")

        for record in self.records:
            if record[self.key_field] == key_value:
                for field_name, value in updates.items():
                    if field_name != self.key_field:
                        record[field_name] = value
                self._touch()
                return deepcopy(record)

        raise RecordNotFoundError(
            f"Запись с {self.key_field}={key_value} не найдена."
        )

    def delete_record(self, key_value: Any) -> dict[str, Any]:
        for index, record in enumerate(self.records):
            if record[self.key_field] == key_value:
                removed = self.records.pop(index)
                self._touch()
                return deepcopy(removed)

        raise RecordNotFoundError(
            f"Запись с {self.key_field}={key_value} не найдена."
        )

    def sort_records(self, field_name: str, descending: bool = False) -> list[dict[str, Any]]:
        if field_name not in self.fields:
            raise ValidationError(f"Поле {field_name} не существует в таблице.")

        return sorted(
            (deepcopy(record) for record in self.records),
            key=lambda record: record.get(field_name),
            reverse=descending,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": list(self.fields),
            "records": [deepcopy(record) for record in self.records],
        }

    @classmethod
    def from_dict(
        cls,
        name: str,
        data: dict[str, Any],
        on_change: SaveCallback = None,
    ) -> "Table":
        if not isinstance(data, dict):
            raise ValidationError("Данные таблицы должны быть словарём.")

        columns = data.get("columns")
        records = data.get("records")

        if not isinstance(columns, list) or not columns or not all(isinstance(item, str) for item in columns):
            raise ValidationError("Поле 'columns' должно быть непустым списком строк.")
        if not isinstance(records, list):
            raise ValidationError("Поле 'records' должно быть списком записей.")

        normalized_records: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                raise ValidationError("Каждая запись должна быть словарём.")
            normalized_records.append(dict(record))

        return cls(
            name=name,
            key_field=columns[0],
            fields=list(columns),
            records=normalized_records,
            _on_change=on_change,
        )


FileTable = Table
