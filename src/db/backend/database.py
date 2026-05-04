from abc import ABC, abstractmethod
from typing import Any

from .table import Table


class Database(ABC):
    @abstractmethod
    def create_table(self, name: str, key_field: str, fields: list[str]) -> Table:
        """Создаёт таблицу и возвращает её."""

    @abstractmethod
    def get_table(self, name: str) -> Table:
        """Возвращает таблицу по имени."""

    @abstractmethod
    def list_tables(self) -> list[str]:
        """Возвращает список таблиц."""

    @abstractmethod
    def delete_table(self, name: str) -> None:
        """Удаляет таблицу."""