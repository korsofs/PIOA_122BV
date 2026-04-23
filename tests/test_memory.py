import unittest

from src.db.backend.errors import (
    DuplicateRecordError,
    DuplicateTableError,
    RecordNotFoundError,
    TableNotFoundError,
    ValidationError,
)
from src.db.backend.memory import MemoryDatabase, Table, build_default_database


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
        self.assertIsInstance(table, Table)

    def test_create_table(self) -> None:
        table = self.db.create_table(
            name="doctors",
            key_field="DoctorID",
            fields=["DoctorID", "FullName", "Specialty"],
        )
        self.assertEqual(table.name, "doctors")
        self.assertIn("doctors", self.db.list_tables())

    def test_create_duplicate_table_raises(self) -> None:
        with self.assertRaises(DuplicateTableError):
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
        with self.assertRaises(DuplicateRecordError):
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

    def test_sort_records_ascending(self) -> None:
        self.patients.create_record(self.patient_3)
        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)

        result = self.patients.sort_records("PatientID", descending=False)
        ids = [record["PatientID"] for record in result]
        self.assertEqual(ids, [101, 102, 103])

    def test_sort_records_descending(self) -> None:
        self.patients.create_record(self.patient_3)
        self.patients.create_record(self.patient_1)
        self.patients.create_record(self.patient_2)

        result = self.patients.sort_records("PatientID", descending=True)
        ids = [record["PatientID"] for record in result]
        self.assertEqual(ids, [103, 102, 101])

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


if __name__ == "__main__":
    unittest.main()