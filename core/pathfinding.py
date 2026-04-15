"""
路径规划

实现最近邻算法和 2-opt 优化的路径规划。
"""

import logging
import math
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """两点之间的欧几里得距离"""
    return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)


def total_distance(route: List[Tuple[float, float]]) -> float:
    """路线总距离"""
    if len(route) < 2:
        return 0.0
    return sum(distance(route[i], route[i + 1]) for i in range(len(route) - 1))


class PathPlanner:
    """
    路径规划器

    算法:
    1. nearest_neighbor: 最近邻贪心算法
    2. optimize_2opt: 2-opt 局部优化
    3. plan_route: 组合方案 (最近邻 + 2-opt)
    """

    def __init__(self, use_2opt: bool = True, max_2opt_iterations: int = 1000):
        self._use_2opt = use_2opt
        self._max_iterations = max_2opt_iterations
        logger.info("PathPlanner initialized (2-opt=%s)", use_2opt)

    def plan_route(self, start: Tuple[float, float],
                   targets: List[Tuple[float, float]],
                   strategy: str = "nearest"
                   ) -> List[Tuple[float, float]]:
        """
        规划路线

        Args:
            start: 起点
            targets: 目标点列表
            strategy: "nearest" (最近邻) 或 "optimal" (最近邻+2-opt)

        Returns:
            排序后的路线点列表 (含起点)
        """
        if not targets:
            return [start]

        if len(targets) == 1:
            return [start, targets[0]]

        # Step 1: 初始路线
        if strategy == "greedy" and len(targets) <= 300:
            route = self.greedy_insertion(start, targets)
        else:
            route = self.nearest_neighbor(start, targets)

        # Step 2: 2-opt 优化 (仅当点数合理时)
        if self._use_2opt and len(route) <= 200:
            route = self.optimize_2opt(route)

        dist = total_distance(route)
        logger.info("Route planned: %d points, distance=%.0f, strategy=%s",
                     len(route), dist, strategy)
        return route

    def nearest_neighbor(self, start: Tuple[float, float],
                         targets: List[Tuple[float, float]]
                         ) -> List[Tuple[float, float]]:
        """
        最近邻贪心算法

        从起点开始，每次选择距离当前点最近的未访问点。

        Args:
            start: 起点
            targets: 目标点列表

        Returns:
            排序后的路线 (含起点)
        """
        route = [start]
        remaining = list(targets)
        current = start

        while remaining:
            nearest_pt = min(remaining, key=lambda p: distance(current, p))
            route.append(nearest_pt)
            remaining.remove(nearest_pt)
            current = nearest_pt

        return route

    def greedy_insertion(self, start: Tuple[float, float],
                         targets: List[Tuple[float, float]]
                         ) -> List[Tuple[float, float]]:
        """
        贪心插入算法
        
        从起点出发，每次将未访问的点插入到路线中使总距离增加最少的位置。
        比最近邻算法通常能得到更好的路线。
        """
        if not targets:
            return [start]
        if len(targets) == 1:
            return [start, targets[0]]
        
        # Start with the farthest point from start
        route = [start]
        remaining = list(targets)
        
        # Add first point: nearest to start
        first = min(remaining, key=lambda p: distance(start, p))
        route.append(first)
        remaining.remove(first)
        
        while remaining:
            best_cost = float('inf')
            best_point = None
            best_pos = 1
            
            for pt in remaining:
                # Try inserting pt at each position in route
                for i in range(1, len(route)):
                    # Cost of inserting between route[i-1] and route[i]
                    cost = (distance(route[i-1], pt) + distance(pt, route[i]) 
                            - distance(route[i-1], route[i]))
                    if cost < best_cost:
                        best_cost = cost
                        best_point = pt
                        best_pos = i
                
                # Also try appending at end
                cost = distance(route[-1], pt)
                if cost < best_cost:
                    best_cost = cost
                    best_point = pt
                    best_pos = len(route)
            
            route.insert(best_pos, best_point)
            remaining.remove(best_point)
        
        return route

    def optimize_2opt(self, route: List[Tuple[float, float]]
                      ) -> List[Tuple[float, float]]:
        """
        2-opt 局部优化 (带时间限制)
        """
        import time
        
        if len(route) < 4:
            return route

        best = list(route)
        best_dist = total_distance(best)
        improved = True
        iterations = 0
        start_time = time.perf_counter()
        max_time = 2.0  # 最多2秒

        while improved and iterations < self._max_iterations:
            improved = False
            iterations += 1

            if time.perf_counter() - start_time > max_time:
                logger.debug("2-opt: time limit reached at iteration %d", iterations)
                break

            for i in range(1, len(best) - 2):
                for j in range(i + 2, len(best)):
                    new_route = best[:i] + best[i:j][::-1] + best[j:]
                    new_dist = total_distance(new_route)

                    if new_dist < best_dist - 0.001:
                        best = new_route
                        best_dist = new_dist
                        improved = True
                        break
                if improved:
                    break

        if iterations > 1:
            logger.debug("2-opt: %d iterations, distance reduced to %.0f", iterations, best_dist)

        return best

    def calculate_route_info(self, route: List[Tuple[float, float]]) -> dict:
        """
        计算路线信息

        Args:
            route: 路线点列表

        Returns:
            路线信息 dict
        """
        if len(route) < 2:
            return {"points": len(route), "total_distance": 0, "segments": []}

        segments = []
        for i in range(len(route) - 1):
            d = distance(route[i], route[i + 1])
            segments.append({
                "from": route[i],
                "to": route[i + 1],
                "distance": d
            })

        return {
            "points": len(route),
            "total_distance": total_distance(route),
            "segments": segments,
            "avg_segment": total_distance(route) / max(1, len(route) - 1),
        }
