import builtins
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.db.backend.database import Database
from src.db.backend.errors import (
    DuplicateKeyError,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
)
from src.db.backend.file import (
    FileDatabase,
    FileTable,
    StorageError,
    build_default_database as build_file_default_database,
)
from src.db.backend.memory import (
    InMemoryDatabase,
    build_default_database as build_memory_default_database,
)
from src.db.backend.table import Table
from src.db.tui import ConsoleApp, _choose_database, main as tui_main


def make_patient(patient_id: int = 101, name: str = "Иванов Иван Иванович") -> dict[str, object]:
    return {
        "PatientID": patient_id,
        "FullName": name,
        "Gender": "M",
        "BirthDate": "15.03.1980",
        "Email": "ivanov@mail.ru",
        "Phone": "+79999999999",
        "Address": "Г. Москва, ул. Ленина, 10",
        "PolicyNumber": "1234567890",
        "InsuranceCompany": "Росгосстрах",
        "Passport": "4010 123456",
        "EmergencyContact": "+79999999989",
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


class TestFileDatabaseExtraCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = build_file_default_database(storage_dir=self.temp_dir.name)
        self.patients = self.db.get_table("patients")

        self.patient_1 = make_patient(101, "Иванов Иван Иванович")
        self.patient_2 = make_patient(102, "Сидоров Сидор Сидорович")
        self.patient_3 = make_patient(103, "Петров Петр Петрович")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_table_validation_branches(self) -> None:
        with self.assertRaises(ValidationError):
            self.db.create_table("", "id", ["id"])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "", ["id"])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "id", [])

        with self.assertRaises(ValidationError):
            self.db.create_table("docs", "id", ["name", "age"])

    def test_create_duplicate_table_raises(self) -> None:
        with self.assertRaises(DuplicateKeyError):
            self.db.create_table(
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

    def test_list_tables_is_sorted(self) -> None:
        self.db.create_table("z_table", "id", ["id", "name"])
        self.db.create_table("a_table", "id", ["id", "name"])
        self.assertEqual(self.db.list_tables(), ["a_table", "patients", "z_table"])

    def test_save_reload_update_delete_flow(self) -> None:
        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)

        reloaded = FileDatabase(self.temp_dir.name)
        table = reloaded.get_table("patients")
        self.assertEqual(len(table.select_records()), 2)

        table.update_record(101, {"Email": "new@mail.ru"})
        updated = FileDatabase(self.temp_dir.name).get_table("patients")
        self.assertEqual(updated.get_by_key(101)["Email"], "new@mail.ru")

        updated.delete_record(102)
        after_delete = FileDatabase(self.temp_dir.name).get_table("patients")
        self.assertEqual(len(after_delete.select_records()), 1)
        self.assertEqual(after_delete.get_by_key(101)["PatientID"], 101)

    def test_get_table_error_branches(self) -> None:
        with self.assertRaises(ValidationError):
            self.db.get_table("")

        with self.assertRaises(TableNotFoundError):
            self.db.get_table("missing")

    def test_get_table_invalid_json_raises_storage_error(self) -> None:
        path = Path(self.temp_dir.name) / "broken.json"
        path.write_text("{not valid json}", encoding="utf-8")

        with self.assertRaises(StorageError):
            self.db.get_table("broken")

    def test_get_table_invalid_structure_raises_storage_error(self) -> None:
        path = Path(self.temp_dir.name) / "broken2.json"
        path.write_text(
            json.dumps({"columns": [], "records": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        with self.assertRaises(StorageError):
            self.db.get_table("broken2")

    def test_get_table_read_oserror_raises_storage_error(self) -> None:
        path = Path(self.temp_dir.name) / "broken3.json"
        path.write_text(
            json.dumps(
                {
                    "columns": ["id", "name"],
                    "records": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with patch.object(Path, "read_text", side_effect=OSError("read failed")):
            with self.assertRaises(StorageError):
                self.db.get_table("broken3")

    def test_save_table_write_error_raises_storage_error(self) -> None:
        with patch.object(Path, "write_text", side_effect=OSError("write failed")):
            with self.assertRaises(StorageError):
                self.db.create_table("write_fail", "id", ["id", "name"])

    def test_save_table_replace_error_raises_storage_error(self) -> None:
        with patch.object(Path, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(StorageError):
                self.db.create_table("replace_fail", "id", ["id", "name"])

    def test_delete_table_success_and_errors(self) -> None:
        self.db.create_table("to_delete", "id", ["id", "name"])
        self.assertIn("to_delete", self.db.list_tables())

        self.db.delete_table("to_delete")
        self.assertNotIn("to_delete", self.db.list_tables())

        with self.assertRaises(ValidationError):
            self.db.delete_table("")

        with self.assertRaises(TableNotFoundError):
            self.db.delete_table("missing")

    def test_delete_table_unlink_error_raises_storage_error(self) -> None:
        self.db.create_table("unlink_fail", "id", ["id", "name"])

        with patch.object(Path, "unlink", side_effect=OSError("unlink failed")):
            with self.assertRaises(StorageError):
                self.db.delete_table("unlink_fail")

    def test_build_default_database_does_not_duplicate_existing_patients_table(self) -> None:
        same_db = build_file_default_database(storage_dir=self.temp_dir.name)
        self.assertIn("patients", same_db.list_tables())

    def test_file_table_alias_and_roundtrip(self) -> None:
        self.assertTrue(FileTable is Table)

        self.patients.create_record(self.patient_1)
        data = self.patients.to_dict()
        restored = FileTable.from_dict("patients", data)
        self.assertEqual(restored.select_records(), [self.patient_1])

    def test_file_table_from_dict_invalid_inputs(self) -> None:
        with self.assertRaises(ValidationError):
            FileTable.from_dict("patients", "not a dict")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            FileTable.from_dict(
                "patients",
                {
                    "columns": "bad",
                    "records": [],
                },
            )

        with self.assertRaises(ValidationError):
            FileTable.from_dict(
                "patients",
                {
                    "columns": ["PatientID", "FullName"],
                    "records": "bad",
                },
            )

        with self.assertRaises(ValidationError):
            FileTable.from_dict(
                "patients",
                {
                    "columns": ["PatientID", "FullName"],
                    "records": [123],
                },
            )

    def test_file_table_validation_and_sorting_paths(self) -> None:
        table = FileTable(
            name="docs",
            key_field="id",
            fields=["id", "meta"],
        )

        with self.assertRaises(ValidationError):
            table.create_record("not a dict")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            table.create_record({"meta": 1})

        with self.assertRaises(ValidationError):
            table.select_records(filters=[] )  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            table.sort_records("unknown")

        table.create_record({"id": 1, "meta": {"a": 1}})
        self.assertEqual(table.get_by_key(1)["meta"]["a"], 1)
        self.assertEqual(len(table.select_records(filters={"id": 1})), 1)

    def test_file_table_update_and_delete_error_paths(self) -> None:
        table = FileTable(
            name="docs2",
            key_field="id",
            fields=["id", "name"],
        )
        table.create_record({"id": 1, "name": "one"})

        with self.assertRaises(ValidationError):
            table.update_record(1, "bad")  # type: ignore[arg-type]

        with self.assertRaises(ValidationError):
            table.update_record(1, {})

        with self.assertRaises(ValidationError):
            table.update_record(1, {"unknown": "x"})

        with self.assertRaises(ValidationError):
            table.update_record(1, {"id": 2})

        with self.assertRaises(RecordNotFoundError):
            table.update_record(999, {"name": "x"})

        with self.assertRaises(RecordNotFoundError):
            table.delete_record(999)

        self.assertEqual(table.delete_record(1)["id"], 1)


class TestMemoryExtraCoverage(unittest.TestCase):
    def test_memory_create_table_validation_paths(self) -> None:
        db = build_memory_default_database()

        with self.assertRaises(ValidationError):
            db.create_table("", "id", ["id"])

        with self.assertRaises(ValidationError):
            db.create_table("docs", "", ["id"])

        with self.assertRaises(ValidationError):
            db.create_table("docs", "id", [])

        with self.assertRaises(DuplicateKeyError):
            db.create_table(
                "patients",
                "PatientID",
                ["PatientID", "FullName"],
            )

        with self.assertRaises(ValidationError):
            db.create_table("docs", "id", ["id", "id"])

        with self.assertRaises(ValidationError):
            db.create_table("docs", "missing", ["id", "name"])

    def test_memory_delete_and_get_missing_table_errors(self) -> None:
        db = InMemoryDatabase()

        with self.assertRaises(TableNotFoundError):
            db.get_table("missing")

        with self.assertRaises(TableNotFoundError):
            db.delete_table("missing")


class TestTuiExtraCoverage(unittest.TestCase):
    def test_choose_database_memory_and_file_branches(self) -> None:
        with patch("builtins.input", return_value="1"):
            db = _choose_database()
            self.assertIsInstance(db, InMemoryDatabase)

        with patch("builtins.input", return_value="2"):
            db = _choose_database()
            self.assertIsInstance(db, FileDatabase)

    def test_consoleapp_internal_error_paths(self) -> None:
        app = ConsoleApp(db=build_memory_default_database())

        with self.assertRaises(ValidationError):
            app._get_current_table()

        app.current_table_name = "patients"
        table = app.db.get_table("patients")

        with patch.object(ConsoleApp, "_read_value", side_effect=["", "x", "y"]):
            with self.assertRaises(ValidationError):
                app._read_record_for_table(table)

        with patch.object(ConsoleApp, "_read_value", side_effect=["101"]):
            with patch("builtins.input", side_effect=["", "", ""]):
                with self.assertRaises(ValidationError):
                    app._read_updates_for_table(table)

        with patch.object(ConsoleApp, "_read_value", side_effect=["PatientID", "wrong"]):
            with self.assertRaises(ValidationError):
                app._sort_records(table)

    def test_tui_main_uses_file_database_branch(self) -> None:
        fake_db = object()

        with patch("builtins.input", return_value="2"), patch(
            "src.db.tui.build_file_database",
            return_value=fake_db,
        ), patch("src.db.tui.ConsoleApp.run", return_value=None):
            tui_main()
