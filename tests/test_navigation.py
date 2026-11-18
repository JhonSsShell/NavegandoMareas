"""Pruebas unitarias y de integración de Navegando Mareas (pytest)."""
import itertools
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from navigation import NavigationError, NavigationService, StrategyRegistry  # noqa: E402
from navigation.cache import CachingRouteProxy, RouteCache  # noqa: E402
from navigation.city import build_port_city, generate_grid_city, largest_component  # noqa: E402
from navigation.costs import get_criterion  # noqa: E402
from navigation.iterator import Route  # noqa: E402


@pytest.fixture
def city():
    return build_port_city()


@pytest.fixture
def service():
    return NavigationService()


# ---------------------------------------------------------------- Strategy
def test_registry_contains_four_strategies():
    assert set(StrategyRegistry.names()) == {"bfs", "dijkstra", "astar", "greedy"}
    with pytest.raises(NavigationError):
        StrategyRegistry.create("teletransporte")


@pytest.mark.parametrize("criterion", ["distance", "time"])
def test_astar_matches_dijkstra_optimal_cost(city, criterion):
    """A* con heurística admisible debe encontrar siempre el costo óptimo."""
    crit = get_criterion(criterion)
    dijkstra, astar = StrategyRegistry.create("dijkstra"), StrategyRegistry.create("astar")
    nodes = sorted(city.nodes)
    for o, d in itertools.islice(itertools.permutations(nodes, 2), 0, None, 37):
        r1 = dijkstra.find_route(city, o, d, crit)
        r2 = astar.find_route(city, o, d, crit)
        assert r1.found and r2.found
        assert r2.cost == pytest.approx(r1.cost)
        assert r2.expanded <= r1.expanded


def test_astar_explores_less_than_dijkstra_on_large_grid():
    grid = generate_grid_city(40, seed=3)
    nodes = largest_component(grid)
    rng = random.Random(1)
    crit = get_criterion("distance")
    dij, ast = StrategyRegistry.create("dijkstra"), StrategyRegistry.create("astar")
    ratios = []
    for _ in range(10):
        o, d = rng.sample(nodes, 2)
        ratios.append(ast.find_route(grid, o, d, crit).expanded /
                      max(dij.find_route(grid, o, d, crit).expanded, 1))
    assert sum(ratios) / len(ratios) < 0.6


def test_bfs_minimises_hops_and_greedy_can_be_suboptimal(city):
    crit = get_criterion("time")
    bfs = StrategyRegistry.create("bfs").find_route(city, "A0", "J6", crit)
    best = StrategyRegistry.create("dijkstra").find_route(city, "A0", "J6", crit)
    greedy = StrategyRegistry.create("greedy").find_route(city, "A0", "J6", crit)
    assert bfs.hops <= best.hops
    assert greedy.cost > best.cost      # demuestra que la heurística sola no basta
    assert bfs.cost > best.cost


def test_path_is_connected_and_starts_and_ends_correctly(city):
    r = StrategyRegistry.create("astar").find_route(city, "A6", "G1", get_criterion("distance"))
    assert r.path[0] == "A6" and r.path[-1] == "G1"
    for a, b in zip(r.path, r.path[1:]):
        city.get_edge(a, b)  # lanza excepción si no son adyacentes


def test_unreachable_destination(city):
    for nbr, _ in list(city.neighbors("J6")):
        city.set_closed("J6", nbr, True)
    r = StrategyRegistry.create("dijkstra").find_route(city, "A0", "J6", get_criterion("time"))
    assert not r.found and r.path == []


def test_unknown_node_raises(city):
    with pytest.raises(NavigationError):
        StrategyRegistry.create("astar").find_route(city, "A0", "Z9", get_criterion("time"))


# ------------------------------------------------------------ Proxy + Observer
def test_cache_hit_and_invalidation_on_map_event(city):
    cache = RouteCache()
    city.attach(cache)
    proxy = CachingRouteProxy(StrategyRegistry.create("astar"), cache)
    crit = get_criterion("time")
    proxy.find_route(city, "A0", "J6", crit)
    assert proxy.last_hit is False
    proxy.find_route(city, "A0", "J6", crit)
    assert proxy.last_hit is True
    city.set_traffic("E1", "F1", 3.0)          # evento -> invalida la caché
    assert cache.stats()["entries"] == 0
    proxy.find_route(city, "A0", "J6", crit)
    assert proxy.last_hit is False


# -------------------------------------------------------------------- Command
def test_close_street_command_undo_redo(service):
    service.apply_command("close", "E1", "F1")
    assert service.city.get_edge("E1", "F1").closed
    service.undo()
    assert not service.city.get_edge("E1", "F1").closed
    service.redo()
    assert service.city.get_edge("E1", "F1").closed
    assert service.history.to_dict()["can_undo"]


def test_traffic_command_restores_previous_value(service):
    before = service.city.get_edge("E3", "F3").traffic
    service.apply_command("traffic", "E3", "F3", 4)
    assert service.city.get_edge("E3", "F3").traffic == 4
    service.undo()
    assert service.city.get_edge("E3", "F3").traffic == before


def test_reroute_when_active_route_is_blocked(service):
    first = service.route("A0", "J6", "astar", "time")
    a, b = first["path"][5], first["path"][6]
    out = service.apply_command("close", a, b)
    assert out["rerouted"] is not None
    new_path = out["rerouted"]["path"]
    assert (a, b) not in set(zip(new_path, new_path[1:]))
    assert out["rerouted"]["cost"] >= first["cost"]


# ------------------------------------------------------------------- Iterator
def test_turn_by_turn_iterator(city):
    r = StrategyRegistry.create("astar").find_route(city, "A0", "J6", get_criterion("time"))
    steps = list(Route(city, r.path))
    assert steps[0].maneuver == "start"
    assert steps[-1].maneuver == "arrive"
    assert sum(s.distance_m for s in steps) == pytest.approx(r.distance_m)
    assert all(s.maneuver in {"start", "straight", "left", "right", "arrive"} for s in steps)


# ------------------------------------------------------------------- API REST
@pytest.fixture
def client():
    app = create_app(NavigationService())
    app.config["TESTING"] = True
    return app.test_client()


def test_api_health_and_map(client):
    assert client.get("/health").json["status"] == "ok"
    data = client.get("/api/map").json
    assert len(data["nodes"]) == 68 and len(data["algorithms"]) == 4


def test_api_route_compare_and_commands(client):
    r = client.post("/api/route", json={"origin": "A0", "destination": "J6",
                                        "algorithm": "astar", "criterion": "time"}).json
    assert r["found"] and r["steps"]
    c = client.post("/api/compare", json={"origin": "A0", "destination": "J6"}).json
    assert sum(x["optimal"] for x in c["results"]) >= 2
    cmd = client.post("/api/commands", json={"type": "close", "u": "E1", "v": "F1"}).json
    assert cmd["events"][0]["kind"] == "closed"
    assert client.post("/api/commands/undo", json={}).status_code == 200
    bad = client.post("/api/route", json={"origin": "A0", "destination": "ZZ"})
    assert bad.status_code == 400


def test_api_benchmark(client):
    b = client.get("/api/benchmark?size=20&pairs=5").json
    assert b["nodes"] > 300
    rows = {r["algorithm"]: r for r in b["results"]}
    assert rows["dijkstra"]["optimal_pct"] == 100.0
    assert rows["astar"]["optimal_pct"] == 100.0
