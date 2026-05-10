"""
路线规划

方向扫描 (Directional Sweep) 算法，适合游戏跑图资源收集。
支持「传送中继点」（庇护所/小庇护所/传送点）作为零代价瞬移枢纽。

原则：单向推进、少回头、就近优先、散点顺路收割、
      密集区连贯清扫、不跨地图乱跳、总路径最短且平滑。
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple
from statistics import median

try:
    from ortools.constraint_solver import routing_enums_pb2, pywrapcp
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False

logger = logging.getLogger(__name__)


# 可作为传送中继点的细分类名（mark_type_name）
# 仅「传送点」是真传送，庇护所是营地无瞬移功能
TELEPORT_HUB_TYPES = frozenset({"传送点"})


def distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """两点间的欧氏距离"""
    dx = p1[0] - p2[0]
    dy = p1[1] - p2[1]
    return math.sqrt(dx * dx + dy * dy)


def total_distance(route) -> float:
    """计算路线总距离

    兼容 RoutePlan 与 List[point]：传 RoutePlan 时直接返回 total_cost
    （包含瞬移收益），传 list 时按欧氏累加（旧行为）。
    """
    if isinstance(route, RoutePlan):
        return route.total_cost
    return sum(distance(route[i], route[i + 1]) for i in range(len(route) - 1))


@dataclass
class RoutePlan:
    """路线规划结果

    - points: 含起点的访问顺序点列表
    - teleport_segments: i ∈ set 表示 points[i] -> points[i+1] 是瞬移段
    - total_cost: 综合代价（瞬移段算 teleport_cost）
    - used_strategy: 实际使用的算法标识

    透明兼容旧调用：旧代码把返回值当 list[point] 用时，__iter__ /
    __getitem__ / __len__ 透传到 points。
    """
    points: List[Tuple[float, float]]
    teleport_segments: Set[int] = field(default_factory=set)
    total_cost: float = 0.0
    used_strategy: str = ""

    def __iter__(self):
        return iter(self.points)

    def __getitem__(self, i):
        return self.points[i]

    def __len__(self):
        return len(self.points)


def _pair_cost(p, q, hub_set, teleport_cost):
    """段代价：终点是 hub 用 teleport_cost（任意位置可瞬移到 hub），
    否则按欧氏距离步行。
    """
    if q in hub_set:
        return teleport_cost
    return distance(p, q)


def _route_cost(points, hub_set, teleport_cost):
    """整条路径的 hub-aware 代价"""
    return sum(_pair_cost(points[i], points[i + 1], hub_set, teleport_cost)
               for i in range(len(points) - 1))


def _mark_teleport_segments(points, hub_set):
    """瞬移段：终点是 hub 的段（任何位置都可瞬移到 hub）"""
    return {i for i in range(len(points) - 1)
            if points[i + 1] in hub_set}


def _compress_hub_chains(points, hub_set):
    """压缩连续 hub 节点链。

    任意位置都能瞬移到任意 hub，所以连续 hub [..., h1, h2, h3, ...]
    中前面的 h1, h2 都是冗余 — 直接瞬移到 h3 即可。仅保留链尾。
    """
    if len(points) < 2:
        return list(points)
    out = [points[0]]
    i = 1
    while i < len(points):
        if points[i] in hub_set:
            j = i
            while j + 1 < len(points) and points[j + 1] in hub_set:
                j += 1
            # 连续 hub [i..j] 仅保留最后一个
            out.append(points[j])
            i = j + 1
        else:
            out.append(points[i])
            i += 1
    return out


class PathPlanner:
    """
    路线规划器

    默认使用方向扫描 (Directional Sweep) 算法：
    1. PCA 确定点云主方向（扫描轴）
    2. 沿扫描轴自适应分割条带
    3. 蛇形遍历各条带（牛耕式覆盖）
    4. 2-opt 局部优化消除交叉
    5. （可选）插入 hub 中转节点缩短长段

    有 OR-Tools 时 auto 策略优先使用 OR-Tools。
    """

    def __init__(self, use_2opt: bool = True, max_iterations: int = 1000):
        self._use_2opt = use_2opt
        self._max_iterations = max_iterations
        logger.info("PathPlanner initialized (2-opt=%s, ortools=%s)",
                     use_2opt, HAS_ORTOOLS)

    def plan_route(self, start: Tuple[float, float],
                   targets: List[Tuple[float, float]],
                   strategy: str = "auto",
                   *,
                   teleport_hubs: Optional[List[Tuple[float, float]]] = None,
                   teleport_cost: float = 0.0,
                   end: Optional[Tuple[float, float]] = None) -> RoutePlan:
        """
        规划从起点经过所有目标点的路线。

        Args:
            start: 起始坐标 (x, y)
            targets: 必访目标点列表 [(x, y), ...]
            strategy: "auto" / "nearest" / "ortools"
            teleport_hubs: 可作为瞬移枢纽的点列表（如庇护所/传送点）
            teleport_cost: hub 之间瞬移的代价（默认 0）
            end: 终点策略
                None    → 开放路径（停在最后一个点）
                =start  → 环形（回到起点）
                =(x,y)  → 必须以指定点结束

        Returns:
            RoutePlan
        """
        hubs = list(teleport_hubs) if teleport_hubs else []
        hub_set = set(hubs)
        # 起点/终点/必访 target 撞 hub 时，从 hub_set 中剔除（hub 仅作辅助节点）
        hub_set.discard(tuple(start))
        if end is not None:
            hub_set.discard(tuple(end))
        target_set = set(targets) if targets else set()
        hub_set -= target_set
        hubs = [h for h in hubs if h in hub_set]

        if not targets:
            points = [start] if end is None else [start, end]
            return RoutePlan(points=points, teleport_segments=set(),
                             total_cost=_route_cost(points, hub_set, teleport_cost),
                             used_strategy="trivial")

        start_time = time.perf_counter()

        # 选择算法
        use_ortools = HAS_ORTOOLS and strategy in ("auto", "ortools")
        if strategy == "ortools" and not HAS_ORTOOLS:
            logger.warning("OR-Tools not available, falling back")

        # 阶段 1: 纯欧氏求解 target 顺序（不考虑 hub，避免组内乱跳）
        if use_ortools:
            points, used = self._solve_ortools(start, list(targets), end)
        elif strategy == "nearest" or len(targets) <= 2:
            points = self._nn_route(start, list(targets), end)
            used = "nearest"
        else:
            points = self._sweep_route(start, list(targets), end)
            used = "sweep"

        # 阶段 2: 2-opt 按欧氏距离消除交叉
        if self._use_2opt and len(points) >= 4:
            points = self._optimize_2opt_euclidean(
                points, fix_last=(end is not None))

        # 阶段 3: 仅在显著长段插入 hub 瞬移（保持组内连续）
        if hubs:
            points = self._post_insert_hubs(points, hubs, hub_set, teleport_cost)

        # 阶段 4: 压缩连续 hub（罕见，但稳妥处理）
        points = _compress_hub_chains(points, hub_set)

        teleport_segments = _mark_teleport_segments(points, hub_set)
        cost = _route_cost(points, hub_set, teleport_cost)

        elapsed = time.perf_counter() - start_time
        logger.info(
            "Route planned: %d targets, %d hubs, %d teleport segs, "
            "cost=%.0f, %.2fs (strategy=%s, ortools=%s)",
            len(targets), len(hubs), len(teleport_segments),
            cost, elapsed, used, HAS_ORTOOLS)

        return RoutePlan(points=points, teleport_segments=teleport_segments,
                         total_cost=cost, used_strategy=used)

    # ==================== 方向扫描算法 ====================

    def _sweep_route(self, start, targets, end):
        """
        方向扫描主算法（不含 hub 处理，hub 由后处理统一插入）。
        """
        axis = self._compute_sweep_axis(start, targets)
        perp = (-axis[1], axis[0])
        strips = self._split_into_strips(targets, start, axis)
        route = self._serpentine_traverse(start, strips, perp)

        # 处理 end 语义
        if end is not None and (not route or route[-1] != end):
            if end in route[1:]:
                route = [p for p in route if p != end] + [end]
            else:
                route.append(end)

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

    def _post_insert_hubs(self, route, hubs, hub_set, teleport_cost):
        """后处理：仅在显著长段插入 hub 瞬移。

        阈值用相邻段长度的中位数 * 2，配合下限保证短数据集行为合理。
        这样：
          - 组内短段不被瞬移打断（整组连续步行）
          - 组间长段才用瞬移连接（地图上虚线少而集中）
          - 整条路径仍是单条折线，无分支
        """
        if not hubs or len(route) < 2:
            return route

        seg_lens = [distance(route[i], route[i + 1])
                    for i in range(len(route) - 1)]
        if not seg_lens:
            return route

        sorted_lens = sorted(seg_lens)
        median_d = sorted_lens[len(sorted_lens) // 2]
        # 长段判定阈值：中位数 * 2，至少 100px
        threshold = max(median_d * 2.0, 100.0)

        out = [route[0]]
        for i in range(len(route) - 1):
            a, b = route[i], route[i + 1]
            # 终点本身是 hub：直接瞬移过去
            if b in hub_set:
                out.append(b)
                continue

            direct = seg_lens[i]
            # 短段不插 hub，保持组内连续
            if direct < threshold:
                out.append(b)
                continue

            # 长段：找 b 附近最近 hub
            best_h = None
            best_cost = direct
            for h in hubs:
                via = teleport_cost + distance(h, b)
                if via < best_cost:
                    best_cost = via
                    best_h = h
            if best_h is not None:
                out.append(best_h)
            out.append(b)
        return out

    # ==================== 最近邻 ====================

    def _nn_route(self, start, targets, end):
        """最近邻贪心（不含 hub，hub 由后处理统一插入）。"""
        explicit_end = None
        if end is not None and end != start:
            if end in targets:
                targets = [t for t in targets if t != end]
            explicit_end = end

        route = [start]
        remaining = list(targets)
        current = start

        while remaining:
            best_idx = 0
            best_cost = distance(current, remaining[0])
            for i in range(1, len(remaining)):
                d = distance(current, remaining[i])
                if d < best_cost:
                    best_cost = d
                    best_idx = i
            chosen = remaining.pop(best_idx)
            route.append(chosen)
            current = chosen

        # end 语义
        if end is not None and end == start:
            route.append(start)
        elif explicit_end is not None:
            route.append(explicit_end)

        return route

    # ==================== 2-opt 优化 ====================

    def _optimize_2opt_euclidean(self, route, max_time=2.0, fix_last=False):
        """2-opt 优化（纯欧氏，作用在 target 序列上，hub 由后处理插入）。

        Args:
            fix_last: 若为 True，禁止反转涉及末尾点的段（保留固定终点）。
        """
        if len(route) < 4:
            return route

        best = list(route)
        j_upper = len(best) - 1 if fix_last else len(best)

        improved = True
        iterations = 0
        start_time = time.perf_counter()

        while improved and iterations < self._max_iterations:
            improved = False
            iterations += 1

            if time.perf_counter() - start_time > max_time:
                break

            for i in range(1, len(best) - 2):
                for j in range(i + 2, j_upper):
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

    def _solve_ortools(self, start, targets, end):
        """Google OR-Tools 求解（纯欧氏 target 排序，hub 由后处理插入）。

        节点布局：[start] + targets (+ optional end_node) (+ optional dummy)
        - end=None  → 追加 dummy，dummy 到任何点距离 0（开放路径）
        - end=start → start 同时作为终点（环形）
        - end=(x,y) → 把 end 作为单独节点固定为终点
        """
        nodes = [start] + list(targets)
        dummy_idx = None

        if end is None:
            nodes.append(("__DUMMY__",))
            dummy_idx = len(nodes) - 1
            end_idx = dummy_idx
        elif end == start:
            end_idx = 0
        else:
            try:
                end_idx = nodes.index(end)
            except ValueError:
                nodes.append(end)
                end_idx = len(nodes) - 1

        n = len(nodes)
        dist_matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if dummy_idx is not None and (i == dummy_idx or j == dummy_idx):
                    dist_matrix[i][j] = 0
                else:
                    dist_matrix[i][j] = int(round(distance(nodes[i], nodes[j])))

        try:
            manager = pywrapcp.RoutingIndexManager(n, 1, [0], [end_idx])
            routing = pywrapcp.RoutingModel(manager)

            def dist_callback(from_idx, to_idx):
                return dist_matrix[manager.IndexToNode(from_idx)][manager.IndexToNode(to_idx)]

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
        except Exception as e:
            logger.warning("OR-Tools error (%s), falling back to sweep", e)
            return self._sweep_route(start, list(targets), end), "sweep_fallback"

        if solution is None:
            logger.warning("OR-Tools no solution, falling back to sweep")
            return self._sweep_route(start, list(targets), end), "sweep_fallback"

        route = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if dummy_idx is None or node != dummy_idx:
                route.append(nodes[node])
            index = solution.Value(routing.NextVar(index))
        end_node = manager.IndexToNode(index)
        if dummy_idx is None or end_node != dummy_idx:
            route.append(nodes[end_node])

        return route, "ortools"
