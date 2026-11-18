"""Patrón Proxy (caché) + Observer (invalidación).

``CachingRouteProxy`` expone la misma interfaz que una ``RouteStrategy``
(``find_route``) y antepone una caché LRU compartida. El cliente no sabe si
habla con el algoritmo real o con el proxy.

``RouteCache`` es además un ``MapObserver``: cuando el mapa cambia (calle
cerrada, tráfico) la caché se vacía para no servir rutas obsoletas.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from typing import Tuple

from .costs import CostCriterion
from .domain import CityMap
from .observer import MapEvent, MapObserver
from .strategies import RouteStrategy, SearchResult


class RouteCache(MapObserver):
    def __init__(self, capacity: int = 256) -> None:
        self.capacity = capacity
        self._data: "OrderedDict[Tuple, SearchResult]" = OrderedDict()
        self.hits = self.misses = self.invalidations = 0

    def get(self, key):
        if key in self._data:
            self._data.move_to_end(key)
            self.hits += 1
            return self._data[key]
        self.misses += 1
        return None

    def put(self, key, value: SearchResult) -> None:
        self._data[key] = value
        self._data.move_to_end(key)
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def on_map_event(self, event: MapEvent) -> None:
        if self._data:
            self.invalidations += 1
        self.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "entries": len(self._data), "capacity": self.capacity,
            "hits": self.hits, "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
            "invalidations": self.invalidations,
        }


class CachingRouteProxy(RouteStrategy):
    """Proxy de caché que envuelve a una estrategia real."""

    def __init__(self, real: RouteStrategy, cache: RouteCache) -> None:
        self._real = real
        self._cache = cache
        self.name, self.label = real.name, real.label
        self.optimal, self.description = real.optimal, real.description
        self.last_hit = False

    def find_route(self, city: CityMap, origin: str, destination: str,
                   criterion: CostCriterion) -> SearchResult:
        key = (self._real.name, criterion.name, origin, destination)
        cached = self._cache.get(key)
        if cached is not None:
            self.last_hit = True
            return replace(cached)  # copia superficial: el cliente no altera la caché
        self.last_hit = False
        result = self._real.find_route(city, origin, destination, criterion)
        self._cache.put(key, result)
        return result

    def _search(self, *args, **kwargs):  # pragma: no cover - delegado
        raise NotImplementedError("El proxy delega en la estrategia real")
