import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from roco_navigator.ui.main_window import MainWindow


class MainWindowRouteHelperTest(unittest.TestCase):
    def test_fallback_start_removes_first_resource_from_targets(self):
        resources = [
            {"x": 1, "y": 2, "name": "起点"},
            {"x": 3, "y": 4, "name": "目标"},
        ]

        start, targets = MainWindow._route_start_and_targets(None, resources)

        self.assertEqual(start, (1, 2))
        self.assertEqual(targets, [resources[1]])

    def test_tracker_position_keeps_all_resources_as_targets(self):
        resources = [
            {"x": 1, "y": 2, "name": "目标一"},
            {"x": 3, "y": 4, "name": "目标二"},
        ]

        start, targets = MainWindow._route_start_and_targets((9, 9), resources)

        self.assertEqual(start, (9, 9))
        self.assertEqual(targets, resources)

    def test_route_edit_display_adds_all_teleports_and_dedupes(self):
        base = [
            {"id": "res_1", "x": 1, "y": 2, "name": "目标", "mark_type_name": "矿石"},
            {"id": "tp_1", "x": 5, "y": 6, "name": "传送甲", "mark_type_name": "传送点"},
        ]
        all_resources = base + [
            {"id": "tp_2", "x": 7, "y": 8, "name": "传送乙", "mark_type_name": "传送点"},
            {"id": "res_2", "x": 9, "y": 10, "name": "未筛选目标", "mark_type_name": "宝箱"},
        ]

        display = MainWindow._resources_for_route_edit_display(base, all_resources)

        self.assertEqual([r["id"] for r in display], ["res_1", "tp_1", "tp_2"])

    def test_normal_display_helper_does_not_add_teleports(self):
        base = [
            {"id": "res_1", "x": 1, "y": 2, "name": "目标", "mark_type_name": "矿石"},
        ]

        display = MainWindow._merge_resources_by_id_or_coord(base, [])

        self.assertEqual(display, base)

    def test_route_teleport_metadata_marks_segments_ending_at_teleport(self):
        points = [(0, 0), (10, 10), (20, 20), (30, 30)]
        teleports = [(20, 20)]

        teleport_segments, hub_indices = MainWindow._route_teleport_metadata(points, teleports)

        self.assertEqual(teleport_segments, {1})
        self.assertEqual(hub_indices, {2})

    def test_route_teleport_metadata_ignores_normal_resources(self):
        points = [(0, 0), (10, 10), (20, 20)]
        teleports = [(99, 99)]

        teleport_segments, hub_indices = MainWindow._route_teleport_metadata(points, teleports)

        self.assertEqual(teleport_segments, set())
        self.assertEqual(hub_indices, set())


if __name__ == "__main__":
    unittest.main()
