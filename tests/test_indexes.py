from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.db.backend.csv import (
    CSVDatabase,
    StorageError as CSVStorageError,
    build_default_database as build_csv_default_database,
)
from src.db.backend.database import Database
from src.db.backend.errors import (
    DuplicateKeyError,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
)
from src.db.backend.file import (
    FileDatabase,
    StorageError as FileStorageError,
    build_default_database as build_file_default_database,
)
from src.db.backend.memory import (
    InMemoryDatabase,
    build_default_database as build_memory_default_database,
)
from src.db.backend.table import Table
from src.db.tui import ConsoleApp, _choose_database, main as tui_main


def make_patient(
    patient_id: int = 101,
    name: str = "Иванов Иван Иванович",
    birth_date: str = "15.03.1980",
) -> dict[str, object]:
    return {
        "PatientID": patient_id,
        "FullName": name,
        "Gender": "M",
        "BirthDate": birth_date,
        "Email": "ivanov@mail.ru",
        "Phone": "+79999999999",
        "Address": "Г. Москва, ул. Ленина, 10",
        "PolicyNumber": "1234567890",
        "InsuranceCompany": "Росгосстрах",
        "Passport": "4010 123456",
        "EmergencyContact": "+79999999989",
    }


def make_simple_row(
    row_id: int,
    category: str = "alpha",
    name: str = "Alice",
    value: int = 10,
) -> dict[str, object]:
    return {
        "id": row_id,
        "category": category,
        "name": name,
        "value": value,
    }


class ConcreteDatabase(Database):
    def create_table(self, name: str, key_field: str, fields: list[str]) -> Table:
        return super().create_table(name, key_field, fields)

    def get_table(self, name: str) -> Table:
        return super().get_table(name)

    def list_tables(self) -> list[str]:
        return super().list_tables()

    def delete_table(self, name: str) -> None:
        return super().delete_table(name)


class TestDatabaseAbstractMethods(unittest.TestCase):
    def test_abstract_methods_raise_not_implemented(self) -> None:
        db = ConcreteDatabase()

        with self.assertRaises(NotImplementedError):
            db.create_table("x", "id", ["id"])

        with self.assertRaises(NotImplementedError):
            db.get_table("x")

        with self.assertRaises(NotImplementedError):
            db.list_tables()

        with self.assertRaises(NotImplementedError):
            db.delete_table("x")


