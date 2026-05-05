import unittest
from unittest.mock import patch
import runpy
from src.db.backend import errors as backend_errors
from src.db.backend.memory import (
    DuplicateKeyError,
    InMemoryDatabase,
    MemoryTable,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
    build_default_database,
)
from src.db.tui import ConsoleApp

ConsoleValidationErrors = (ValidationError, backend_errors.ValidationError)


class TestMemoryDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = build_default_database()
        self.patients = self.db.get_table("patients")

        self.patient_1 = {
            "PatientID": 101,
            "FullName": "Иванов Иван Иванович",
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

        self.patient_2 = {
            "PatientID": 102,
            "FullName": "Сидоров Сидор Сидорович",
            "Gender": "M",
            "BirthDate": "24.08.1992",
            "Email": "sid@mail.ru",
            "Phone": "+79999999998",
            "Address": "Г. Москва, пр. Победы, 33",
            "PolicyNumber": "0987654321",
            "InsuranceCompany": "Согаз",
            "Passport": "4011 654321",
            "EmergencyContact": "+79999999979",
        }

        self.patient_3 = {
            "PatientID": 103,
            "FullName": "Петров Петр Петрович",
            "Gender": "M",
            "BirthDate": "10.06.1985",
            "Email": "petrov@mail.ru",
            "Phone": "+79999999997",
            "Address": "Г. Москва, ул. Гагарина, 5",
            "PolicyNumber": "1122334455",
            "InsuranceCompany": "ВТБ",
            "Passport": "4012 111222",
            "EmergencyContact": "+79999999969",
        }

    def test_default_database_has_patients_table(self) -> None:
        table = self.db.get_table("patients")
        self.assertIsInstance(table, MemoryTable)

    def test_create_table(self) -> None:
        table = self.db.create_table(
            name="doctors",
            key_field="DoctorID",
            fields=["DoctorID", "FullName", "Specialty"],
        )
        self.assertEqual(table.name, "doctors")
        self.assertIn("doctors", self.db.list_tables())

    def test_create_duplicate_table_raises(self) -> None:
        with self.assertRaises(DuplicateKeyError):
            self.db.create_table(
                name="patients",
                key_field="PatientID",
                fields=["PatientID", "FullName"],
            )

    def test_get_missing_table_raises(self) -> None:
        with self.assertRaises(TableNotFoundError):
            self.db.get_table("unknown")

    def test_add_record(self) -> None:
        created = self.patients.create_record(self.patient_1)
        self.assertEqual(created["PatientID"], 101)
        self.assertEqual(len(self.patients.select_records()), 1)

    def test_add_duplicate_record_raises(self) -> None:
        self.patients.create_record(self.patient_1)
        with self.assertRaises(DuplicateKeyError):
            self.patients.create_record(self.patient_1)

    def test_select_records_by_one_filter(self) -> None:
        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)
        result = self.patients.select_records(filters={"Gender": "M"})
        self.assertEqual(len(result), 2)

    def test_select_records_by_multiple_filters(self) -> None:
        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)
        self.patients.create_record(self.patient_3)

        result = self.patients.select_records(
            filters={"Gender": "M", "InsuranceCompany": "ВТБ"}
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["PatientID"], 103)

    def test_select_records_unknown_field_raises(self) -> None:
        with self.assertRaises(ValidationError):
            self.patients.select_records(filters={"Unknown": "value"})

    def test_update_record(self) -> None:
        self.patients.create_record(self.patient_1)
        updated = self.patients.update_record(
            101,
            {
                "Email": "new@mail.ru",
                "Phone": "+70000000000",
            },
        )
        self.assertEqual(updated["Email"], "new@mail.ru")
        self.assertEqual(updated["Phone"], "+70000000000")

    def test_update_record_rejects_non_dict(self) -> None:
        self.patients.create_record(self.patient_1)
        with self.assertRaises(ValidationError):
            self.patients.update_record(101, ["Email", "new@mail.ru"])  # type: ignore[arg-type]

    def test_update_record_rejects_key_change(self) -> None:
        self.patients.create_record(self.patient_1)
        with self.assertRaises(ValidationError):
            self.patients.update_record(101, {"PatientID": 999})

    def test_update_missing_record_raises(self) -> None:
        with self.assertRaises(RecordNotFoundError):
            self.patients.update_record(999, {"Email": "x@mail.ru"})

    def test_delete_record(self) -> None:
        self.patients.create_record(self.patient_1)
        removed = self.patients.delete_record(101)
        self.assertEqual(removed["PatientID"], 101)
        self.assertEqual(len(self.patients.select_records()), 0)

    def test_delete_missing_record_raises(self) -> None:
        with self.assertRaises(RecordNotFoundError):
            self.patients.delete_record(999)

    def test_multiple_tables_are_independent(self) -> None:
        doctors = self.db.create_table(
            name="doctors",
            key_field="DoctorID",
            fields=["DoctorID", "FullName", "Specialty"],
        )
        doctors.create_record(
            {
                "DoctorID": 1,
                "FullName": "Иванов И.И.",
                "Specialty": "Терапевт",
            }
        )
        self.patients.create_record(self.patient_1)

        self.assertEqual(len(doctors.select_records()), 1)
        self.assertEqual(len(self.patients.select_records()), 1)

    def test_get_by_key_returns_deep_copy(self) -> None:
        table = self.db.create_table(
            name="docs",
            key_field="ID",
            fields=["ID", "Meta"],
        )
        table.create_record({"ID": 1, "Meta": {"inner": {"value": 1}}})

        record = table.get_by_key(1)
        record["Meta"]["inner"]["value"] = 999

        stored = table.get_by_key(1)
        self.assertEqual(stored["Meta"]["inner"]["value"], 1)

    def test_select_records_returns_deep_copy(self) -> None:
        table = self.db.create_table(
            name="docs2",
            key_field="ID",
            fields=["ID", "Meta"],
        )
        table.create_record({"ID": 1, "Meta": {"inner": {"value": 1}}})

        selected = table.select_records()
        selected[0]["Meta"]["inner"]["value"] = 777

        stored = table.get_by_key(1)
        self.assertEqual(stored["Meta"]["inner"]["value"], 1)


