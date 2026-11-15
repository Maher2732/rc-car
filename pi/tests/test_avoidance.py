import unittest

from rc_pi.avoidance import AvoidanceController, nearest_in_path, stopping_distance, to_car_frame
from rc_pi.config import AvoidanceConfig
from rc_pi.protocol import (
    CORR_FLAG_ACTIVE,
    CORR_FLAG_BLOCK_FORWARD,
    CORR_FLAG_LIDAR_OK,
    NO_OBSTACLE_MM,
)


def wall(angle_from, angle_to, distance_mm, step=1.0):
    """Fake lidar returns at a constant distance across an arc of angles."""
    scan = []
    angle = angle_from
    while angle <= angle_to:
        scan.append((15, angle % 360, distance_mm))
        angle += step
    return scan


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.cfg = AvoidanceConfig()

    def test_point_straight_ahead_is_in_path(self):
        points = to_car_frame([(15, 0.0, 1000)], self.cfg)
        self.assertAlmostEqual(nearest_in_path(points, self.cfg), 1.0, places=3)

    def test_point_to_the_side_is_not_in_path(self):
        points = to_car_frame([(15, 90.0, 500)], self.cfg)
        self.assertIsNone(nearest_in_path(points, self.cfg))

    def test_points_behind_are_ignored(self):
        points = to_car_frame([(15, 180.0, 300)], self.cfg)
        self.assertIsNone(nearest_in_path(points, self.cfg))

    def test_bad_quality_and_self_hits_are_dropped(self):
        points = to_car_frame([(0, 0.0, 1000), (15, 0.0, 50)], self.cfg)
        self.assertEqual(points, [])

    def test_mounting_offset(self):
        cfg = AvoidanceConfig(lidar_forward_deg=90.0)
        points = to_car_frame([(15, 90.0, 1000)], cfg)
        self.assertAlmostEqual(nearest_in_path(points, cfg), 1.0, places=3)

    def test_stopping_distance_grows_with_speed(self):
        self.assertGreater(stopping_distance(3.0, self.cfg), stopping_distance(1.0, self.cfg))
        self.assertAlmostEqual(stopping_distance(0.0, self.cfg), self.cfg.stop_buffer)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.cfg = AvoidanceConfig()
        self.ctrl = AvoidanceController(self.cfg)

    def test_clear_path_sends_no_correction(self):
        c = self.ctrl.update(wall(-40, 40, 5000), 0.0, 1.0)
        self.assertEqual(c.flags, CORR_FLAG_LIDAR_OK)
        self.assertEqual(c.throttle_limit_pct, 100)
        self.assertEqual(c.steer_offset_deg, 0)
        self.assertAlmostEqual(c.nearest_obstacle_mm, 5000, delta=10)    # forward distance, not range

    def test_nearest_any_direction_includes_objects_off_the_path(self):
        c = self.ctrl.update(wall(-3, 3, 4000) + wall(85, 95, 600), 0.0, 1.0)
        self.assertAlmostEqual(c.nearest_any_mm, 600, delta=10)
        self.assertGreater(c.nearest_obstacle_mm, 3000)      # the side object isn't in the path

    def test_empty_scan_sends_no_obstacle(self):
        c = self.ctrl.update([], 0.0, 1.0)
        self.assertEqual(c.nearest_obstacle_mm, NO_OBSTACLE_MM)
        self.assertEqual(c.nearest_any_mm, NO_OBSTACLE_MM)
        self.assertFalse(c.flags & CORR_FLAG_ACTIVE)

    def test_close_obstacle_blocks_forward(self):
        c = self.ctrl.update(wall(-5, 5, 200), 0.0, 0.5)
        self.assertTrue(c.flags & CORR_FLAG_BLOCK_FORWARD)
        self.assertEqual(c.throttle_limit_pct, 0)

    def test_slow_zone_limits_throttle(self):
        stop = stopping_distance(1.0, self.cfg)
        mid = stop + self.cfg.slow_zone / 2
        c = self.ctrl.update(wall(-3, 3, mid * 1000), 0.0, 1.0)
        self.assertTrue(c.flags & CORR_FLAG_ACTIVE)
        self.assertFalse(c.flags & CORR_FLAG_BLOCK_FORWARD)
        self.assertTrue(self.cfg.min_slow_limit_pct < c.throttle_limit_pct < 100)

    def test_faster_car_reacts_earlier(self):
        scan = wall(-3, 3, 900)
        slow = AvoidanceController(self.cfg).update(scan, 0.0, 0.3)
        fast = AvoidanceController(self.cfg).update(scan, 0.0, 3.0)
        self.assertGreater(slow.throttle_limit_pct, fast.throttle_limit_pct)

    def test_steers_away_from_obstacle_on_the_left(self):
        # Obstacle ahead, more clutter on the left -> steer right (positive)
        scan = wall(-3, 3, 600) + wall(-60, -15, 500)
        for _ in range(5):
            c = self.ctrl.update(scan, 0.0, 1.0)
        self.assertGreater(c.steer_offset_deg, 0)

    def test_steers_away_from_obstacle_on_the_right(self):
        scan = wall(-3, 3, 600) + wall(15, 60, 500)
        for _ in range(5):
            c = self.ctrl.update(scan, 0.0, 1.0)
        self.assertLess(c.steer_offset_deg, 0)

    def test_block_releases_only_after_hysteresis(self):
        stop = stopping_distance(0.0, self.cfg)
        self.ctrl.update(wall(-3, 3, (stop - 0.05) * 1000), 0.0, 0.0)
        self.assertTrue(self.ctrl.blocked)

        # Just past the stop line: still blocked
        self.ctrl.update(wall(-3, 3, (stop + 0.05) * 1000), 0.0, 0.0)
        self.assertTrue(self.ctrl.blocked)

        # Past the hysteresis band: released
        self.ctrl.update(wall(-3, 3, (stop + 0.2) * 1000), 0.0, 0.0)
        self.assertFalse(self.ctrl.blocked)

    def test_stale_lidar_limits_speed(self):
        c = self.ctrl.update(wall(-3, 3, 5000), 5.0, 1.0)
        self.assertFalse(c.flags & CORR_FLAG_LIDAR_OK)
        self.assertTrue(c.flags & CORR_FLAG_ACTIVE)
        self.assertEqual(c.throttle_limit_pct, self.cfg.lidar_lost_limit_pct)

    def test_no_lidar_yet_limits_speed(self):
        c = self.ctrl.update(None, float("inf"), None)
        self.assertEqual(c.throttle_limit_pct, self.cfg.lidar_lost_limit_pct)

    def test_unknown_speed_is_treated_as_fast(self):
        scan = wall(-3, 3, 1200)
        unknown = AvoidanceController(self.cfg).update(scan, 0.0, None)
        crawling = AvoidanceController(self.cfg).update(scan, 0.0, 0.1)
        self.assertLess(unknown.throttle_limit_pct, crawling.throttle_limit_pct)


if __name__ == "__main__":
    unittest.main()