class TestTableIndexes(unittest.TestCase):
    def setUp(self) -> None:
        self.table = Table(
            name="docs",
            key_field="id",
            fields=["id", "category", "name", "value"],
        )
        self.row_1 = make_simple_row(1, "alpha", "Alice", 10)
        self.row_2 = make_simple_row(2, "alpha", "Bob", 20)
        self.row_3 = make_simple_row(3, "beta", "Alice", 30)
        self.row_4 = make_simple_row(4, "beta", "Carol", 40)

        self.table.create_record(self.row_1)
        self.table.create_record(self.row_2)
        self.table.create_record(self.row_3)
        self.table.create_record(self.row_4)

    def test_create_index_and_list_indexes(self) -> None:
        self.assertEqual(self.table.list_indexes(), [])

        self.table.create_index(["category"])
        self.table.create_index(["category", "name"])

        self.assertEqual(self.table.list_indexes(), [["category"], ["category", "name"]])

    def test_create_duplicate_index_raises(self) -> None:
        self.table.create_index(["category"])
        with self.assertRaises(DuplicateKeyError):
            self.table.create_index(["category"])

    def test_create_index_validation_errors(self) -> None:
        with self.assertRaises(ValidationError):
            self.table.create_index([])

        with self.assertRaises(ValidationError):
            self.table.create_index(["unknown"])

        with self.assertRaises(ValidationError):
            self.table.create_index(["category", "category"])

    def test_drop_index(self) -> None:
        self.table.create_index(["category"])
        self.table.create_index(["category", "name"])

        self.table.drop_index(["category"])
        self.assertEqual(self.table.list_indexes(), [["category", "name"]])

        with self.assertRaises(ValidationError):
            self.table.drop_index(["category"])

    def test_select_records_uses_indexed_filters_correctly(self) -> None:
        self.table.create_index(["category"])
        self.table.create_index(["category", "name"])

        by_category = self.table.select_records(filters={"category": "alpha"})
        self.assertEqual([row["id"] for row in by_category], [1, 2])

        by_composite = self.table.select_records(filters={"category": "beta", "name": "Carol"})
        self.assertEqual([row["id"] for row in by_composite], [4])

        by_key = self.table.select_records(filters={"id": 3})
        self.assertEqual([row["name"] for row in by_key], ["Alice"])

    def test_select_records_with_non_indexed_filter_still_works(self) -> None:
        self.table.create_index(["category"])
        result = self.table.select_records(filters={"value": 40})
        self.assertEqual([row["id"] for row in result], [4])

    def test_select_records_with_empty_filters_returns_all_rows(self) -> None:
        self.table.create_index(["category"])
        result = self.table.select_records()
        self.assertEqual([row["id"] for row in result], [1, 2, 3, 4])

    def test_update_record_refreshes_indexes(self) -> None:
        self.table.create_index(["category"])
        self.table.create_index(["category", "name"])

        self.table.update_record(1, {"category": "beta", "name": "Zoe", "value": 99})

        old_result = self.table.select_records(filters={"category": "alpha", "name": "Alice"})
        new_result = self.table.select_records(filters={"category": "beta", "name": "Zoe"})

        self.assertEqual(old_result, [])
        self.assertEqual([row["id"] for row in new_result], [1])

    def test_delete_record_refreshes_indexes(self) -> None:
        self.table.create_index(["category"])
        self.table.create_index(["category", "name"])

        removed = self.table.delete_record(2)
        self.assertEqual(removed["id"], 2)

        after_delete = self.table.select_records(filters={"category": "alpha"})
        self.assertEqual([row["id"] for row in after_delete], [1])

        composite_after_delete = self.table.select_records(filters={"category": "alpha", "name": "Bob"})
        self.assertEqual(composite_after_delete, [])

    def test_create_record_after_index_creation_updates_index(self) -> None:
        self.table.create_index(["category"])
        self.table.create_index(["category", "name"])

        self.table.create_record(make_simple_row(5, "gamma", "Diana", 50))

        result = self.table.select_records(filters={"category": "gamma", "name": "Diana"})
        self.assertEqual([row["id"] for row in result], [5])

    def test_get_by_key_still_works_with_indexes(self) -> None:
        self.table.create_index(["category"])
        row = self.table.get_by_key(3)
        self.assertEqual(row["name"], "Alice")
        self.assertEqual(row["category"], "beta")

    def test_to_dict_and_from_dict_roundtrip_with_indexes(self) -> None:
        self.table.create_index(["category"])
        self.table.create_index(["category", "name"])

        data = self.table.to_dict()
        restored = Table.from_dict("docs", data)

        self.assertEqual(restored.list_indexes(), [["category"], ["category", "name"]])
        self.assertEqual(restored.select_records(filters={"category": "beta", "name": "Carol"})[0]["id"], 4)

    def test_from_dict_validation_errors(self) -> None:
        with self.assertRaises(ValidationError):
            Table.from_dict("docs", "bad")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            Table.from_dict("docs", {"columns": "bad", "records": []})

        with self.assertRaises(ValidationError):
            Table.from_dict("docs", {"columns": ["id", "name"], "records": "bad"})

        with self.assertRaises(ValidationError):
            Table.from_dict("docs", {"columns": ["id", "name"], "records": [123]})

    def test_table_validation_paths(self) -> None:
        with self.assertRaises(ValidationError):
            Table(name="", key_field="id", fields=["id"])

        with self.assertRaises(ValidationError):
            Table(name="docs", key_field="", fields=["id"])

        with self.assertRaises(ValidationError):
            Table(name="docs", key_field="id", fields=[])

        with self.assertRaises(ValidationError):
            Table(name="docs", key_field="missing", fields=["id", "name"])

        with self.assertRaises(ValidationError):
            Table(name="docs", key_field="id", fields=["id", "id"])

    def test_table_record_and_filter_validation(self) -> None:
        with self.assertRaises(ValidationError):
            self.table.create_record("not a dict")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            self.table.create_record({"name": "X", "category": "Y", "value": 1})

        with self.assertRaises(ValidationError):
            self.table.select_records(filters=[])  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            self.table.select_records(filters={"unknown": 1})

        with self.assertRaises(ValidationError):
            self.table.update_record(1, "bad")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            self.table.update_record(1, {})

        with self.assertRaises(ValidationError):
            self.table.update_record(1, {"unknown": "x"})

        with self.assertRaises(ValidationError):
            self.table.update_record(1, {"id": 2})

        with self.assertRaises(RecordNotFoundError):
            self.table.update_record(999, {"name": "x"})

        with self.assertRaises(RecordNotFoundError):
            self.table.delete_record(999)

        with self.assertRaises(ValidationError):
            self.table.sort_records("unknown")


