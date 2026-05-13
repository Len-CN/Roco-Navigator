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


if __name__ == "__main__":
    unittest.main()
