from typing import Any

from src.db.backend.errors import DatabaseError, ValidationError
from src.db.backend.file import FileDatabase, build_default_database as build_file_database
from src.db.backend.memory import InMemoryDatabase, build_default_database as build_memory_database


class ConsoleApp:
    def __init__(self, db: InMemoryDatabase | FileDatabase | None = None) -> None:
        self.db = db if db is not None else build_memory_database()
        self.current_table_name: str = ""

    def _read_value(self, prompt: str) -> str:
        return input(prompt).strip()

    def _parse_value(self, raw: str) -> Any:
        raw = raw.strip()
        if raw == "":
            return ""
        if raw.isdigit():
            return int(raw)
        if raw.startswith("-") and raw[1:].isdigit():
            return int(raw)
        return raw

    def _print_records(self, records: list[dict[str, Any]]) -> None:
        if not records:
            print("Записи не найдены.")
            return

        for index, record in enumerate(records, start=1):
            print("-" * 60)
            print(f"Запись {index}")
            for field_name, value in record.items():
                print(f"{field_name}: {value}")
        print("-" * 60)

    def _print_tables(self) -> None:
        tables = self.db.list_tables()
        if not tables:
            print("Таблиц пока нет.")
            return

        print("Список таблиц:")
        for table_name in tables:
            table = self.db.get_table(table_name)
            print(f"- {table.name} (ключ: {table.key_field}, поля: {', '.join(table.fields)})")

    def _choose_table(self) -> None:
        self._print_tables()
        table_name = self._read_value("Введите имя таблицы: ")
        self.db.get_table(table_name)
        self.current_table_name = table_name
        print(f"Выбрана таблица {self.current_table_name}.")

    def _create_table(self) -> None:
        print("Создание новой таблицы.")
        table_name = self._read_value("Имя таблицы: ")
        key_field = self._read_value("Ключевое поле: ")
        fields_line = self._read_value("Поля через запятую: ")

        fields = [field_name.strip() for field_name in fields_line.split(",") if field_name.strip()]
        table = self.db.create_table(table_name, key_field, fields)
        self.current_table_name = table.name
        print(f"Таблица {table.name} создана и выбрана.")

    def _get_current_table(self):
        if not self.current_table_name:
            raise ValidationError("Сначала создайте или выберите таблицу.")
        return self.db.get_table(self.current_table_name)

    def _read_record_for_table(self, table) -> dict[str, Any]:
        print(f"Добавление записи в таблицу {table.name}.")
        record: dict[str, Any] = {}

        for field_name in table.fields:
            raw_value = self._read_value(f"{field_name}: ")
            value = self._parse_value(raw_value)
            if field_name == table.key_field and value == "":
                raise ValidationError(f"Поле {table.key_field} обязательно.")
            record[field_name] = value

        return record

    def _read_filters_for_table(self, table) -> dict[str, Any]:
        print("Введите фильтры. Пустое значение пропускается.")
        filters: dict[str, Any] = {}

        for field_name in table.fields:
            raw_value = self._read_value(f"{field_name}: ")
            value = self._parse_value(raw_value)
            if value != "":
                filters[field_name] = value

        return filters

    def _read_updates_for_table(self, table):
        key_raw = self._read_value(f"Введите {table.key_field}: ")
        key_value = self._parse_value(key_raw)

        updates = {}
        for field in table.fields:
            if field == table.key_field:
                continue

            try:
                value = input(f"{field}: ")
            except StopIteration:
                break

            value = value.strip()

            if value == "":
                continue

            updates[field] = self._parse_value(value)

        if not updates:
            raise ValidationError("Нет данных для обновления.")

        return key_value, updates

    def _read_key_for_delete(self, table) -> Any:
        raw_key = self._read_value(f"Введите {table.key_field} для удаления: ")
        key_value = self._parse_value(raw_key)
        if key_value == "":
            raise ValidationError(f"{table.key_field} обязателен.")
        return key_value

    def _sort_records(self, table) -> None:
        field_name = self._read_value("Поле сортировки: ")
        order = self._read_value("Порядок (asc/desc): ").lower()

        if field_name not in table.fields:
            raise ValidationError(f"Поле {field_name} не существует в таблице.")
        if order not in {"asc", "desc"}:
            raise ValidationError("Порядок должен быть asc или desc.")

        descending = order == "desc"
        records = table.sort_records(field_name, descending=descending)
        self._print_records(records)

    def run(self) -> None:
        while True:
            print("\nБаза данных")
            print(f"Текущая таблица: {self.current_table_name or 'не выбрана'}")
            print("1. Показать список таблиц")
            print("2. Создать таблицу")
            print("3. Выбрать таблицу")
            print("4. Добавить запись")
            print("5. Показать все записи")
            print("6. Найти записи по фильтрам")
            print("7. Обновить запись")
            print("8. Удалить запись")
            print("9. Удалить таблицу")
            print("10. Сортировать записи")
            print("0. Выход")

            choice = self._read_value("Выберите пункт: ")

            try:
                if choice == "1":
                    self._print_tables()

                elif choice == "2":
                    self._create_table()

                elif choice == "3":
                    self._choose_table()

                elif choice == "4":
                    table = self._get_current_table()
                    record = self._read_record_for_table(table)
                    created = table.create_record(record)
                    print("Запись добавлена:")
                    self._print_records([created])

                elif choice == "5":
                    table = self._get_current_table()
                    self._print_records(table.select_records())

                elif choice == "6":
                    table = self._get_current_table()
                    filters = self._read_filters_for_table(table)
                    self._print_records(table.select_records(filters=filters))

                elif choice == "7":
                    table = self._get_current_table()
                    key_value, updates = self._read_updates_for_table(table)
                    updated = table.update_record(key_value, updates)
                    print("Запись обновлена:")
                    self._print_records([updated])

                elif choice == "8":
                    table = self._get_current_table()
                    key_value = self._read_key_for_delete(table)
                    removed = table.delete_record(key_value)
                    print("Запись удалена:")
                    self._print_records([removed])

                elif choice == "9":
                    table_name = self._read_value("Введите имя таблицы для удаления: ")
                    self.db.delete_table(table_name)
                    print(f"Таблица {table_name} удалена.")
                    tables = self.db.list_tables()
                    self.current_table_name = tables[0] if tables else ""

                elif choice == "10":
                    table = self._get_current_table()
                    self._sort_records(table)

                elif choice == "0":
                    print("Выход.")
                    break

                else:
                    print("Неизвестная команда.")

            except DatabaseError as error:
                print(f"Ошибка: {error}")
            except Exception as error:
                print(f"Непредвиденная ошибка: {error}")


def _choose_database() -> InMemoryDatabase | FileDatabase:
    print("Выберите тип базы данных:")
    print("1. В памяти")
    print("2. Файловая (JSON)")
    choice = input("Введите пункт: ").strip()

    if choice == "2":
        return build_file_database("data")
    return build_memory_database()


def main() -> None:
    db = _choose_database()
    app = ConsoleApp(db=db)
    app.run()