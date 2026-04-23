class DatabaseError(Exception):
    """Базовая ошибка базы данных."""


class ValidationError(DatabaseError):
    """Ошибка валидации данных."""


class DuplicateTableError(DatabaseError):
    """Таблица с таким именем уже существует."""


class TableNotFoundError(DatabaseError):
    """Таблица не найдена."""


class DuplicateRecordError(DatabaseError):
    """Запись с таким ключом уже существует."""


class RecordNotFoundError(DatabaseError):
    """Запись не найдена."""