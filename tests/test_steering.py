import math
import unittest

from arrietty_up.steering import effective_steering_degrees, world_yaw_degrees


def rotation_y(degrees):
    angle = math.radians(degrees)
    return (
        (math.cos(angle), 0.0, math.sin(angle)),
        (0.0, 1.0, 0.0),
        (-math.sin(angle), 0.0, math.cos(angle)),
    )


class SteeringTests(unittest.TestCase):
    def test_mounting_orientation_is_removed(self):
        baseline = rotation_y(30.0)
        current = rotation_y(40.0)
        self.assertAlmostEqual(world_yaw_degrees(current, baseline), 10.0)

    def test_deadzone_gain_and_limit(self):
        self.assertEqual(effective_steering_degrees(1.4), 0.0)
        self.assertAlmostEqual(effective_steering_degrees(11.5), 5.0)
        self.assertEqual(effective_steering_degrees(100.0), 15.0)
        self.assertEqual(effective_steering_degrees(-100.0), -15.0)


if __name__ == "__main__":
    unittest.main()