class TestMemoryDatabaseAndPatients(unittest.TestCase):
    def setUp(self) -> None:
        self.db = build_memory_default_database()
        self.patients = self.db.get_table("patients")
        self.patient_1 = make_patient(101, "Иванов Иван Иванович", "15.03.1980")
        self.patient_2 = make_patient(102, "Сидоров Сидор Сидорович", "24.08.1992")
        self.patient_3 = make_patient(103, "Петров Петр Петрович", "11.01.1990")

    def test_default_database_contains_patients(self) -> None:
        self.assertIn("patients", self.db.list_tables())
        self.assertEqual(self.patients.key_field, "PatientID")
        self.assertIn("Email", self.patients.fields)

    def test_memory_create_get_delete_list_paths(self) -> None:
        with self.assertRaises(DuplicateKeyError):
            self.db.create_table("patients", "PatientID", ["PatientID", "FullName"])

        table = self.db.create_table("docs", "id", ["id", "name"])
        self.assertEqual(table.name, "docs")
        self.assertIn("docs", self.db.list_tables())

        self.assertIs(self.db.get_table("docs"), table)

        with self.assertRaises(TableNotFoundError):
            self.db.get_table("missing")

        self.db.delete_table("docs")
        self.assertNotIn("docs", self.db.list_tables())

        with self.assertRaises(TableNotFoundError):
            self.db.delete_table("missing")

    def test_memory_patients_flow_with_index(self) -> None:
        self.patients.create_index(["FullName"])
        self.patients.create_index(["Gender", "BirthDate"])

        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)
        self.patients.create_record(self.patient_3)

        by_name = self.patients.select_records(filters={"FullName": "Иванов Иван Иванович"})
        self.assertEqual([row["PatientID"] for row in by_name], [101])

        by_composite = self.patients.select_records(filters={"Gender": "M", "BirthDate": "24.08.1992"})
        self.assertEqual([row["PatientID"] for row in by_composite], [102])

        self.patients.update_record(101, {"Email": "new@mail.ru"})
        self.assertEqual(self.patients.get_by_key(101)["Email"], "new@mail.ru")

        self.patients.delete_record(102)
        remaining = self.patients.select_records()
        self.assertEqual([row["PatientID"] for row in remaining], [101, 103])

    def test_memory_patients_duplicate_key_and_not_found_errors(self) -> None:
        self.patients.create_record(self.patient_1)

        with self.assertRaises(DuplicateKeyError):
            self.patients.create_record(self.patient_1)

        with self.assertRaises(RecordNotFoundError):
            self.patients.get_by_key(999)

    def test_memory_build_default_database_is_usable(self) -> None:
        db = build_memory_default_database()
        self.assertIn("patients", db.list_tables())


