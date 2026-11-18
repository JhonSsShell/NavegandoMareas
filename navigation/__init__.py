"""Núcleo de navegación de *Navegando Mareas*.

Patrones aplicados:
    Strategy ........ strategies.py (BFS, Dijkstra, A*, Greedy) y costs.py
    Template Method . RouteStrategy.find_route
    Registry/Factory  StrategyRegistry
    Proxy ........... cache.CachingRouteProxy
    Observer ........ observer.py, cache.RouteCache, service.ActiveRouteWatcher
    Command ......... commands.py (cerrar calle, tráfico, deshacer/rehacer)
    Iterator ........ iterator.TurnByTurnIterator
    Facade .......... service.NavigationService
"""
from .domain import CityMap, Edge, NavigationError, Node
from .service import NavigationService
from .strategies import StrategyRegistry

__all__ = ["CityMap", "Edge", "Node", "NavigationError", "NavigationService",
           "StrategyRegistry"]
