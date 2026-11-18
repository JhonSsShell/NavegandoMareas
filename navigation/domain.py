"""Modelo de dominio: intersecciones, calles y el mapa de la ciudad."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

from .observer import MapEvent, Subject


class NavigationError(ValueError):
    """Error de negocio (nodo inexistente, calle inexistente, etc.)."""


def edge_key(u: str, v: str) -> Tuple[str, str]:
    """Las calles son de doble sentido: la clave no depende del orden."""
    return (u, v) if u <= v else (v, u)


@dataclass(frozen=True)
class Node:
    id: str
    x: float          # metros (eje x hacia el oriente)
    y: float          # metros (eje y hacia el sur, como en pantalla)
    label: str = ""   # nombre del punto de interés, si lo hay

    def to_dict(self) -> dict:
        return {"id": self.id, "x": self.x, "y": self.y, "label": self.label}


@dataclass
class Edge:
    u: str
    v: str
    name: str
    length: float        # metros
    speed_kmh: float     # velocidad permitida
    traffic: float = 1.0  # 1.0 = flujo libre; 2.0 = tarda el doble
    closed: bool = False
    kind: str = "street"  # street | avenue | bridge | diagonal

    @property
    def key(self) -> Tuple[str, str]:
        return edge_key(self.u, self.v)

    @property
    def travel_time_s(self) -> float:
        return self.length / (self.speed_kmh / 3.6) * self.traffic

    def other(self, node_id: str) -> str:
        return self.v if node_id == self.u else self.u

    def to_dict(self) -> dict:
        return {
            "u": self.u, "v": self.v, "name": self.name, "kind": self.kind,
            "length": round(self.length, 1), "speed": self.speed_kmh,
            "traffic": self.traffic, "closed": self.closed,
            "time_s": round(self.travel_time_s, 1),
        }


class CityMap(Subject):
    """Grafo no dirigido y ponderado que representa la red vial.

    Es el *Subject* del patrón Observer: cada modificación incrementa la
    versión del mapa y notifica a los suscriptores.
    """

    def __init__(self, name: str = "Ciudad") -> None:
        super().__init__()
        self.name = name
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[Tuple[str, str], Edge] = {}
        self._adj: Dict[str, List[Edge]] = {}
        self.features: List[dict] = []   # río, parque, mar (solo visual)
        self.version = 0
        self._max_speed_kmh = 0.0

    # ---------- construcción ----------
    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        self._adj.setdefault(node.id, [])

    def add_edge(self, u: str, v: str, name: str, speed_kmh: float,
                 length: Optional[float] = None, traffic: float = 1.0,
                 kind: str = "street") -> Edge:
        if u not in self.nodes or v not in self.nodes:
            raise NavigationError(f"Nodo inexistente en la calle {u}-{v}")
        if length is None:
            length = self.euclidean(u, v)
        edge = Edge(u, v, name, length, speed_kmh, traffic, False, kind)
        self.edges[edge.key] = edge
        self._max_speed_kmh = max(self._max_speed_kmh, speed_kmh)
        self._adj[u].append(edge)
        self._adj[v].append(edge)
        return edge

    # ---------- consultas ----------
    def neighbors(self, node_id: str) -> Iterator[Tuple[str, Edge]]:
        """Vecinos alcanzables (omite calles cerradas)."""
        for edge in self._adj.get(node_id, ()):
            if not edge.closed:
                yield edge.other(node_id), edge

    def get_edge(self, u: str, v: str) -> Edge:
        try:
            return self.edges[edge_key(u, v)]
        except KeyError:
            raise NavigationError(f"No existe la calle {u} - {v}") from None

    def require_node(self, node_id: str) -> Node:
        if node_id not in self.nodes:
            raise NavigationError(f"La intersección '{node_id}' no existe")
        return self.nodes[node_id]

    def euclidean(self, a: str, b: str) -> float:
        na, nb = self.nodes[a], self.nodes[b]
        return math.hypot(na.x - nb.x, na.y - nb.y)

    @property
    def max_speed_ms(self) -> float:
        """Velocidad máxima de la red en m/s (cota para la heurística)."""
        return self._max_speed_kmh / 3.6

    # ---------- mutaciones (notifican a los observadores) ----------
    def _changed(self, kind: str, key: tuple, detail: str,
                 improvement: bool = False) -> None:
        self.version += 1
        self.notify(MapEvent(kind, key, detail, self.version, improvement))

    def set_closed(self, u: str, v: str, closed: bool) -> None:
        edge = self.get_edge(u, v)
        if edge.closed == closed:
            return
        edge.closed = closed
        verb = "cerrada" if closed else "reabierta"
        self._changed("closed" if closed else "opened", edge.key,
                      f"{edge.name} ({edge.u}–{edge.v}) {verb}",
                      improvement=not closed)

    def set_traffic(self, u: str, v: str, factor: float) -> None:
        edge = self.get_edge(u, v)
        factor = round(max(1.0, min(float(factor), 5.0)), 2)
        if edge.traffic == factor:
            return
        improvement = factor < edge.traffic
        edge.traffic = factor
        self._changed("traffic", edge.key,
                      f"Tráfico x{factor} en {edge.name} ({edge.u}–{edge.v})",
                      improvement=improvement)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
            "features": self.features,
        }
