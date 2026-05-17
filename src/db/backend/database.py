from abc import ABC, abstractmethod

from .table import Table


class Database(ABC):
    @abstractmethod
    def create_table(self, name: str, key_field: str, fields: list[str]) -> Table:
        raise NotImplementedError

    @abstractmethod
    def get_table(self, name: str) -> Table:
        raise NotImplementedError

    @abstractmethod
    def list_tables(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def delete_table(self, name: str) -> None:
        raise NotImplementedError
