from __future__ import annotations

from typing import Any

from src.db.backend.memory import (
    DatabaseError,
    InMemoryDatabase,
    ValidationError,
    build_default_database,
)


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if raw == "":
        return ""
    if raw.isdigit():
        return int(raw)
    if raw.startswith("-") and raw[1:].isdigit():
        return int(raw)
    return raw


def _read_input(prompt: str) -> str:
    return input(prompt).strip()


def _print_records(records: list[dict[str, Any]]) -> None:
    if not records:
        print("Записи не найдены.")
        return

    for index, record in enumerate(records, start=1):
        print("-" * 60)
        print(f"Запись {index}")
        for field_name, value in record.items():
            print(f"{field_name}: {value}")
    print("-" * 60)


def _print_tables(db: InMemoryDatabase) -> None:
    tables = db.list_tables()
    if not tables:
        print("Таблиц пока нет.")
        return

    print("Список таблиц:")
    for name in tables:
        table = db.get_table(name)
        print(f"- {table.name} (ключ: {table.key_field}, поля: {', '.join(table.fields)})")


def _choose_table(db: InMemoryDatabase) -> str:
    _print_tables(db)
    table_name = _read_input("Введите имя таблицы: ")
    db.get_table(table_name)
    return table_name


def _create_table(db: InMemoryDatabase) -> str:
    print("Создание новой таблицы.")
    table_name = _read_input("Имя таблицы: ")
    key_field = _read_input("Ключевое поле: ")
    fields_line = _read_input("Поля через запятую: ")

    fields = [field_name.strip() for field_name in fields_line.split(",") if field_name.strip()]
    table = db.create_table(table_name, key_field, fields)
    print(f"Таблица {table.name} создана.")
    return table.name


def _read_record_for_table(table) -> dict[str, Any]:
    print(f"Добавление записи в таблицу {table.name}.")
    record: dict[str, Any] = {}

    for field_name in table.fields:
        raw_value = _read_input(f"{field_name}: ")
        value = _parse_value(raw_value)

        if field_name == table.key_field and value == "":
            raise ValidationError(f"Поле {table.key_field} обязательно.")

        record[field_name] = value

    return record


def _read_filters_for_table(table) -> dict[str, Any]:
    print("Введите фильтры. Пустое значение пропускается.")
    filters: dict[str, Any] = {}

    for field_name in table.fields:
        raw_value = _read_input(f"{field_name}: ")
        value = _parse_value(raw_value)
        if value != "":
            filters[field_name] = value

    return filters


def _update_record_for_table(table) -> tuple[Any, dict[str, Any]]:
    raw_key = _read_input(f"Введите {table.key_field} для обновления: ")
    key_value = _parse_value(raw_key)
    if key_value == "":
        raise ValidationError(f"{table.key_field} обязателен.")

    current_record = table.get_by_key(key_value)

    print("Введите новые значения. Пустое значение оставит поле без изменений.")
    updates: dict[str, Any] = {}

    for field_name in table.fields:
        if field_name == table.key_field:
            continue
        current_value = current_record.get(field_name, "")
        raw_value = input(f"{field_name} [{current_value}]: ").strip()
        if raw_value != "":
            updates[field_name] = _parse_value(raw_value)

    if not updates:
        raise ValidationError("Не введено ни одного нового значения.")

    return key_value, updates


def _delete_record_for_table(table) -> Any:
    raw_key = _read_input(f"Введите {table.key_field} для удаления: ")
    key_value = _parse_value(raw_key)
    if key_value == "":
        raise ValidationError(f"{table.key_field} обязателен.")
    return key_value


def run() -> None:
    db = build_default_database()
    current_table_name = "patients"

    while True:
        print("\nБД в оперативной памяти")
        print(f"Текущая таблица: {current_table_name}")
        print("1. Показать список таблиц")
        print("2. Создать таблицу")
        print("3. Выбрать таблицу")
        print("4. Добавить запись")
        print("5. Показать все записи")
        print("6. Найти записи по фильтрам")
        print("7. Обновить запись")
        print("8. Удалить запись")
        print("9. Удалить таблицу")
        print("0. Выход")

        choice = _read_input("Выберите пункт: ")

        try:
            if choice == "1":
                _print_tables(db)

            elif choice == "2":
                current_table_name = _create_table(db)

            elif choice == "3":
                current_table_name = _choose_table(db)
                print(f"Выбрана таблица {current_table_name}.")

            elif choice == "4":
                table = db.get_table(current_table_name)
                record = _read_record_for_table(table)
                created = table.create_record(record)
                print("Запись добавлена:")
                _print_records([created])

            elif choice == "5":
                table = db.get_table(current_table_name)
                records = table.select_records()
                _print_records(records)

            elif choice == "6":
                table = db.get_table(current_table_name)
                filters = _read_filters_for_table(table)
                records = table.select_records(filters)
                _print_records(records)

            elif choice == "7":
                table = db.get_table(current_table_name)
                key_value, updates = _update_record_for_table(table)
                updated = table.update_record(key_value, updates)
                print("Запись обновлена:")
                _print_records([updated])

            elif choice == "8":
                table = db.get_table(current_table_name)
                key_value = _delete_record_for_table(table)
                removed = table.delete_record(key_value)
                print("Запись удалена:")
                _print_records([removed])

            elif choice == "9":
                table_name = _read_input("Введите имя таблицы для удаления: ")
                db.delete_table(table_name)
                print(f"Таблица {table_name} удалена.")
                if current_table_name == table_name:
                    tables = db.list_tables()
                    current_table_name = tables[0] if tables else ""

            elif choice == "0":
                print("Выход.")
                break

            else:
                print("Неизвестная команда.")

        except DatabaseError as error:
            print(f"Ошибка: {error}")
        except Exception as error:
            print(f"Непредвиденная ошибка: {error}")