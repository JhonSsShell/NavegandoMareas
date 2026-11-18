"""Patrón Command: acciones sobre el mapa que se pueden deshacer y rehacer.

Cada acción del operador (cerrar una calle, reportar tráfico) se encapsula en
un objeto con ``execute`` y ``undo``. ``CommandHistory`` actúa como *Invoker*
y mantiene las pilas de deshacer/rehacer, lo que permite simular escenarios
("¿qué pasa si cierro el puente?") y volver atrás sin recargar el mapa.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from .domain import CityMap


class MapCommand(ABC):
    def __init__(self, city: CityMap, u: str, v: str) -> None:
        self.city, self.u, self.v = city, u, v
        self.edge = city.get_edge(u, v)  # valida que exista

    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...

    @property
    @abstractmethod
    def description(self) -> str: ...


class CloseStreetCommand(MapCommand):
    def execute(self) -> None:
        self._was_closed = self.edge.closed
        self.city.set_closed(self.u, self.v, True)

    def undo(self) -> None:
        self.city.set_closed(self.u, self.v, self._was_closed)

    @property
    def description(self) -> str:
        return f"Cerrar {self.edge.name} ({self.u}–{self.v})"


class ReopenStreetCommand(MapCommand):
    def execute(self) -> None:
        self._was_closed = self.edge.closed
        self.city.set_closed(self.u, self.v, False)

    def undo(self) -> None:
        self.city.set_closed(self.u, self.v, self._was_closed)

    @property
    def description(self) -> str:
        return f"Reabrir {self.edge.name} ({self.u}–{self.v})"


class SetTrafficCommand(MapCommand):
    def __init__(self, city: CityMap, u: str, v: str, factor: float) -> None:
        super().__init__(city, u, v)
        self.factor = factor

    def execute(self) -> None:
        self._previous = self.edge.traffic
        self.city.set_traffic(self.u, self.v, self.factor)

    def undo(self) -> None:
        self.city.set_traffic(self.u, self.v, self._previous)

    @property
    def description(self) -> str:
        return f"Tráfico x{self.factor} en {self.edge.name} ({self.u}–{self.v})"


class CommandHistory:
    """Invoker con pilas de deshacer y rehacer."""

    def __init__(self) -> None:
        self._done: List[MapCommand] = []
        self._undone: List[MapCommand] = []

    def execute(self, command: MapCommand) -> MapCommand:
        command.execute()
        self._done.append(command)
        self._undone.clear()
        return command

    def undo(self):
        if not self._done:
            return None
        command = self._done.pop()
        command.undo()
        self._undone.append(command)
        return command

    def redo(self):
        if not self._undone:
            return None
        command = self._undone.pop()
        command.execute()
        self._done.append(command)
        return command

    def clear(self) -> None:
        self._done.clear()
        self._undone.clear()

    def to_dict(self) -> dict:
        return {
            "done": [c.description for c in self._done],
            "undone": [c.description for c in self._undone],
            "can_undo": bool(self._done), "can_redo": bool(self._undone),
        }
