import tempfile
import unittest
from pathlib import Path

from src.db.backend import errors as backend_errors
from src.db.backend.file import (
    DuplicateKeyError,
    FileDatabase,
    FileTable,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
    build_default_database,
)

FileValidationErrors = (ValidationError, backend_errors.ValidationError)


class TestFileDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = build_default_database(storage_dir=self.temp_dir.name)
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

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_database_has_patients_table(self) -> None:
        table = self.db.get_table("patients")
        self.assertIsInstance(table, FileTable)

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

    def test_data_persists_between_database_instances(self) -> None:
        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)

        new_db = FileDatabase(storage_dir=self.temp_dir.name)
        new_patients = new_db.get_table("patients")

        self.assertEqual(len(new_patients.select_records()), 2)
        self.assertEqual(new_patients.get_by_key(101)["FullName"], "Иванов Иван Иванович")
        self.assertEqual(new_patients.get_by_key(102)["FullName"], "Сидоров Сидор Сидорович")

    def test_file_is_created_on_disk(self) -> None:
        self.patients.create_record(self.patient_1)

        table_path = Path(self.temp_dir.name) / "patients.json"
        self.assertTrue(table_path.exists())

    def test_select_records_after_reload(self) -> None:
        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)

        reloaded_db = FileDatabase(storage_dir=self.temp_dir.name)
        reloaded_patients = reloaded_db.get_table("patients")

        result = reloaded_patients.select_records(filters={"Gender": "M"})
        self.assertEqual(len(result), 2)