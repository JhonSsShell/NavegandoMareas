"""Patrón Facade: ``NavigationService`` es la única puerta de entrada a la
lógica de navegación para la capa web.

Coordina estrategias, caché, comandos, observadores e iterador, y protege el
estado compartido con un candado (Flask atiende peticiones en varios hilos).
"""
from __future__ import annotations

import random
import statistics
import threading
import time
from typing import Optional

from .cache import CachingRouteProxy, RouteCache
from .city import build_port_city, generate_grid_city, largest_component
from .commands import (CloseStreetCommand, CommandHistory, ReopenStreetCommand,
                       SetTrafficCommand)
from .costs import CRITERIA, get_criterion
from .domain import CityMap, NavigationError, edge_key
from .iterator import Route
from .observer import EventLog, MapEvent, MapObserver
from .strategies import StrategyRegistry


class ActiveRouteWatcher(MapObserver):
    """Observador que detecta si un evento afecta la ruta que se está
    siguiendo; en ese caso marca que hay que recalcular (re-ruteo)."""

    def __init__(self) -> None:
        self.active: Optional[dict] = None
        self.needs_reroute = False
        self.reason = ""

    def follow(self, request: dict, path: list) -> None:
        self.active = {**request, "edges": {edge_key(a, b) for a, b in zip(path, path[1:])}}
        self.needs_reroute = False

    def on_map_event(self, event: MapEvent) -> None:
        if not self.active:
            return
        if event.kind == "reset":
            self.active = None
            return
        if event.edge_key in self.active["edges"] or event.improvement:
            # Un cierre o más tráfico en la ruta la empeora; una reapertura o
            # menos tráfico en cualquier calle puede habilitar una ruta mejor.
            self.needs_reroute = True
            self.reason = event.detail


