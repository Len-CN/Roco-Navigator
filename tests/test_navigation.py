import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from roco_navigator.core.navigation import NavigationState, Navigator


class NavigatorProgressTest(unittest.TestCase):
    def test_start_initializes_current_target_without_visiting_first_segment(self):
        nav = Navigator(arrival_distance=5)
        nav.start([(0, 0), (10, 0), (20, 0)])

        info = nav.update(0, 0)

        self.assertEqual(info.state, NavigationState.NAVIGATING)
        self.assertEqual(info.current_target_index, 1)
        self.assertEqual(nav.visited_indices, set())

    def test_reaching_first_target_marks_only_that_target_visited(self):
        nav = Navigator(arrival_distance=5)
        nav.start([(0, 0), (10, 0), (20, 0)])

        info = nav.update(10, 0)

        self.assertEqual(info.state, NavigationState.NAVIGATING)
        self.assertEqual(info.current_target_index, 2)
        self.assertEqual(nav.visited_indices, {1})

    def test_jump_to_marks_skipped_targets_visited(self):
        nav = Navigator(arrival_distance=5)
        nav.start([(0, 0), (10, 0), (20, 0), (30, 0)])

        nav.jump_to(3)

        self.assertEqual(nav.current_index, 3)
        self.assertEqual(nav.visited_indices, {1, 2})

    def test_completion_marks_last_target_visited(self):
        nav = Navigator(arrival_distance=5)
        nav.start([(0, 0), (10, 0)])

        info = nav.update(10, 0)

        self.assertEqual(info.state, NavigationState.ARRIVED)
        self.assertEqual(info.current_target_index, 2)
        self.assertEqual(nav.visited_indices, {1})


if __name__ == "__main__":
    unittest.main()
