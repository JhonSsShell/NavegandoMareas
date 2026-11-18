"""Patrón Strategy (+ Template Method + Registry/Factory).

Cada algoritmo de búsqueda es una estrategia intercambiable con la misma
interfaz ``find_route``. ``RouteStrategy.find_route`` es un *Template Method*:
fija los pasos comunes (validar, medir tiempo, reconstruir ruta, calcular
costo) y delega en ``_search`` la parte que cambia entre algoritmos.
El ``StrategyRegistry`` permite agregar algoritmos nuevos sin modificar el
resto del sistema (principio abierto/cerrado).
"""
from __future__ import annotations

import heapq
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Type

from .costs import CostCriterion
from .domain import CityMap, NavigationError


@dataclass
class SearchResult:
    algorithm: str
    criterion: str
    origin: str
    destination: str
    found: bool
    path: List[str] = field(default_factory=list)
    cost: float = float("inf")
    distance_m: float = 0.0
    time_s: float = 0.0
    expanded: int = 0           # nodos sacados de la frontera
    relaxed: int = 0            # aristas evaluadas
    explored_order: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    @property
    def hops(self) -> int:
        return max(len(self.path) - 1, 0)

    def to_dict(self, include_explored: bool = True) -> dict:
        data = {
            "algorithm": self.algorithm, "criterion": self.criterion,
            "origin": self.origin, "destination": self.destination,
            "found": self.found, "path": self.path, "hops": self.hops,
            "cost": round(self.cost, 2) if self.found else None,
            "distance_m": round(self.distance_m, 1),
            "time_s": round(self.time_s, 1),
            "expanded": self.expanded, "relaxed": self.relaxed,
            "elapsed_ms": round(self.elapsed_ms, 4),
        }
        if include_explored:
            data["explored_order"] = self.explored_order
        return data


SearchOutput = Tuple[Optional[Dict[str, Optional[str]]], List[str], int]


class RouteStrategy(ABC):
    name: str = ""
    label: str = ""
    optimal: bool = False
    description: str = ""

    # ----- Template Method -----
    def find_route(self, city: CityMap, origin: str, destination: str,
                   criterion: CostCriterion) -> SearchResult:
        city.require_node(origin)
        city.require_node(destination)
        start = time.perf_counter()
        prev, explored, relaxed = self._search(city, origin, destination, criterion)
        elapsed = (time.perf_counter() - start) * 1000
        result = SearchResult(self.name, criterion.name, origin, destination,
                              found=False, expanded=len(explored),
                              relaxed=relaxed, explored_order=explored,
                              elapsed_ms=elapsed)
        if prev is not None:
            result.found = True
            result.path = self._reconstruct(prev, destination)
            self._fill_costs(city, result, criterion)
        return result

    @abstractmethod
    def _search(self, city: CityMap, origin: str, destination: str,
                criterion: CostCriterion) -> SearchOutput:
        """Devuelve (predecesores | None si no hay ruta, orden de expansión,
        aristas evaluadas)."""

    # ----- pasos comunes -----
    @staticmethod
    def _reconstruct(prev: Dict[str, Optional[str]], destination: str) -> List[str]:
        path, node = [], destination
        while node is not None:
            path.append(node)
            node = prev[node]
        return path[::-1]

    @staticmethod
    def _fill_costs(city: CityMap, result: SearchResult,
                    criterion: CostCriterion) -> None:
        dist = secs = cost = 0.0
        for a, b in zip(result.path, result.path[1:]):
            edge = city.get_edge(a, b)
            dist += edge.length
            secs += edge.travel_time_s
            cost += criterion.edge_cost(edge)
        result.distance_m, result.time_s, result.cost = dist, secs, cost

    def info(self) -> dict:
        return {"name": self.name, "label": self.label,
                "optimal": self.optimal, "description": self.description}


class StrategyRegistry:
    """Fábrica de estrategias registradas por nombre."""

    _strategies: Dict[str, Type[RouteStrategy]] = {}

    @classmethod
    def register(cls, strategy_cls: Type[RouteStrategy]) -> Type[RouteStrategy]:
        cls._strategies[strategy_cls.name] = strategy_cls
        return strategy_cls

    @classmethod
    def create(cls, name: str) -> RouteStrategy:
        try:
            return cls._strategies[name]()
        except KeyError:
            raise NavigationError(f"Algoritmo desconocido: {name}") from None

    @classmethod
    def names(cls) -> List[str]:
        return list(cls._strategies)

    @classmethod
    def catalog(cls) -> List[dict]:
        return [s().info() for s in cls._strategies.values()]


