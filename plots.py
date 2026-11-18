"""Gráficos de resultados (solo desarrollo: requiere matplotlib)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"dijkstra": "#2a78d6", "astar": "#eb6834", "bfs": "#1baf7a", "greedy": "#eda100"}
LABELS = {"dijkstra": "Dijkstra", "astar": "A*", "bfs": "BFS", "greedy": "Greedy"}
ORDER = ["dijkstra", "astar", "bfs", "greedy"]
CRIT = {"distance": "Criterio: menor distancia", "time": "Criterio: menor tiempo"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
})


def _style(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)


def _grouped(ax, rows, metric, algos, crit, fmt=None):
    sizes = list(dict.fromkeys(r["size"] for r in rows))
    n = len(algos)
    width = min(0.8 / n, 0.2)
    for i, a in enumerate(algos):
        vals = [next(r[metric] for r in rows if r["size"] == s and r["algorithm"] == a
                     and r["criterion"] == crit) for s in sizes]
        xs = [j + (i - (n - 1) / 2) * (width + 0.02) for j in range(len(sizes))]
        bars = ax.bar(xs, vals, width, color=COLORS[a], label=LABELS[a], linewidth=0)
        if fmt:
            for b, v in zip(bars, vals):
                ax.annotate(fmt(v), (b.get_x() + b.get_width() / 2, b.get_height()),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(range(len(sizes)))
    ax.set_xticklabels([f"{s}\n({next(r['nodes'] for r in rows if r['size'] == s):,} nodos)".replace(",", ".")
                        for s in sizes])
    ax.set_title(CRIT[crit], fontsize=10, color=INK2, loc="left")
    _style(ax)


def _two_panels(rows, metric, title, ylabel, path, algos=ORDER, fmt=None):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, crit in zip(axes, ("distance", "time")):
        _grouped(ax, rows, metric, algos, crit, fmt)
    axes[0].set_ylabel(ylabel)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=len(algos), frameon=False,
               bbox_to_anchor=(0.98, 0.98))
    fig.suptitle(title, x=0.01, y=0.97, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def make_plots(data: dict, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    e1 = data["e1_scalability"]
    _two_panels(e1, "avg_expanded", "Nodos explorados promedio por búsqueda",
                "Nodos explorados", outdir / "e1_nodos_explorados.png")
    _two_panels(e1, "avg_ms", "Tiempo de cómputo promedio por búsqueda",
                "Milisegundos", outdir / "e1_tiempo_ms.png")
    _two_panels(e1, "avg_overhead_pct", "Sobrecosto promedio frente a la ruta óptima",
                "% sobre el costo óptimo", outdir / "e1_sobrecosto.png",
                algos=["bfs", "greedy"], fmt=lambda v: f"{v:.0f}%")

    c = data["e4_cache"]
    fig, ax = plt.subplots(figsize=(7, 2.4))
    names = ["Sin caché", "Con caché (Proxy)"]
    vals = [c["sin_cache"]["avg_ms"], c["con_cache"]["avg_ms"]]
    bars = ax.barh(names, vals, height=0.42, color="#2a78d6", linewidth=0)
    for b, v in zip(bars, vals):
        ax.annotate(f"{v:.3f} ms", (b.get_width(), b.get_y() + b.get_height() / 2),
                    xytext=(4, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
    ax.invert_yaxis()
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.set_xlabel("Latencia promedio por consulta (ms)")
    ax.set_xlim(0, max(vals) * 1.25)
    fig.suptitle(f"Efecto de la caché · {c['con_cache']['queries']} consultas, "
                 f"aciertos {c['con_cache']['hit_rate'] * 100:.0f}%, {c['speedup']}x más rápido",
                 x=0.01, ha="left", fontsize=11, fontweight="bold")
    fig.tight_layout()
    fig.savefig(outdir / "e4_cache.png", dpi=200)
    plt.close(fig)