class NavigationService:
    def __init__(self, city: Optional[CityMap] = None) -> None:
        self._lock = threading.RLock()
        self._build(city or build_port_city())

    def _build(self, city: CityMap) -> None:
        self.city = city
        self.cache = RouteCache(capacity=256)
        self.events = EventLog()
        self.watcher = ActiveRouteWatcher()
        self.history = CommandHistory()
        for observer in (self.cache, self.events, self.watcher):
            self.city.attach(observer)
        self.stats = {"routes": 0, "compares": 0, "reroutes": 0}

    # ------------------------------------------------------------------ mapa
    def map_state(self) -> dict:
        with self._lock:
            data = self.city.to_dict()
            data["algorithms"] = StrategyRegistry.catalog()
            data["criteria"] = [{"name": c.name, "label": c.label, "unit": c.unit}
                                for c in CRITERIA.values()]
            data["history"] = self.history.to_dict()
            return data

    # ----------------------------------------------------------------- rutas
    def _route(self, origin, destination, algorithm, criterion, use_cache=True):
        crit = get_criterion(criterion)
        strategy = StrategyRegistry.create(algorithm)
        finder = CachingRouteProxy(strategy, self.cache) if use_cache else strategy
        t0 = time.perf_counter()
        result = finder.find_route(self.city, origin, destination, crit)
        response_ms = (time.perf_counter() - t0) * 1000
        hit = getattr(finder, "last_hit", False)
        return result, hit, response_ms

    def route(self, origin: str, destination: str, algorithm: str = "astar",
              criterion: str = "time", use_cache: bool = True,
              follow: bool = True) -> dict:
        with self._lock:
            result, hit, response_ms = self._route(origin, destination,
                                                   algorithm, criterion, use_cache)
            self.stats["routes"] += 1
            data = result.to_dict()
            data.update(cache_hit=hit, response_ms=round(response_ms, 4),
                        steps=[s.to_dict() for s in Route(self.city, result.path)]
                        if result.found else [])
            if follow and result.found:
                self.watcher.follow({"origin": origin, "destination": destination,
                                     "algorithm": algorithm, "criterion": criterion},
                                    result.path)
            return data

    def compare(self, origin: str, destination: str, criterion: str = "time") -> dict:
        with self._lock:
            self.stats["compares"] += 1
            rows = []
            for name in StrategyRegistry.names():
                result, _, _ = self._route(origin, destination, name, criterion,
                                           use_cache=False)
                rows.append(result.to_dict(include_explored=False))
            best = min((r["cost"] for r in rows if r["found"]), default=None)
            for r in rows:
                r["optimal"] = bool(r["found"] and best is not None
                                    and abs(r["cost"] - best) < 1e-6)
                r["overhead_pct"] = (round((r["cost"] / best - 1) * 100, 1)
                                     if r["found"] and best else None)
            return {"origin": origin, "destination": destination,
                    "criterion": criterion, "best_cost": best, "results": rows}

    # -------------------------------------------------------------- comandos
    def apply_command(self, kind: str, u: str, v: str, factor: float = 2.0) -> dict:
        with self._lock:
            if kind == "close":
                cmd = CloseStreetCommand(self.city, u, v)
            elif kind == "open":
                cmd = ReopenStreetCommand(self.city, u, v)
            elif kind == "traffic":
                cmd = SetTrafficCommand(self.city, u, v, factor)
            else:
                raise NavigationError(f"Comando desconocido: {kind}")
            self.history.execute(cmd)
            return self._after_change(cmd.description)

    def undo(self) -> dict:
        with self._lock:
            cmd = self.history.undo()
            return self._after_change(f"Deshacer: {cmd.description}" if cmd else None)

    def redo(self) -> dict:
        with self._lock:
            cmd = self.history.redo()
            return self._after_change(f"Rehacer: {cmd.description}" if cmd else None)

    def reset(self) -> dict:
        with self._lock:
            self._build(build_port_city())
            return self._after_change("Mapa restablecido")

    def _after_change(self, action: Optional[str]) -> dict:
        rerouted = None
        if self.watcher.active and self.watcher.needs_reroute:
            req = self.watcher.active
            rerouted = self.route(req["origin"], req["destination"],
                                  req["algorithm"], req["criterion"])
            rerouted["reason"] = self.watcher.reason
            self.stats["reroutes"] += 1
        return {"action": action, "map": self.map_state(),
                "events": self.events.to_list(), "rerouted": rerouted}

    # ------------------------------------------------------------- métricas
    def metrics(self) -> dict:
        with self._lock:
            return {"cache": self.cache.stats(), "usage": dict(self.stats),
                    "map_version": self.city.version,
                    "history": self.history.to_dict()}

    @staticmethod
    def benchmark(size: int = 40, pairs: int = 15, seed: int = 7) -> dict:
        """Prueba rápida de escalabilidad sobre una cuadrícula generada."""
        size = max(10, min(int(size), 80))
        pairs = max(3, min(int(pairs), 40))
        city = generate_grid_city(size, seed=seed)
        nodes = largest_component(city)
        rng = random.Random(seed)
        crit = get_criterion("time")
        acc = {n: {"ms": [], "expanded": [], "overhead": []}
               for n in StrategyRegistry.names()}
        for _ in range(pairs):
            o, d = rng.sample(nodes, 2)
            results = {n: StrategyRegistry.create(n).find_route(city, o, d, crit)
                       for n in StrategyRegistry.names()}
            best = results["dijkstra"].cost
            for n, r in results.items():
                acc[n]["ms"].append(r.elapsed_ms)
                acc[n]["expanded"].append(r.expanded)
                acc[n]["overhead"].append((r.cost / best - 1) * 100 if best else 0)
        rows = [{"algorithm": n,
                 "avg_ms": round(statistics.mean(v["ms"]), 3),
                 "avg_expanded": round(statistics.mean(v["expanded"]), 1),
                 "avg_overhead_pct": round(statistics.mean(v["overhead"]), 2),
                 "optimal_pct": round(100 * sum(x < 1e-6 for x in v["overhead"])
                                      / len(v["overhead"]), 1)}
                for n, v in acc.items()]
        return {"size": size, "nodes": len(city.nodes), "edges": len(city.edges),
                "pairs": pairs, "criterion": "time", "results": rows}
