"""Construcción de mapas.

* ``build_port_city``: "Puerto Marea", ciudad ficticia de 68 intersecciones
  con un río que solo se cruza por tres puentes, un parque que obliga a
  rodear, un centro congestionado y avenidas rápidas. Está diseñada para que
  las diferencias entre algoritmos y criterios sean visibles en la demo.
* ``generate_grid_city``: cuadrículas aleatorias (reproducibles por semilla)
  de cualquier tamaño, usadas en las pruebas de rendimiento y escalabilidad.
"""
from __future__ import annotations

import random
from typing import Dict, Tuple

from .domain import CityMap, Node

COLS, ROWS = 10, 7
DX, DY = 250.0, 220.0          # metros entre intersecciones
RIVER_BETWEEN = (4, 5)          # el río pasa entre la carrera 5 y la 6
BRIDGES = {1: ("Puente Norte", 1.0), 3: ("Puente Central", 2.5),
           5: ("Puente Sur", 1.0)}
PARK_NODES = {(7, 2), (7, 3)}   # Parque Marea: no hay intersecciones
POIS: Dict[Tuple[int, int], str] = {
    (0, 0): "Terminal de Buses", (9, 0): "Aeropuerto", (6, 1): "Universidad",
    (2, 3): "Plaza Central", (5, 3): "Estadio", (8, 4): "Hospital",
    (0, 6): "Faro", (3, 6): "Mercado del Mar", (9, 6): "Puerto Marítimo",
}


def node_id(c: int, r: int) -> str:
    return f"{chr(ord('A') + c)}{r}"


def build_port_city() -> CityMap:
    city = CityMap("Puerto Marea")
    for c in range(COLS):
        for r in range(ROWS):
            if (c, r) in PARK_NODES:
                continue
            city.add_node(Node(node_id(c, r), c * DX, r * DY, POIS.get((c, r), "")))

    def exists(c, r):
        return node_id(c, r) in city.nodes

    # Calles (oriente-occidente)
    for r in range(ROWS):
        if r == 0:
            name, speed, kind = "Avenida Norte", 50, "avenue"
        elif r == ROWS - 1:
            name, speed, kind = "Avenida Costanera", 60, "avenue"
        else:
            name, speed, kind = f"Calle {r * 10}", 30, "street"
        for c in range(COLS - 1):
            if not (exists(c, r) and exists(c + 1, r)):
                continue
            if (c, c + 1) == RIVER_BETWEEN:
                if r not in BRIDGES:
                    continue
                bname, traffic = BRIDGES[r]
                city.add_edge(node_id(c, r), node_id(c + 1, r), bname, 40,
                              length=DX * 1.1, traffic=traffic, kind="bridge")
                continue
            traffic = 1.8 if (1 <= c <= 3 and 2 <= r <= 4) else 1.0  # centro
            city.add_edge(node_id(c, r), node_id(c + 1, r), name, speed,
                          traffic=traffic, kind=kind)

    # Carreras (norte-sur)
    for c in range(COLS):
        if c == COLS - 1:
            name, speed, kind = "Avenida Oriental", 50, "avenue"
        elif c == RIVER_BETWEEN[1]:
            name, speed, kind = "Avenida del Río", 50, "avenue"
        else:
            name, speed, kind = f"Carrera {c + 1}", 40, "street"
        for r in range(ROWS - 1):
            if not (exists(c, r) and exists(c, r + 1)):
                continue
            traffic = 1.8 if (1 <= c <= 3 and 2 <= r <= 3) else 1.0
            city.add_edge(node_id(c, r), node_id(c, r + 1), name, speed,
                          traffic=traffic, kind=kind)

    # Diagonal 45: atajo del Faro hacia la Plaza
    diag = [(0, 6), (1, 5), (2, 4), (3, 3)]
    for (c1, r1), (c2, r2) in zip(diag, diag[1:]):
        city.add_edge(node_id(c1, r1), node_id(c2, r2), "Diagonal 45", 50,
                      kind="diagonal")

    # Elementos visuales (no afectan el grafo)
    rx = (RIVER_BETWEEN[0] + 0.5) * DX
    city.features = [
        {"type": "sea", "label": "Mar de las Mareas",
         "rect": [-500, (ROWS - 1) * DY + 70, COLS * DX + 750, 300]},
        {"type": "river", "label": "Río Marea",
         "points": [[rx - 20, -150], [rx + 25, 300], [rx - 25, 700],
                    [rx + 20, 1100], [rx, (ROWS - 1) * DY + 90]], "width": 70},
        {"type": "park", "label": "Parque Marea",
         "rect": [6 * DX + 25, 1 * DY + 25, 2 * DX - 50, 3 * DY - 50]},
        {"type": "zone", "label": "Centro (congestión)",
         "rect": [1 * DX - 30, 2 * DY - 30, 2 * DX + 60, 2 * DY + 60]},
    ]
    return city


def generate_grid_city(size: int, seed: int = 42, obstacle_ratio: float = 0.10,
                       spacing: float = 100.0) -> CityMap:
    """Cuadrícula ``size x size`` con obstáculos, avenidas y tráfico aleatorio.

    Las longitudes son >= distancia euclidiana (factor 1.0-1.35), de modo que
    las heurísticas de ``costs.py`` siguen siendo admisibles.
    """
    rng = random.Random(seed)
    city = CityMap(f"Cuadrícula {size}x{size}")
    for c in range(size):
        for r in range(size):
            if rng.random() < obstacle_ratio and (c, r) not in {(0, 0)}:
                continue
            city.add_node(Node(f"{c}_{r}", c * spacing, r * spacing))
    for c in range(size):
        for r in range(size):
            a = f"{c}_{r}"
            if a not in city.nodes:
                continue
            for dc, dr in ((1, 0), (0, 1)):
                b = f"{c + dc}_{r + dr}"
                if b not in city.nodes:
                    continue
                avenue = (r % 5 == 0) if dc else (c % 5 == 0)
                speed = 60 if avenue else rng.choice((30, 40))
                traffic = rng.uniform(1.5, 3.0) if rng.random() < 0.2 else 1.0
                city.add_edge(a, b, "Av" if avenue else "Calle", speed,
                              length=spacing * rng.uniform(1.0, 1.35),
                              traffic=round(traffic, 2),
                              kind="avenue" if avenue else "street")
    return city


def largest_component(city: CityMap) -> list:
    """Nodos de la componente conexa más grande (para elegir pares válidos)."""
    seen, best = set(), []
    for start in city.nodes:
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            n = stack.pop()
            comp.append(n)
            for nbr, _ in city.neighbors(n):
                if nbr not in seen:
                    seen.add(nbr)
                    stack.append(nbr)
        if len(comp) > len(best):
            best = comp
    return best