class TestFileDatabaseAndPatients(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = build_file_default_database(storage_dir=self.temp_dir.name)
        self.patients = self.db.get_table("patients")
        self.patient_1 = make_patient(101, "Иванов Иван Иванович", "15.03.1980")
        self.patient_2 = make_patient(102, "Сидоров Сидор Сидорович", "24.08.1992")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_database_contains_patients(self) -> None:
        self.assertIn("patients", self.db.list_tables())
        self.assertEqual(self.patients.key_field, "PatientID")

    def test_file_database_basic_paths(self) -> None:
        with self.assertRaises(ValidationError):
            self.db.create_table("", "id", ["id"])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "", ["id"])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "id", [])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "id", ["name", "age"])

        with self.assertRaises(DuplicateKeyError):
            self.db.create_table(
                "patients",
                "PatientID",
                ["PatientID", "FullName"],
            )

        self.db.create_table("docs", "id", ["id", "name"])
        self.assertIn("docs", self.db.list_tables())

        with self.assertRaises(TableNotFoundError):
            self.db.get_table("missing")

        self.db.delete_table("docs")
        with self.assertRaises(TableNotFoundError):
            self.db.delete_table("docs")

    def test_file_patients_roundtrip_with_index(self) -> None:
        self.patients.create_index(["FullName"])
        self.patients.create_index(["Gender", "BirthDate"])

        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)
        self.patients.update_record(101, {"Email": "new@mail.ru"})

        reloaded = FileDatabase(self.temp_dir.name).get_table("patients")
        self.assertEqual(reloaded.list_indexes(), [["FullName"], ["Gender", "BirthDate"]])
        self.assertEqual(reloaded.get_by_key(101)["Email"], "new@mail.ru")

        result = reloaded.select_records(filters={"FullName": "Сидоров Сидор Сидорович"})
        self.assertEqual([row["PatientID"] for row in result], [102])

        reloaded.delete_record(102)
        after_delete = FileDatabase(self.temp_dir.name).get_table("patients")
        self.assertEqual([row["PatientID"] for row in after_delete.select_records()], [101])

    def test_file_storage_error_branches(self) -> None:
        bad_json = Path(self.temp_dir.name) / "broken.json"
        bad_json.write_text("{not valid json}", encoding="utf-8")
        with self.assertRaises(FileStorageError):
            self.db.get_table("broken")

        broken_structure = Path(self.temp_dir.name) / "broken2.json"
        broken_structure.write_text(
            json.dumps({"columns": [], "records": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaises(FileStorageError):
            self.db.get_table("broken2")

        with patch.object(Path, "read_text", side_effect=OSError("read failed")):
            with self.assertRaises(FileStorageError):
                self.db.get_table("patients")

        with patch.object(Path, "write_text", side_effect=OSError("write failed")):
            with self.assertRaises(FileStorageError):
                self.db.create_table("write_fail", "id", ["id", "name"])

        self.db.create_table("unlink_fail", "id", ["id", "name"])
        with patch.object(Path, "unlink", side_effect=OSError("unlink failed")):
            with self.assertRaises(FileStorageError):
                self.db.delete_table("unlink_fail")


class TestCSVDatabaseAndPatients(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = build_csv_default_database(storage_dir=self.temp_dir.name)
        self.patients = self.db.get_table("patients")
        self.patient_1 = make_patient(101, "Иванов Иван Иванович", "15.03.1980")
        self.patient_2 = make_patient(102, "Сидоров Сидор Сидорович", "24.08.1992")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_database_contains_patients(self) -> None:
        self.assertIn("patients", self.db.list_tables())
        self.assertEqual(self.patients.key_field, "PatientID")

    def test_csv_database_basic_paths(self) -> None:
        with self.assertRaises(ValidationError):
            self.db.create_table("", "id", ["id"])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "", ["id"])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "id", [])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "id", ["name", "age"])

        with self.assertRaises(DuplicateKeyError):
            self.db.create_table(
                "patients",
                "PatientID",
                ["PatientID", "FullName"],
            )

        self.db.create_table("docs", "id", ["id", "name"])
        self.assertIn("docs", self.db.list_tables())

        with self.assertRaises(TableNotFoundError):
            self.db.get_table("missing")

        self.db.delete_table("docs")
        with self.assertRaises(TableNotFoundError):
            self.db.delete_table("docs")

    def test_csv_patients_roundtrip_with_index(self) -> None:
        self.patients.create_index(["FullName"])
        self.patients.create_index(["Gender", "BirthDate"])

        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)
        self.patients.update_record(101, {"Email": "new@mail.ru"})

        reloaded = CSVDatabase(self.temp_dir.name).get_table("patients")
        self.assertEqual(reloaded.list_indexes(), [["FullName"], ["Gender", "BirthDate"]])
        self.assertEqual(reloaded.get_by_key(101)["Email"], "new@mail.ru")

        result = reloaded.select_records(filters={"FullName": "Сидоров Сидор Сидорович"})
        self.assertEqual([row["PatientID"] for row in result], [102])

        reloaded.delete_record(102)
        after_delete = CSVDatabase(self.temp_dir.name).get_table("patients")
        self.assertEqual([row["PatientID"] for row in after_delete.select_records()], [101])

    def test_csv_storage_error_branches(self) -> None:
        bad_csv = Path(self.temp_dir.name) / "broken.csv"
        bad_csv.write_text("not,a,valid,csv\n1,2\n", encoding="utf-8")
        with self.assertRaises(CSVStorageError):
            self.db.get_table("broken")

        broken_header = Path(self.temp_dir.name) / "broken2.csv"
        broken_header.write_text("wrong_magic,broken2,ID,[\"ID\"],[[]]\n", encoding="utf-8")
        with self.assertRaises(CSVStorageError):
            self.db.get_table("broken2")

        with patch.object(Path, "open", side_effect=OSError("open failed")):
            with self.assertRaises(CSVStorageError):
                self.db.get_table("patients")

        with patch.object(Path, "open", side_effect=OSError("write failed")):
            with self.assertRaises(CSVStorageError):
                self.db.create_table("write_fail", "id", ["id", "name"])

        self.db.create_table("unlink_fail", "id", ["id", "name"])
        with patch.object(Path, "unlink", side_effect=OSError("unlink failed")):
            with self.assertRaises(CSVStorageError):
                self.db.delete_table("unlink_fail")


