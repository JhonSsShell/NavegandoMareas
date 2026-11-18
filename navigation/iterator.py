"""Patrón Iterator: recorrido de la ruta como indicaciones paso a paso.

``Route`` es una colección iterable; ``TurnByTurnIterator`` la recorre de
forma perezosa agrupando tramos consecutivos de la misma vía y calculando la
maniobra (seguir, girar a la izquierda/derecha) a partir del producto cruz
entre direcciones. La UI y las pruebas consumen la ruta sin conocer su
estructura interna.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, List, Optional, Tuple

from .domain import CityMap

CARDINALS = ["oriente", "suroriente", "sur", "suroccidente",
             "occidente", "noroccidente", "norte", "nororiente"]


@dataclass
class RouteStep:
    index: int
    maneuver: str        # start | straight | left | right | arrive
    street: str
    from_id: str
    to_id: str
    distance_m: float
    time_s: float
    instruction: str

    def to_dict(self) -> dict:
        return {k: (round(v, 1) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


class Route:
    def __init__(self, city: CityMap, path: List[str]) -> None:
        self.city, self.path = city, path

    def __iter__(self) -> "TurnByTurnIterator":
        return TurnByTurnIterator(self.city, self.path)

    def __len__(self) -> int:
        return max(len(self.path) - 1, 0)


class TurnByTurnIterator(Iterator[RouteStep]):
    def __init__(self, city: CityMap, path: List[str]) -> None:
        self.city, self.path = city, path
        self._i = 0                     # índice del tramo actual
        self._step = 0
        self._prev_heading: Optional[Tuple[float, float]] = None
        self._arrived = len(path) < 2

    def __iter__(self) -> "TurnByTurnIterator":
        return self

    def _heading(self, a: str, b: str) -> Tuple[float, float]:
        na, nb = self.city.nodes[a], self.city.nodes[b]
        dx, dy = nb.x - na.x, nb.y - na.y
        norm = math.hypot(dx, dy) or 1.0
        return dx / norm, dy / norm

    def _maneuver(self, new: Tuple[float, float]) -> str:
        if self._prev_heading is None:
            return "start"
        hx, hy = self._prev_heading
        cross = hx * new[1] - hy * new[0]      # y crece hacia el sur
        dot = hx * new[0] + hy * new[1]
        angle = math.degrees(math.atan2(cross, dot))
        if abs(angle) < 25:
            return "straight"
        return "right" if angle > 0 else "left"

    @staticmethod
    def _cardinal(h: Tuple[float, float]) -> str:
        angle = math.degrees(math.atan2(h[1], h[0])) % 360
        return CARDINALS[int((angle + 22.5) // 45) % 8]

    def __next__(self) -> RouteStep:
        n_edges = len(self.path) - 1
        if self._i >= n_edges:
            if self._arrived:
                raise StopIteration
            self._arrived = True
            self._step += 1
            last = self.path[-1]
            label = self.city.nodes[last].label or last
            return RouteStep(self._step, "arrive", "", last, last, 0.0, 0.0,
                             f"Llegue a su destino: {label}")

        a, b = self.path[self._i], self.path[self._i + 1]
        edge = self.city.get_edge(a, b)
        heading = self._heading(a, b)
        maneuver = self._maneuver(heading)
        start_node, street = a, edge.name
        dist, secs = edge.length, edge.travel_time_s
        self._i += 1
        last_heading = heading
        # Agrupa tramos consecutivos de la misma vía.
        while self._i < n_edges:
            c, d = self.path[self._i], self.path[self._i + 1]
            nxt = self.city.get_edge(c, d)
            if nxt.name != street:
                break
            dist += nxt.length
            secs += nxt.travel_time_s
            last_heading = self._heading(c, d)
            self._i += 1
        end_node = self.path[self._i]
        self._prev_heading = last_heading
        self._step += 1

        meters = f"{dist:,.0f} m".replace(",", ".")
        if maneuver == "start":
            origin = self.city.nodes[start_node].label or start_node
            text = (f"Salga de {origin} por {street} hacia el "
                    f"{self._cardinal(heading)} ({meters})")
        elif maneuver == "straight":
            text = f"Continúe recto por {street} ({meters})"
        else:
            side = "derecha" if maneuver == "right" else "izquierda"
            text = f"Gire a la {side} en {street} ({meters})"
        return RouteStep(self._step, maneuver, street, start_node, end_node,
                         dist, secs, text)
