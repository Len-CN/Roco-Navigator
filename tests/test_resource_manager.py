import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from roco_navigator.data.resource_manager import Resource, ResourceManager


class ResourceManagerIndexTest(unittest.TestCase):
    def _manager(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return ResourceManager(data_path=os.path.join(tmp.name, "resources.json"))

    def test_update_rebuilds_type_indexes(self):
        manager = self._manager()
        manager.add(Resource(
            id="a",
            name="旧点位",
            type="旧类型",
            x=1,
            y=2,
            mark_type_name="旧细分",
        ))

        self.assertTrue(manager.update(Resource(
            id="a",
            name="新点位",
            type="新类型",
            x=3,
            y=4,
            mark_type_name="新细分",
        )))

        self.assertEqual(manager.get_types(), ["新类型"])
        self.assertEqual(manager.get_mark_type_names(), ["新细分"])

    def test_delete_rebuilds_type_indexes(self):
        manager = self._manager()
        manager.add(Resource(
            id="a",
            name="点位",
            type="采集",
            x=1,
            y=2,
            mark_type_name="草药",
        ))

        self.assertTrue(manager.delete("a"))

        self.assertEqual(manager.get_types(), [])
        self.assertEqual(manager.get_mark_type_names(), [])


if __name__ == "__main__":
    unittest.main()
