import abc
from typing import Any

class BaseAgent(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass

    async def execute(self, *args, **kwargs) -> Any:
        """
        Einheitliche Schnittstelle für die Ausführung der Hauptaufgabe des Agenten.
        Jeder Agent sollte perspektivisch diese Methode implementieren, um via
        Polymorphie vom Orchestrator angesteuert werden zu können.
        """
        raise NotImplementedError(f"{self.name} hat keine einheitliche execute() Methode implementiert.")