class TestConsoleApp(unittest.TestCase):
    def setUp(self) -> None:
        self.app = ConsoleApp()
        self.doctors = self.app.db.create_table(
            name="doctors",
            key_field="DoctorID",
            fields=["DoctorID", "FullName", "Specialty"],
        )
        self.doctors.create_record(
            {
                "DoctorID": 1,
                "FullName": "Иванов И.И.",
                "Specialty": "Терапевт",
            }
        )
        self.app.current_table_name = "doctors"

    def test_parse_value(self) -> None:
        self.assertEqual(self.app._parse_value("  42  "), 42)
        self.assertEqual(self.app._parse_value(" -7 "), -7)
        self.assertEqual(self.app._parse_value(" text "), "text")
        self.assertEqual(self.app._parse_value("   "), "")

    def test_print_records_empty(self) -> None:
        with patch("builtins.print") as mocked_print:
            self.app._print_records([])
        mocked_print.assert_any_call("Записи не найдены.")

    def test_print_tables_empty(self) -> None:
        empty_app = ConsoleApp()
        empty_app.db = InMemoryDatabase()
        empty_app.current_table_name = ""

        with patch("builtins.print") as mocked_print:
            empty_app._print_tables()
        mocked_print.assert_any_call("Таблиц пока нет.")

    def test_print_tables_non_empty(self) -> None:
        with patch("builtins.print") as mocked_print:
            self.app._print_tables()
        mocked_print.assert_any_call("Список таблиц:")

    def test_choose_table_sets_current_table(self) -> None:
        with patch.object(ConsoleApp, "_read_value", side_effect=["doctors"]), patch(
            "builtins.print"
        ):
            self.app._choose_table()
        self.assertEqual(self.app.current_table_name, "doctors")

    def test_create_table_sets_current_table(self) -> None:
        app = ConsoleApp()
        with patch.object(
            ConsoleApp,
            "_read_value",
            side_effect=["labs", "LabID", "LabID, Title, City"],
        ), patch("builtins.print"):
            app._create_table()
        self.assertEqual(app.current_table_name, "labs")
        self.assertIn("labs", app.db.list_tables())

    def test_get_current_table_requires_selection(self) -> None:
        self.app.current_table_name = ""
        with self.assertRaises(ConsoleValidationErrors):
            self.app._get_current_table()

    def test_read_record_for_table(self) -> None:
        with patch.object(
            ConsoleApp,
            "_read_value",
            side_effect=["2", "Петров П.П.", "Хирург"],
        ), patch("builtins.print"):
            record = self.app._read_record_for_table(self.doctors)

        self.assertEqual(record["DoctorID"], 2)
        self.assertEqual(record["FullName"], "Петров П.П.")
        self.assertEqual(record["Specialty"], "Хирург")

    def test_read_filters_for_table(self) -> None:
        with patch.object(
            ConsoleApp,
            "_read_value",
            side_effect=["1", "", "Терапевт"],
        ), patch("builtins.print"):
            filters = self.app._read_filters_for_table(self.doctors)

        self.assertEqual(filters, {"DoctorID": 1, "Specialty": "Терапевт"})

    def test_read_updates_for_table(self) -> None:
        with patch.object(ConsoleApp, "_read_value", side_effect=["1"]), patch(
            "builtins.input",
            side_effect=["Петров П.П.", "Хирург"],
        ), patch("builtins.print"):
            key_value, updates = self.app._read_updates_for_table(self.doctors)

        self.assertEqual(key_value, 1)
        self.assertEqual(updates, {"FullName": "Петров П.П.", "Specialty": "Хирург"})

    def test_read_key_for_delete(self) -> None:
        with patch.object(ConsoleApp, "_read_value", side_effect=["1"]), patch(
            "builtins.print"
        ):
            key_value = self.app._read_key_for_delete(self.doctors)
        self.assertEqual(key_value, 1)

    def test_run_unknown_command(self) -> None:
        with patch.object(ConsoleApp, "_read_value", side_effect=["x", "0"]), patch(
            "builtins.print"
        ) as mocked_print:
            self.app.run()

        mocked_print.assert_any_call("Неизвестная команда.")

    def test_run_exit(self) -> None:
        with patch.object(ConsoleApp, "_read_value", side_effect=["0"]), patch(
            "builtins.print"
        ):
            self.app.run()

    def test_run_database_error_branch(self) -> None:
        self.app.current_table_name = ""
        with patch.object(ConsoleApp, "_read_value", side_effect=["4", "0"]), patch(
            "builtins.print"
        ) as mocked_print:
            self.app.run()

        self.assertTrue(
            any(
                "Ошибка:" in str(call.args[0])
                for call in mocked_print.call_args_list
                if call.args
            )
        )
    def test_run_full_flow(self) -> None:
        read_values = [
            "1",
            "2",
            "labs",
            "LabID",
            "LabID, Title, City",
            "3",
            "doctors",
            "4",
            "2",
            "Петров П.П.",
            "Хирург",
            "5",
            "6",
            "1",
            "",
            "Терапевт",
            "7",
            "1",
            "Иванов Илья Ильич",
            "Хирург",
            "8",
            "2",
            "9",
            "doctors",
            "0",
        ]

        with patch.object(ConsoleApp, "_read_value", side_effect=read_values), patch(
            "builtins.input",
            side_effect=["Иванов Илья Ильич", "Хирург"],
        ), patch("builtins.print"):
            self.app.run()

        self.assertIn("patients", self.app.db.list_tables())
        self.assertNotIn("doctors", self.app.db.list_tables())

    def test_main_module_executes(self) -> None:
        with patch("src.db.tui.ConsoleApp.run", return_value=None), patch(
            "src.db.tui.main",
            return_value=None,
            create=True,
        ):
            runpy.run_module("src.db.__main__", run_name="__main__")

if __name__ == "__main__":
    unittest.main()