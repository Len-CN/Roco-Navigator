"""
路线规划

聚类 + 区域内 TSP 算法，适合游戏跑图资源收集。
"""

import logging
import math
import time
import random
from typing import List, Tuple, Optional

try:
    from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

logger = logging.getLogger(__name__)


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """两点间的欧氏距离"""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return math.sqrt(dx * dx + dy * dy)


def total_distance(route: List[Tuple[float, float]]) -> float:
    """计算路线总距离"""
    return sum(distance(route[i], route[i + 1]) for i in range(len(route) - 1))


class PathPlanner:
    """
    路线规划器

    使用空间聚类 + 区域内 TSP 的两层算法。

    流程:
    1. K-Means 将点位分成空间簇
    2. 最近邻对簇排序
    3. 每个簇内用最近邻 + 2-opt 求解
    4. 串联为最终路线
    """

    def __init__(self, use_2opt: bool = True, max_iterations: int = 1000):
        self._use_2opt = use_2opt
        self._max_iterations = max_iterations
        logger.info("PathPlanner initialized (2-opt=%s)", use_2opt)

    def plan_route(self, start: Tuple[float, float],
                   targets: List[Tuple[float, float]],
                   strategy: str = "auto") -> List[Tuple[float, float]]:
        """
        规划从起点经过所有目标点的路线。

        Args:
            start: 起始坐标 (x, y)
            targets: 目标点列表 [(x, y), ...]
            strategy: "auto" / "nearest" / "ortools"

        Returns:
            有序路线 [start, target1, target2, ...]
        """
        if not targets:
            return [start]
        if len(targets) == 1:
            return [start, targets[0]]

        start_time = time.perf_counter()

        if strategy == "nearest":
            # Fast: just NN, no optimization
            route = self._nearest_neighbor(start, list(targets))
        elif strategy == "ortools" and HAS_ORTOOLS:
            route = self._solve_ortools(start, list(targets))
        elif strategy == "auto" and HAS_ORTOOLS and len(targets) <= 500:
            route = self._solve_ortools(start, list(targets))
        else:
            # Default: cluster + NN + 2-opt
            if len(targets) <= 20:
                route = self._nearest_neighbor(start, list(targets))
                if self._use_2opt:
                    route = self._optimize_2opt(route)
            else:
                route = self._cluster_route(start, list(targets))

        elapsed = time.perf_counter() - start_time
        dist = total_distance(route)
        logger.info("Route planned: %d targets, %.0f distance, %.2fs (strategy=%s, ortools=%s)",
                     len(targets), dist, elapsed, strategy, HAS_ORTOOLS)
        return route

    # ==================== Clustering ====================

    def _cluster_route(self, start, targets):
        """Cluster-based route planning"""
        # Step 1: K-Means clustering
        k = max(1, min(30, len(targets) // 15))
        if k <= 1:
            route = self._nearest_neighbor(start, targets)
            if self._use_2opt:
                route = self._optimize_2opt(route)
            return route

        clusters = self._kmeans(targets, k)

        # Step 2: Order clusters by nearest-neighbor from start
        cluster_centers = []
        for cluster in clusters:
            if cluster:
                cx = sum(p[0] for p in cluster) / len(cluster)
                cy = sum(p[1] for p in cluster) / len(cluster)
                cluster_centers.append((cx, cy))
            else:
                cluster_centers.append((0, 0))

        ordered_indices = self._order_clusters(start, cluster_centers)

        # Step 3: Solve TSP within each cluster and concatenate
        route = [start]
        current = start
        for idx in ordered_indices:
            cluster = clusters[idx]
            if not cluster:
                continue
            # Find nearest point in cluster to current position as entry
            sub_route = self._nearest_neighbor(current, cluster)
            if self._use_2opt and len(sub_route) <= 200:
                sub_route = self._optimize_2opt(sub_route)
            route.extend(sub_route[1:])  # skip the start (which is 'current')
            current = route[-1]

        return route

    def _kmeans(self, points, k, max_iter=20):
        """Simple K-Means clustering"""
        # K-Means++ initialization
        centroids = [random.choice(points)]
        for _ in range(1, min(k, len(points))):
            dists = [min(distance(p, c) for c in centroids) ** 2 for p in points]
            total = sum(dists)
            if total == 0:
                break
            probs = [d / total for d in dists]
            cumulative = []
            s = 0
            for p_val in probs:
                s += p_val
                cumulative.append(s)
            r = random.random()
            for idx_c, c_val in enumerate(cumulative):
                if r <= c_val:
                    centroids.append(points[idx_c])
                    break
            else:
                centroids.append(points[-1])
        clusters = [[] for _ in range(k)]

        for _ in range(max_iter):
            # Assign points to nearest centroid
            clusters = [[] for _ in range(k)]
            for p in points:
                min_dist = float('inf')
                min_idx = 0
                for i, c in enumerate(centroids):
                    d = distance(p, c)
                    if d < min_dist:
                        min_dist = d
                        min_idx = i
                clusters[min_idx].append(p)

            # Update centroids
            new_centroids = []
            converged = True
            for i, cluster in enumerate(clusters):
                if cluster:
                    cx = sum(p[0] for p in cluster) / len(cluster)
                    cy = sum(p[1] for p in cluster) / len(cluster)
                    new_c = (cx, cy)
                    if distance(new_c, centroids[i]) > 1.0:
                        converged = False
                    new_centroids.append(new_c)
                else:
                    new_centroids.append(centroids[i])

            centroids = new_centroids
            if converged:
                break

        return clusters

    def _order_clusters(self, start, centers):
        """Order cluster centers by nearest neighbor from start"""
        ordered = []
        remaining = list(range(len(centers)))
        current = start
        while remaining:
            nearest_idx = min(remaining, key=lambda i: distance(current, centers[i]))
            ordered.append(nearest_idx)
            remaining.remove(nearest_idx)
            current = centers[nearest_idx]
        return ordered

    # ==================== TSP Solvers ====================

    def _nearest_neighbor(self, start, targets):
        """Nearest neighbor heuristic"""
        route = [start]
        remaining = set(range(len(targets)))
        current = start
        while remaining:
            nearest_idx = min(remaining, key=lambda i: distance(current, targets[i]))
            remaining.remove(nearest_idx)
            route.append(targets[nearest_idx])
            current = targets[nearest_idx]
        return route

    def _optimize_2opt(self, route, max_time=2.0):
        """2-opt optimization with O(1) delta computation"""
        if len(route) < 4:
            return route

        best = list(route)
        improved = True
        iterations = 0
        start_time = time.perf_counter()

        while improved and iterations < self._max_iterations:
            improved = False
            iterations += 1

            if time.perf_counter() - start_time > max_time:
                break

            for i in range(1, len(best) - 2):
                for j in range(i + 2, len(best)):
                    # O(1) delta computation
                    # Current edges: (i-1, i) and (j, j+1 if exists)
                    d_old = distance(best[i - 1], best[i])
                    d_new = distance(best[i - 1], best[j])

                    if j + 1 < len(best):
                        d_old += distance(best[j], best[j + 1])
                        d_new += distance(best[i], best[j + 1])

                    if d_new < d_old - 0.001:
                        # Reverse segment [i, j]
                        best[i:j + 1] = best[i:j + 1][::-1]
                        improved = True
                        break
                if improved:
                    break

        return best

    def _solve_ortools(self, start, targets):
        """Solve TSP using Google Or-Tools (optimal for < 1000 points)."""
        all_points = [start] + list(targets)
        n = len(all_points)

        # Build distance matrix
        dist_matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    dist_matrix[i][j] = int(distance(all_points[i], all_points[j]))

        manager = pywrapcp.RoutingIndexManager(n, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def dist_callback(from_idx, to_idx):
            from_node = manager.IndexToNode(from_idx)
            to_node = manager.IndexToNode(to_idx)
            return dist_matrix[from_node][to_node]

        transit_id = routing.RegisterTransitCallback(dist_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_id)

        # Search parameters
        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        # Time limit: scale with problem size
        time_limit = min(10, max(1, n // 50))
        search_params.time_limit.FromSeconds(time_limit)

        solution = routing.SolveWithParameters(search_params)
        if solution is None:
            logger.warning("Or-Tools failed, falling back to NN+2-opt")
            route = self._nearest_neighbor(start, list(targets))
            if self._use_2opt:
                route = self._optimize_2opt(route)
            return route

        # Extract route
        route = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route.append(all_points[node])
            index = solution.Value(routing.NextVar(index))

        return route
