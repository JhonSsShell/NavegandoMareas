"""Patrón Observer: eventos del mapa y suscriptores.

El mapa de la ciudad (Subject) publica un ``MapEvent`` cada vez que cambia el
estado de una calle (cierre, reapertura o nivel de tráfico). Los observadores
reaccionan sin que el mapa conozca sus clases concretas: la caché de rutas se
invalida, la bitácora registra el evento y el vigilante de ruta activa decide
si hay que recalcular.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class MapEvent:
    kind: str            # "closed" | "opened" | "traffic" | "reset"
    edge_key: tuple      # (u, v) ordenado; () para eventos globales
    detail: str
    version: int
    improvement: bool = False   # True si el cambio puede abrir una ruta mejor
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "edge": list(self.edge_key),
            "detail": self.detail,
            "version": self.version,
            "improvement": self.improvement,
            "timestamp": round(self.timestamp, 3),
        }


class MapObserver(ABC):
    """Interfaz que implementan todos los suscriptores del mapa."""

    @abstractmethod
    def on_map_event(self, event: MapEvent) -> None: ...


class Subject:
    """Mantiene la lista de observadores y los notifica."""

    def __init__(self) -> None:
        self._observers: List[MapObserver] = []

    def attach(self, observer: MapObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer: MapObserver) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def notify(self, event: MapEvent) -> None:
        for observer in list(self._observers):
            observer.on_map_event(event)


class EventLog(MapObserver):
    """Observador que guarda una bitácora acotada de eventos para la UI."""

    def __init__(self, limit: int = 50) -> None:
        self.limit = limit
        self.events: List[MapEvent] = []

    def on_map_event(self, event: MapEvent) -> None:
        self.events.append(event)
        if len(self.events) > self.limit:
            self.events.pop(0)

    def to_list(self) -> list:
        return [e.to_dict() for e in reversed(self.events)]
