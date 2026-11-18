"""Pruebas de rendimiento y escenarios de Navegando Mareas.

Uso:
    python benchmark.py            # ejecuta todo y guarda results/*.json|csv
    python benchmark.py --plots    # además genera gráficos (requiere matplotlib)

Experimentos:
  E1. Escalabilidad: 4 algoritmos x 3 tamaños de cuadrícula x 2 criterios.
  E2. Rutas de referencia en Puerto Marea (pruebas funcionales).
  E3. Re-ruteo ante eventos (Command + Observer).
  E4. Efecto de la caché (Proxy) con consultas repetidas.
  E5. Latencia extremo a extremo de la API REST.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import time
from pathlib import Path

from app import create_app
from navigation import NavigationService, StrategyRegistry
from navigation.city import build_port_city, generate_grid_city, largest_component
from navigation.costs import get_criterion
from navigation.iterator import Route

OUT = Path(__file__).parent / "results"
ORDER = ["dijkstra", "astar", "bfs", "greedy"]
SEED = 2026


def pct(values, p):
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return values[k]


def e1_scalability(sizes=(25, 50, 100), pairs=30, repeats=3):
    rows = []
    for size in sizes:
        city = generate_grid_city(size, seed=SEED)
        nodes = largest_component(city)
        rng = random.Random(SEED + size)
        queries = [rng.sample(nodes, 2) for _ in range(pairs)]
        for crit_name in ("distance", "time"):
            crit = get_criterion(crit_name)
            acc = {a: {"ms": [], "exp": [], "over": [], "opt": 0} for a in ORDER}
            for o, d in queries:
                res = {}
                for a in ORDER:
                    strat = StrategyRegistry.create(a)
                    times = []
                    for _ in range(repeats):          # mejor de N para reducir ruido
                        r = strat.find_route(city, o, d, crit)
                        times.append(r.elapsed_ms)
                    r.elapsed_ms = min(times)
                    res[a] = r
                best = res["dijkstra"].cost
                for a, r in res.items():
                    over = (r.cost / best - 1) * 100
                    acc[a]["ms"].append(r.elapsed_ms)
                    acc[a]["exp"].append(r.expanded)
                    acc[a]["over"].append(over)
                    acc[a]["opt"] += over < 1e-6
            for a in ORDER:
                v = acc[a]
                rows.append({
                    "size": f"{size}x{size}", "nodes": len(city.nodes),
                    "edges": len(city.edges), "criterion": crit_name,
                    "algorithm": a, "avg_ms": round(statistics.mean(v["ms"]), 3),
                    "p95_ms": round(pct(v["ms"], 95), 3),
                    "avg_expanded": round(statistics.mean(v["exp"]), 1),
                    "avg_overhead_pct": round(statistics.mean(v["over"]), 2),
                    "max_overhead_pct": round(max(v["over"]), 2),
                    "optimal_pct": round(100 * v["opt"] / pairs, 1),
                })
            print(f"  E1 {size}x{size} {crit_name} listo")
    return rows


def e2_reference_routes():
    city = build_port_city()
    cases = [("A0", "J6", "time", "Terminal de Buses → Puerto Marítimo"),
             ("G1", "I4", "distance", "Universidad → Hospital"),
             ("A6", "G1", "distance", "Faro → Universidad"),
             ("C3", "H5", "time", "Plaza Central → Intersección H5")]
    rows = []
    for o, d, c, label in cases:
        crit = get_criterion(c)
        res = {a: StrategyRegistry.create(a).find_route(city, o, d, crit) for a in ORDER}
        best = res["dijkstra"].cost
        for a, r in res.items():
            rows.append({"case": label, "origin": o, "destination": d,
                         "criterion": c, "algorithm": a,
                         "cost": round(r.cost, 1), "distance_m": round(r.distance_m),
                         "time_s": round(r.time_s, 1), "hops": r.hops,
                         "expanded": r.expanded, "elapsed_ms": round(r.elapsed_ms, 4),
                         "overhead_pct": round((r.cost / best - 1) * 100, 1),
                         "path": "-".join(r.path)})
    return rows


def e3_rerouting():
    svc = NavigationService()
    base = svc.route("A0", "J6", "astar", "time")
    steps = [("Ruta inicial (A*, menor tiempo)", None, base)]
    a, b = base["path"][5], base["path"][6]
    out = svc.apply_command("close", a, b)
    steps.append((f"Cierre de {svc.city.get_edge(a, b).name} ({a}–{b})", out["action"], out["rerouted"]))
    r2 = out["rerouted"]
    c, d = r2["path"][8], r2["path"][9]
    out = svc.apply_command("traffic", c, d, 4)
    steps.append((f"Trancón x4 en {svc.city.get_edge(c, d).name} ({c}–{d})", out["action"], out["rerouted"]))
    out = svc.undo()
    steps.append(("Deshacer último comando", out["action"], out["rerouted"]))
    rows = []
    for label, action, r in steps:
        via = (" → ".join(s.street for s in Route(svc.city, r["path"]) if s.street)
               if r else "")
        rows.append({"scenario": label, "found": r["found"] if r else None,
                     "cost_s": r["cost"] if r else None,
                     "distance_m": r["distance_m"] if r else None,
                     "expanded": r["expanded"] if r else None,
                     "path": "-".join(r["path"]) if r else "(sin cambio en la ruta)",
                     "via": via})
    rows.append({"scenario": "Re-ruteos automáticos", "found": None,
                 "cost_s": None, "distance_m": None,
                 "expanded": svc.stats["reroutes"], "path": "", "via": ""})
    return rows


def e4_cache(size=60, unique_pairs=25, queries=500):
    results = {}
    for use_cache in (False, True):
        svc = NavigationService(generate_grid_city(size, seed=SEED))
        nodes = largest_component(svc.city)
        rng = random.Random(SEED)
        popular = [rng.sample(nodes, 2) for _ in range(unique_pairs)]
        weights = [1 / (i + 1) for i in range(unique_pairs)]   # distribución tipo Zipf
        sample_rng = random.Random(SEED + 1)   # misma secuencia en ambos modos
        times = []
        for _ in range(queries):
            o, d = sample_rng.choices(popular, weights)[0]
            t0 = time.perf_counter()
            svc.route(o, d, "astar", "time", use_cache=use_cache, follow=False)
            times.append((time.perf_counter() - t0) * 1000)
        stats = svc.cache.stats()
        results["con_cache" if use_cache else "sin_cache"] = {
            "queries": queries, "avg_ms": round(statistics.mean(times), 4),
            "p95_ms": round(pct(times, 95), 4), "total_ms": round(sum(times), 1),
            "hit_rate": stats["hit_rate"] if use_cache else 0.0,
        }
    s, c = results["sin_cache"], results["con_cache"]
    results["speedup"] = round(s["total_ms"] / c["total_ms"], 1)
    results["grid"] = f"{size}x{size}"
    return results


def e5_api_latency(n=200):
    client = create_app(NavigationService()).test_client()
    rng = random.Random(SEED)
    ids = sorted(build_port_city().nodes)
    out = {}
    for name, use_cache in (("route_sin_cache", False), ("route_con_cache", True)):
        times = []
        for _ in range(n):
            o, d = rng.sample(ids[:20], 2) if use_cache else rng.sample(ids, 2)
            t0 = time.perf_counter()
            resp = client.post("/api/route", json={"origin": o, "destination": d,
                                                   "algorithm": "astar", "criterion": "time",
                                                   "use_cache": use_cache})
            times.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200
        out[name] = {"requests": n, "avg_ms": round(statistics.mean(times), 3),
                     "p95_ms": round(pct(times, 95), 3)}
    times = []
    for _ in range(50):
        o, d = rng.sample(ids, 2)
        t0 = time.perf_counter()
        client.post("/api/compare", json={"origin": o, "destination": d})
        times.append((time.perf_counter() - t0) * 1000)
    out["compare"] = {"requests": 50, "avg_ms": round(statistics.mean(times), 3),
                      "p95_ms": round(pct(times, 95), 3)}
    return out


def write_csv(path: Path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plots", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    print("Ejecutando experimentos…")
    data = {"seed": SEED,
            "e1_scalability": e1_scalability(),
            "e2_reference_routes": e2_reference_routes(),
            "e3_rerouting": e3_rerouting(),
            "e4_cache": e4_cache(),
            "e5_api_latency": e5_api_latency()}
    (OUT / "benchmark.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(OUT / "e1_escalabilidad.csv", data["e1_scalability"])
    write_csv(OUT / "e2_rutas_referencia.csv", data["e2_reference_routes"])
    write_csv(OUT / "e3_reruteo.csv", data["e3_rerouting"])
    print(json.dumps({k: data[k] for k in ("e4_cache", "e5_api_latency")}, indent=2))
    if args.plots:
        from plots import make_plots
        make_plots(data, OUT / "charts")
    print(f"Resultados guardados en {OUT}")


if __name__ == "__main__":
    main()