# ---------------------------------------------------------------------------
# Estrategias concretas
# ---------------------------------------------------------------------------
@StrategyRegistry.register
class BreadthFirstStrategy(RouteStrategy):
    name, label, optimal = "bfs", "BFS (anchura)", False
    description = ("Minimiza el número de intersecciones; ignora distancias y "
                   "tráfico. Útil como línea base.")

    def _search(self, city, origin, destination, criterion):
        prev = {origin: None}
        queue, explored, relaxed = deque([origin]), [], 0
        while queue:
            node = queue.popleft()
            explored.append(node)
            if node == destination:
                return prev, explored, relaxed
            for nbr, _edge in city.neighbors(node):
                relaxed += 1
                if nbr not in prev:
                    prev[nbr] = node
                    queue.append(nbr)
        return None, explored, relaxed


@StrategyRegistry.register
class DijkstraStrategy(RouteStrategy):
    name, label, optimal = "dijkstra", "Dijkstra", True
    description = ("Óptimo para pesos no negativos. Expande en todas las "
                   "direcciones (búsqueda no informada).")

    def _search(self, city, origin, destination, criterion):
        dist = {origin: 0.0}
        prev = {origin: None}
        heap, counter = [(0.0, 0, origin)], 1
        done, explored, relaxed = set(), [], 0
        while heap:
            d, _, node = heapq.heappop(heap)
            if node in done:
                continue
            done.add(node)
            explored.append(node)
            if node == destination:
                return prev, explored, relaxed
            for nbr, edge in city.neighbors(node):
                relaxed += 1
                nd = d + criterion.edge_cost(edge)
                if nd < dist.get(nbr, float("inf")):
                    dist[nbr], prev[nbr] = nd, node
                    heapq.heappush(heap, (nd, counter, nbr))
                    counter += 1
        return None, explored, relaxed


@StrategyRegistry.register
class AStarStrategy(RouteStrategy):
    name, label, optimal = "astar", "A* (A estrella)", True
    description = ("Óptimo con heurística admisible. Prioriza los nodos que "
                   "se acercan al destino: explora mucho menos que Dijkstra.")

    def _search(self, city, origin, destination, criterion):
        h = lambda n: criterion.heuristic(city, n, destination)  # noqa: E731
        g = {origin: 0.0}
        prev = {origin: None}
        heap, counter = [(h(origin), 0, origin)], 1
        done, explored, relaxed = set(), [], 0
        while heap:
            _, _, node = heapq.heappop(heap)
            if node in done:
                continue
            done.add(node)
            explored.append(node)
            if node == destination:
                return prev, explored, relaxed
            for nbr, edge in city.neighbors(node):
                relaxed += 1
                ng = g[node] + criterion.edge_cost(edge)
                if ng < g.get(nbr, float("inf")):
                    g[nbr], prev[nbr] = ng, node
                    heapq.heappush(heap, (ng + h(nbr), counter, nbr))
                    counter += 1
        return None, explored, relaxed


@StrategyRegistry.register
class GreedyBestFirstStrategy(RouteStrategy):
    name, label, optimal = "greedy", "Greedy (voraz)", False
    description = ("Sigue solo la heurística: muy rápido y explora poco, pero "
                   "no garantiza la mejor ruta.")

    def _search(self, city, origin, destination, criterion):
        h = lambda n: criterion.heuristic(city, n, destination)  # noqa: E731
        prev = {origin: None}
        heap, counter = [(h(origin), 0, origin)], 1
        done, explored, relaxed = set(), [], 0
        while heap:
            _, _, node = heapq.heappop(heap)
            if node in done:
                continue
            done.add(node)
            explored.append(node)
            if node == destination:
                return prev, explored, relaxed
            for nbr, _edge in city.neighbors(node):
                relaxed += 1
                if nbr not in prev:
                    prev[nbr] = node
                    heapq.heappush(heap, (h(nbr), counter, nbr))
                    counter += 1
        return None, explored, relaxed
