"""
路线管理

负责路线的保存、加载和管理。
"""

import logging
import os
import uuid
from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

from ..utils.file_utils import load_json, save_json, get_data_dir

logger = logging.getLogger(__name__)


@dataclass
class Route:
    """路线"""
    id: str
    name: str
    points: List[Tuple[float, float]]    # [(x, y), ...]，包含起点
    total_distance: float = 0.0
    strategy: str = "nearest"            # "nearest", "optimal", "custom"
    map_id: str = "default"
    created: str = ""
    updated: str = ""
    description: str = ""

    @property
    def targets(self) -> List[Tuple[float, float]]:
        """兼容旧调用：旧版 targets 不含起点。"""
        return self.points[1:] if len(self.points) > 1 else []

    @targets.setter
    def targets(self, value: List[Tuple[float, float]]):
        self.points = list(value or [])


class RouteManager:
    """路线管理器"""

    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = os.path.join(get_data_dir(), "routes.json")

        self._data_path = data_path
        self._routes: List[Route] = []

        logger.info("RouteManager initialized")

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _normalize_points(raw_points) -> List[Tuple[float, float]]:
        points = []
        for item in raw_points or []:
            try:
                if isinstance(item, dict):
                    x, y = item.get("x"), item.get("y")
                else:
                    x, y = item[0], item[1]
                points.append((float(x), float(y)))
            except Exception:
                logger.debug("Skip invalid route point: %s", item)
        return points

    def _new_id(self) -> str:
        existing = {r.id for r in self._routes}
        while True:
            route_id = f"route_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
            if route_id not in existing:
                return route_id

    def _unique_name(self, name: str) -> str:
        base = (name or "未命名路线").strip() or "未命名路线"
        existing = {r.name for r in self._routes}
        if base not in existing:
            return base

        index = 2
        while True:
            candidate = f"{base} 副本{index}"
            if candidate not in existing:
                return candidate
            index += 1

    def _route_from_dict(self, item: dict, keep_identity: bool = True) -> Route:
        points = self._normalize_points(item.get("points"))
        if not points:
            # 兼容旧格式：targets 里只有目标点，没有单独起点。
            points = self._normalize_points(item.get("targets"))

        route_id = str(item.get("id", "")).strip()
        if not keep_identity or not route_id or self.get_by_id(route_id):
            route_id = self._new_id()

        name = item.get("name", "") or "未命名路线"
        if not keep_identity or any(r.name == name for r in self._routes):
            name = self._unique_name(name)

        created = item.get("created", "") or self._now()
        updated = item.get("updated", "") or created
        return Route(
            id=route_id,
            name=name,
            points=points,
            total_distance=float(item.get("total_distance", 0)),
            strategy=item.get("strategy", "custom"),
            map_id=item.get("map_id", "default"),
            created=created,
            updated=updated,
            description=item.get("description", ""),
        )

    @staticmethod
    def route_to_dict(route: Route) -> dict:
        return {
            "id": route.id,
            "name": route.name,
            "points": [{"x": p[0], "y": p[1]} for p in route.points],
            "total_distance": route.total_distance,
            "strategy": route.strategy,
            "map_id": route.map_id,
            "created": route.created,
            "updated": route.updated,
            "description": route.description,
        }

    @staticmethod
    def export_payload(routes: List[Route]) -> dict:
        return {
            "version": "1.1.0",
            "exported_at": datetime.now().isoformat(),
            "app": "roco_navigator",
            "routes": [RouteManager.route_to_dict(r) for r in routes],
        }

    def load(self) -> bool:
        data = load_json(self._data_path, default={"routes": []})
        if data is None:
            return False

        self._routes = []
        for item in data.get("routes", []):
            try:
                route = self._route_from_dict(item, keep_identity=True)
                self._routes.append(route)
            except Exception as e:
                logger.warning("Failed to parse route: %s", e)

        logger.info("Loaded %d routes", len(self._routes))
        return True

    def save(self) -> bool:
        data = {
            "version": "1.1.0",
            "last_updated": datetime.now().isoformat(),
            "routes": [self.route_to_dict(r) for r in self._routes]
        }
        return save_json(self._data_path, data)

    def get_all(self) -> List[Route]:
        return self._routes.copy()

    def get_by_id(self, route_id: str) -> Optional[Route]:
        for r in self._routes:
            if r.id == route_id:
                return r
        return None

    def add(self, route: Route) -> bool:
        if not route.id or self.get_by_id(route.id):
            route.id = self._new_id()
        route.name = self._unique_name(route.name)
        if not route.created:
            route.created = self._now()
        route.updated = self._now()
        self._routes.append(route)
        return True

    def update(self, route: Route) -> bool:
        for i, r in enumerate(self._routes):
            if r.id == route.id:
                if not route.created:
                    route.created = r.created or self._now()
                route.updated = self._now()
                self._routes[i] = route
                return True
        return False

    def delete(self, route_id: str) -> bool:
        for i, r in enumerate(self._routes):
            if r.id == route_id:
                self._routes.pop(i)
                return True
        return False

    def clear(self):
        self._routes.clear()

    def duplicate(self, route_id: str) -> Optional[Route]:
        source = self.get_by_id(route_id)
        if source is None:
            return None
        route = Route(
            id=self._new_id(),
            name=self._unique_name(f"{source.name} 副本"),
            points=list(source.points),
            total_distance=source.total_distance,
            strategy=source.strategy,
            map_id=source.map_id,
            created=self._now(),
            updated=self._now(),
            description=source.description,
        )
        self._routes.append(route)
        return route

    def export_route(self, route: Route, filepath: str) -> bool:
        return save_json(filepath, self.export_payload([route]))

    def export_one(self, route_id: str, filepath: str) -> bool:
        route = self.get_by_id(route_id)
        if route is None:
            return False
        return self.export_route(route, filepath)

    def export_all(self, filepath: str) -> bool:
        return save_json(filepath, self.export_payload(self._routes))

    def import_routes(self, filepath: str) -> List[Route]:
        data = load_json(filepath, default=None)
        if data is None:
            return []

        raw_routes = data.get("routes") if isinstance(data, dict) else None
        if raw_routes is None and isinstance(data, list):
            raw_routes = data
        if raw_routes is None:
            return []

        imported = []
        for item in raw_routes:
            try:
                route = self._route_from_dict(item, keep_identity=True)
                self._routes.append(route)
                imported.append(route)
            except Exception as e:
                logger.warning("Failed to import route: %s", e)
        return imported

    @property
    def count(self) -> int:
        return len(self._routes)