class TestTuiBranches(unittest.TestCase):
    def test_choose_database_all_branches(self) -> None:
        with patch("builtins.input", return_value="1"):
            db = _choose_database()
            self.assertIsInstance(db, InMemoryDatabase)

        with patch("builtins.input", return_value="2"):
            db = _choose_database()
            self.assertIsInstance(db, FileDatabase)

        with patch("builtins.input", return_value="3"):
            db = _choose_database()
            self.assertIsInstance(db, CSVDatabase)

    def test_consoleapp_helper_branches(self) -> None:
        app = ConsoleApp(db=build_memory_default_database())

        with self.assertRaises(ValidationError):
            app._get_current_table()

        app.current_table_name = "patients"
        table = app.db.get_table("patients")

        with patch.object(ConsoleApp, "_read_value", side_effect=["PatientID", "asc"]):
            app._sort_records(table)

        with patch.object(ConsoleApp, "_read_value", side_effect=["unknown", "asc"]):
            with self.assertRaises(ValidationError):
                app._sort_records(table)

        with patch.object(ConsoleApp, "_read_value", side_effect=["PatientID", "wrong"]):
            with self.assertRaises(ValidationError):
                app._sort_records(table)

        with patch.object(ConsoleApp, "_read_value", side_effect=[""] * len(table.fields)):
            with self.assertRaises(ValidationError):
                app._read_record_for_table(table)

        with patch.object(ConsoleApp, "_read_value", side_effect=[""] * len(table.fields)):
            filters = app._read_filters_for_table(table)
            self.assertEqual(filters, {})

    def test_consoleapp_main_smoke(self) -> None:
        fake_db = object()

        with patch("builtins.input", return_value="1"), patch(
            "src.db.tui.ConsoleApp.run",
            return_value=None,
        ), patch("src.db.tui.build_memory_database", return_value=fake_db):
            tui_main()
