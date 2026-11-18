"""Capa de presentación / API REST de *Navegando Mareas*.

La capa web solo traduce HTTP <-> llamadas a la fachada ``NavigationService``;
no contiene lógica de navegación.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify, render_template, request

from navigation import NavigationError, NavigationService


def create_app(service: NavigationService | None = None) -> Flask:
    app = Flask(__name__)
    svc = service or NavigationService()
    app.config["NAV_SERVICE"] = svc

    def body() -> dict:
        return request.get_json(silent=True) or {}

    @app.errorhandler(NavigationError)
    def handle_navigation_error(err):
        return jsonify({"error": str(err)}), 400

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "map_version": svc.city.version})

    @app.get("/api/map")
    def get_map():
        return jsonify(svc.map_state())

    @app.post("/api/route")
    def route():
        data = body()
        return jsonify(svc.route(
            data.get("origin", ""), data.get("destination", ""),
            data.get("algorithm", "astar"), data.get("criterion", "time"),
            use_cache=bool(data.get("use_cache", True))))

    @app.post("/api/compare")
    def compare():
        data = body()
        return jsonify(svc.compare(data.get("origin", ""),
                                   data.get("destination", ""),
                                   data.get("criterion", "time")))

    @app.post("/api/commands")
    def command():
        data = body()
        return jsonify(svc.apply_command(data.get("type", ""), data.get("u", ""),
                                         data.get("v", ""),
                                         float(data.get("factor", 2.0))))

    @app.post("/api/commands/undo")
    def undo():
        return jsonify(svc.undo())

    @app.post("/api/commands/redo")
    def redo():
        return jsonify(svc.redo())

    @app.post("/api/reset")
    def reset():
        return jsonify(svc.reset())

    @app.get("/api/events")
    def events():
        return jsonify(svc.events.to_list())

    @app.get("/api/metrics")
    def metrics():
        return jsonify(svc.metrics())

    @app.get("/api/benchmark")
    def benchmark():
        return jsonify(NavigationService.benchmark(
            request.args.get("size", 40), request.args.get("pairs", 15)))

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
