import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from roco_navigator.data.route_manager import Route, RouteManager


class RouteManagerTest(unittest.TestCase):
    def _manager(self, path):
        return RouteManager(data_path=path)

    def test_save_and_load_new_points_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "routes.json")
            manager = self._manager(path)
            manager.add(Route(
                id="route_a",
                name="测试路线",
                points=[(1, 2), (3, 4), (5, 6)],
                total_distance=10,
                strategy="custom",
            ))
            self.assertTrue(manager.save())

            loaded = self._manager(path)
            self.assertTrue(loaded.load())
            route = loaded.get_all()[0]
            self.assertEqual(route.points, [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)])
            self.assertEqual(route.targets, [(3.0, 4.0), (5.0, 6.0)])

    def test_load_legacy_targets_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "routes.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": "1.0.0",
                    "routes": [{
                        "id": "legacy",
                        "name": "旧路线",
                        "targets": [{"x": 10, "y": 20}, {"x": 30, "y": 40}],
                    }],
                }, f)

            manager = self._manager(path)
            self.assertTrue(manager.load())
            self.assertEqual(manager.get_by_id("legacy").points, [(10.0, 20.0), (30.0, 40.0)])

    def test_import_conflicts_keep_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "routes.json")
            import_path = os.path.join(tmp, "import.json")
            manager = self._manager(path)
            manager.add(Route(id="same", name="同名", points=[(1, 1), (2, 2)]))

            with open(import_path, "w", encoding="utf-8") as f:
                json.dump(RouteManager.export_payload([
                    Route(id="same", name="同名", points=[(3, 3), (4, 4)])
                ]), f, ensure_ascii=False)

            imported = manager.import_routes(import_path)
            self.assertEqual(len(imported), 1)
            self.assertNotEqual(imported[0].id, "same")
            self.assertNotEqual(imported[0].name, "同名")
            self.assertEqual(manager.count, 2)

    def test_export_all_can_be_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            export_path = os.path.join(tmp, "export.json")
            source = self._manager(os.path.join(tmp, "routes.json"))
            source.add(Route(id="r1", name="路线1", points=[(1, 2), (3, 4)]))
            self.assertTrue(source.export_all(export_path))

            target = self._manager(os.path.join(tmp, "target.json"))
            imported = target.import_routes(export_path)
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].points, [(1.0, 2.0), (3.0, 4.0)])


if __name__ == "__main__":
    unittest.main()
