"""Criterios de costo (Strategy secundaria): ¿qué significa "ruta óptima"?

Separar el criterio del algoritmo permite combinar libremente
{BFS, Dijkstra, A*, Greedy} x {distancia, tiempo} sin duplicar código.
Cada criterio aporta además una heurística *admisible* (nunca sobreestima),
condición necesaria para que A* garantice la ruta óptima.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .domain import CityMap, Edge, NavigationError


class CostCriterion(ABC):
    name: str = ""
    label: str = ""
    unit: str = ""

    @abstractmethod
    def edge_cost(self, edge: Edge) -> float: ...

    @abstractmethod
    def heuristic(self, city: CityMap, a: str, b: str) -> float: ...

    def format(self, value: float) -> str:
        return f"{value:.1f} {self.unit}"


class DistanceCriterion(CostCriterion):
    name, label, unit = "distance", "Menor distancia", "m"

    def edge_cost(self, edge: Edge) -> float:
        return edge.length

    def heuristic(self, city: CityMap, a: str, b: str) -> float:
        # La línea recta es la distancia mínima posible.
        return city.euclidean(a, b)


class TimeCriterion(CostCriterion):
    name, label, unit = "time", "Menor tiempo", "s"

    def edge_cost(self, edge: Edge) -> float:
        return edge.travel_time_s

    def heuristic(self, city: CityMap, a: str, b: str) -> float:
        # Línea recta a la velocidad máxima de la red y sin tráfico.
        return city.euclidean(a, b) / city.max_speed_ms


CRITERIA = {c.name: c for c in (DistanceCriterion(), TimeCriterion())}


def get_criterion(name: str) -> CostCriterion:
    try:
        return CRITERIA[name]
    except KeyError:
        raise NavigationError(f"Criterio desconocido: {name}") from None
