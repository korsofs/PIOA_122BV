class DatabaseError(Exception):
    """Базовая ошибка базы данных."""


class ValidationError(DatabaseError):
    """Ошибка валидации данных."""


class DuplicateKeyError(DatabaseError):
    """Ключ или имя уже заняты."""


class TableNotFoundError(DatabaseError):
    """Таблица не найдена."""


class RecordNotFoundError(DatabaseError):
    """Запись не найдена."""


class DuplicateTableError(DuplicateKeyError):
    """Таблица с таким именем уже существует."""


class DuplicateRecordError(DuplicateKeyError):
    """Запись с таким ключом уже существует."""
