from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import DuplicateKeyError, RecordNotFoundError, ValidationError

SaveCallback = Callable[[], None] | None
IndexSpec = tuple[str, ...]


@dataclass
class Table:
    name: str
    key_field: str
    fields: list[str]
    records: list[dict[str, Any]] = field(default_factory=list)
    _on_change: SaveCallback = field(default=None, repr=False, compare=False)
    _indexed_fields: list[IndexSpec] = field(default_factory=list, repr=False, compare=False)
    _key_index: dict[Any, int] = field(default_factory=dict, repr=False, compare=False)
    _index_data: dict[IndexSpec, dict[tuple[str, ...], set[int]]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

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

        original_indexes = list(self._indexed_fields)
        self._indexed_fields = []
        for index_fields in original_indexes:
            self._indexed_fields.append(self._normalize_index_spec(index_fields))

        if len(set(self._indexed_fields)) != len(self._indexed_fields):
            raise ValidationError("Индексы таблицы должны быть уникальными.")

        self._ensure_unique_keys()
        self._rebuild_indexes()

    def _touch(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def _normalize_index_spec(self, fields: list[str] | tuple[str, ...]) -> IndexSpec:
        if not isinstance(fields, (list, tuple)):
            raise ValidationError("Индекс должен быть списком полей.")

        normalized: list[str] = []
        for field_name in fields:
            if not isinstance(field_name, str):
                raise ValidationError("Имена полей индекса должны быть строками.")

            field_name = field_name.strip()
            if field_name:
                normalized.append(field_name)

        if not normalized:
            raise ValidationError("Индекс должен содержать хотя бы одно поле.")
        if len(set(normalized)) != len(normalized):
            raise ValidationError("Поля индекса должны быть уникальными.")

        unknown_fields = [field_name for field_name in normalized if field_name not in self.fields]
        if unknown_fields:
            raise ValidationError(f"Неизвестные поля индекса: {', '.join(unknown_fields)}")

        return tuple(normalized)

    def _validate_index_fields(self, fields: list[str] | tuple[str, ...]) -> IndexSpec:
        index_spec = self._normalize_index_spec(fields)
        if index_spec in self._indexed_fields:
            raise DuplicateKeyError(
                f"Индекс по полям {', '.join(index_spec)} уже существует."
            )
        return index_spec

    def _rebuild_indexes(self) -> None:
        self._key_index = {}
        self._index_data = {index_spec: {} for index_spec in self._indexed_fields}

        for position, record in enumerate(self.records):
            key_value = record[self.key_field]
            try:
                self._key_index[key_value] = position
            except TypeError:
                pass

            for index_spec in self._indexed_fields:
                index_key = self._build_index_key(record, index_spec)
                bucket = self._index_data.setdefault(index_spec, {}).setdefault(index_key, set())
                bucket.add(position)

    def _build_index_key(self, source: dict[str, Any], fields: IndexSpec) -> tuple[str, ...]:
        return tuple(self._normalize_index_value(source[field_name]) for field_name in fields)

    @staticmethod
    def _normalize_index_value(value: Any) -> str:
        return str(value).casefold()

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
            if str(actual_value).casefold() != str(expected_value).casefold():
                return False
        return True

    def _best_index_for_filters(self, filters: dict[str, Any]) -> IndexSpec | None:
        active_filter_fields = {
            field_name
            for field_name, value in filters.items()
            if value not in (None, "")
        }

        candidates = [
            index_spec
            for index_spec in self._indexed_fields
            if set(index_spec).issubset(active_filter_fields)
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda item: (len(item), item), reverse=True)
        return candidates[0]

    def _positions_by_index(self, index_spec: IndexSpec, filters: dict[str, Any]) -> list[int]:
        index_key = self._build_index_key(filters, index_spec)
        positions = self._index_data.get(index_spec, {}).get(index_key, set())
        return sorted(positions)

    def _record_index_by_key(self, key_value: Any) -> int | None:
        try:
            return self._key_index.get(key_value)
        except TypeError:
            for position, record in enumerate(self.records):
                if record[self.key_field] == key_value:
                    return position
            return None

    def _key_exists(self, key_value: Any) -> bool:
        position = self._record_index_by_key(key_value)
        return position is not None

    def create_index(self, fields: list[str] | tuple[str, ...]) -> None:
        index_spec = self._validate_index_fields(fields)
        self._indexed_fields.append(index_spec)
        self._rebuild_indexes()
        self._touch()

    def drop_index(self, fields: list[str] | tuple[str, ...]) -> None:
        index_spec = self._normalize_index_spec(fields)
        if index_spec not in self._indexed_fields:
            raise ValidationError(f"Индекс по полям {', '.join(index_spec)} не найден.")

        self._indexed_fields.remove(index_spec)
        self._rebuild_indexes()
        self._touch()

    def list_indexes(self) -> list[list[str]]:
        return [list(index_spec) for index_spec in self._indexed_fields]

    def create_record(self, record: dict[str, Any]) -> dict[str, Any]:
        self._validate_record_shape(record)

        key_value = record[self.key_field]
        if self._key_exists(key_value):
            raise DuplicateKeyError(
                f"Запись с {self.key_field}={key_value} уже существует."
            )

        normalized = self._append_record_without_touch(record)
        self._rebuild_indexes()
        self._touch()
        return deepcopy(normalized)

    def select_records(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = self._validate_filters(filters)

        active_filters = {
            field_name: value
            for field_name, value in filters.items()
            if value not in (None, "")
        }
        if not active_filters:
            return [deepcopy(record) for record in self.records]

        index_spec = self._best_index_for_filters(active_filters)
        if index_spec is None:
            candidate_positions = range(len(self.records))
        else:
            candidate_positions = self._positions_by_index(index_spec, active_filters)

        result: list[dict[str, Any]] = []
        for position in candidate_positions:
            record = self.records[position]
            if self._matches(record, active_filters):
                result.append(deepcopy(record))
        return result

    def get_by_key(self, key_value: Any) -> dict[str, Any]:
        position = self._record_index_by_key(key_value)
        if position is not None:
            return deepcopy(self.records[position])

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

        position = self._record_index_by_key(key_value)
        if position is None:
            raise RecordNotFoundError(
                f"Запись с {self.key_field}={key_value} не найдена."
            )

        record = self.records[position]
        for field_name, value in updates.items():
            if field_name != self.key_field:
                record[field_name] = value

        self._rebuild_indexes()
        self._touch()
        return deepcopy(record)

    def delete_record(self, key_value: Any) -> dict[str, Any]:
        position = self._record_index_by_key(key_value)
        if position is None:
            raise RecordNotFoundError(
                f"Запись с {self.key_field}={key_value} не найдена."
            )

        removed = self.records.pop(position)
        self._rebuild_indexes()
        self._touch()
        return deepcopy(removed)

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
            "key_field": self.key_field,
            "columns": list(self.fields),
            "records": [deepcopy(record) for record in self.records],
            "indexes": self.list_indexes(),
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
        key_field = data.get("key_field")
        indexes = data.get("indexes", [])

        if not isinstance(columns, list) or not columns or not all(
            isinstance(item, str) for item in columns
        ):
            raise ValidationError("Поле 'columns' должно быть непустым списком строк.")
        if not isinstance(records, list):
            raise ValidationError("Поле 'records' должно быть списком записей.")

        if key_field is None:
            key_field = columns[0]
        if not isinstance(key_field, str) or not key_field.strip():
            raise ValidationError("Поле 'key_field' должно быть непустой строкой.")
        if key_field not in columns:
            raise ValidationError("Ключевое поле должно входить в список полей.")

        if indexes is None:
            indexes = []
        if not isinstance(indexes, list):
            raise ValidationError("Поле 'indexes' должно быть списком индексов.")

        normalized_records: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                raise ValidationError("Каждая запись должна быть словарём.")
            normalized_records.append(dict(record))

        normalized_indexes: list[IndexSpec] = []
        for index_fields in indexes:
            normalized_indexes.append(
                cls(
                    name=name,
                    key_field=key_field,
                    fields=list(columns),
                    records=[],
                )._normalize_index_spec(index_fields)
            )

        return cls(
            name=name,
            key_field=key_field,
            fields=list(columns),
            records=normalized_records,
            _on_change=on_change,
            _indexed_fields=normalized_indexes,
        )


FileTable = Table
