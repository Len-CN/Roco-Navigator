"""
路线规划

方向扫描 (Directional Sweep) 算法，适合游戏跑图资源收集。

原则：单向推进、少回头、就近优先、散点顺路收割、
      密集区连贯清扫、不跨地图乱跳、总路径最短且平滑。
"""

import logging
import math
import time
from typing import List, Tuple
from statistics import median

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

    默认使用方向扫描 (Directional Sweep) 算法：
    1. PCA 确定点云主方向（扫描轴）
    2. 沿扫描轴自适应分割条带
    3. 蛇形遍历各条带（牛耕式覆盖）
    4. 2-opt 局部优化消除交叉

    有 OR-Tools 时 auto 策略优先使用 OR-Tools。
    """

    def __init__(self, use_2opt: bool = True, max_iterations: int = 1000):
        self._use_2opt = use_2opt
        self._max_iterations = max_iterations
        logger.info("PathPlanner initialized (2-opt=%s, ortools=%s)",
                     use_2opt, HAS_ORTOOLS)

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
            route = self._nn_route(start, list(targets))
            if self._use_2opt:
                route = self._optimize_2opt(route)
        elif strategy == "ortools" and HAS_ORTOOLS:
            route = self._solve_ortools(start, list(targets))
        elif strategy == "auto" and HAS_ORTOOLS:
            # 有 OR-Tools 时优先使用
            route = self._solve_ortools(start, list(targets))
        else:
            # 无 OR-Tools 时使用方向扫描
            if len(targets) <= 5:
                route = self._nn_route(start, list(targets))
                if self._use_2opt:
                    route = self._optimize_2opt(route)
            else:
                route = self._sweep_route(start, list(targets))

        elapsed = time.perf_counter() - start_time
        dist = total_distance(route)
        logger.info("Route planned: %d targets, %.0f distance, %.2fs "
                     "(strategy=%s, ortools=%s)",
                     len(targets), dist, elapsed, strategy, HAS_ORTOOLS)
        return route

    # ==================== 方向扫描算法 ====================

    def _sweep_route(self, start, targets):
        """
        方向扫描主算法

        沿点云主方向推进，蛇形扫描覆盖所有点位。
        """
        # Phase 1: 确定扫描方向
        axis = self._compute_sweep_axis(start, targets)
        perp = (-axis[1], axis[0])  # 垂直轴

        # Phase 2: 自适应条带分割
        strips = self._split_into_strips(targets, start, axis)

        # Phase 3: 蛇形遍历
        route = self._serpentine_traverse(start, strips, perp)

        # Phase 4: 2-opt 局部优化
        if self._use_2opt:
            route = self._optimize_2opt(route)

        return route

    def _compute_sweep_axis(self, start, targets):
        """
        PCA 计算主扫描方向。

        Returns:
            (ax, ay) 归一化方向向量，从起点端指向远端
        """
        n = len(targets)

        # 质心
        cx = sum(p[0] for p in targets) / n
        cy = sum(p[1] for p in targets) / n

        # 协方差矩阵
        cov_xx = sum((p[0] - cx) ** 2 for p in targets) / n
        cov_xy = sum((p[0] - cx) * (p[1] - cy) for p in targets) / n
        cov_yy = sum((p[1] - cy) ** 2 for p in targets) / n

        # 2x2 矩阵的特征值/特征向量（解析解）
        trace = cov_xx + cov_yy
        det = cov_xx * cov_yy - cov_xy * cov_xy
        discriminant = max(0, trace * trace / 4.0 - det)
        sqrt_disc = math.sqrt(discriminant)

        # 最大特征值对应的特征向量 = 主方向
        lambda1 = trace / 2.0 + sqrt_disc

        if abs(cov_xy) > 1e-9:
            ax = lambda1 - cov_yy
            ay = cov_xy
        elif cov_xx >= cov_yy:
            ax, ay = 1.0, 0.0
        else:
            ax, ay = 0.0, 1.0

        # 归一化
        length = math.sqrt(ax * ax + ay * ay)
        if length < 1e-9:
            ax, ay = 1.0, 0.0
        else:
            ax /= length
            ay /= length

        # 确保方向从起点指向质心（起点在低端）
        to_center_x = cx - start[0]
        to_center_y = cy - start[1]
        dot = ax * to_center_x + ay * to_center_y
        if dot < 0:
            ax, ay = -ax, -ay

        return (ax, ay)

    def _split_into_strips(self, targets, start, axis):
        """
        沿扫描轴自适应分割条带。

        用间距中位数的 2 倍作为分割阈值，
        间距大的地方切开，间距小的地方合并。

        Returns:
            List[List[Tuple]] — 按扫描方向排序的条带列表
        """
        ax, ay = axis

        # 计算每个点在扫描轴上的投影
        projected = []
        for p in targets:
            proj = (p[0] - start[0]) * ax + (p[1] - start[1]) * ay
            projected.append((proj, p))

        # 按投影值排序
        projected.sort(key=lambda x: x[0])

        # 计算相邻点的间距
        gaps = []
        for i in range(1, len(projected)):
            gap = projected[i][0] - projected[i - 1][0]
            gaps.append(gap)

        if not gaps:
            return [[p for _, p in projected]]

        # 自适应阈值：间距中位数的 2 倍
        gap_threshold = median(gaps) * 2.0
        # 至少保证一个最小值，避免所有点都被分开
        gap_threshold = max(gap_threshold, 20.0)

        # 按间距分割条带
        strips = []
        current_strip = [projected[0][1]]

        for i in range(1, len(projected)):
            if gaps[i - 1] > gap_threshold:
                strips.append(current_strip)
                current_strip = [projected[i][1]]
            else:
                current_strip.append(projected[i][1])

        if current_strip:
            strips.append(current_strip)

        return strips

    def _serpentine_traverse(self, start, strips, perp):
        """
        蛇形遍历所有条带。

        奇数条带沿垂直轴正向排序，偶数条带反向排序，
        形成牛耕式 (boustrophedon) 路径。
        """
        px, py = perp
        route = [start]

        for i, strip in enumerate(strips):
            # 沿垂直轴的投影排序
            strip_sorted = sorted(
                strip,
                key=lambda p: p[0] * px + p[1] * py,
                reverse=(i % 2 == 1)
            )

            # 条带入口优化：如果条带反向排列后入口更近，就翻转
            if len(route) > 0 and len(strip_sorted) > 1:
                last = route[-1]
                d_first = distance(last, strip_sorted[0])
                d_last = distance(last, strip_sorted[-1])
                if d_last < d_first:
                    strip_sorted.reverse()

            route.extend(strip_sorted)

        return route

    # ==================== 最近邻 ====================

    def _nn_route(self, start, targets):
        """最近邻贪心算法（小规模回退用）"""
        route = [start]
        remaining = set(range(len(targets)))
        current = start
        while remaining:
            nearest_idx = min(remaining, key=lambda i: distance(current, targets[i]))
            remaining.remove(nearest_idx)
            route.append(targets[nearest_idx])
            current = targets[nearest_idx]
        return route

    # ==================== 2-opt 优化 ====================

    def _optimize_2opt(self, route, max_time=2.0):
        """2-opt 优化，O(1) delta 计算"""
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
                    d_old = distance(best[i - 1], best[i])
                    d_new = distance(best[i - 1], best[j])

                    if j + 1 < len(best):
                        d_old += distance(best[j], best[j + 1])
                        d_new += distance(best[i], best[j + 1])

                    if d_new < d_old - 0.001:
                        best[i:j + 1] = best[i:j + 1][::-1]
                        improved = True
                        break
                if improved:
                    break

        return best

    # ==================== OR-Tools ====================

    def _solve_ortools(self, start, targets):
        """Google OR-Tools 求解（有 OR-Tools 时的最优解）"""
        all_points = [start] + list(targets)
        n = len(all_points)

        # 构建距离矩阵
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

        search_params = pywrapcp.DefaultRoutingSearchParameters()
        search_params.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_params.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        time_limit = min(10, max(1, n // 50))
        search_params.time_limit.FromSeconds(time_limit)

        solution = routing.SolveWithParameters(search_params)
        if solution is None:
            logger.warning("OR-Tools failed, falling back to sweep")
            return self._sweep_route(start, list(targets))

        route = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            route.append(all_points[node])
            index = solution.Value(routing.NextVar(index))

        return route
