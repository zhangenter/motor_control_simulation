import math
import unittest

from servolab.control import tune_current_loop, tune_position_loop, tune_speed_loop
from servolab.units import RPM_PER_RAD_S


class PIDTuningTests(unittest.TestCase):
    def test_current_loop_uses_rl_pole_cancellation(self):
        result = tune_current_loop(0.6, 0.0015, 400.0)
        omega = 2.0 * math.pi * 400.0
        self.assertAlmostEqual(result.kp, 0.0015 * omega)
        self.assertAlmostEqual(result.ki, 0.6 * omega)
        self.assertEqual(result.kd, 0.0)

    def test_speed_loop_gains_match_rpm_plant(self):
        result = tune_speed_loop(0.0008, 0.0001, 4, 0.055, 20.0, 0.707)
        omega = 2.0 * math.pi * 20.0
        plant_gain = 1.5 * 4 * 0.055 * RPM_PER_RAD_S
        self.assertAlmostEqual(
            result.kp,
            (2.0 * 0.707 * omega * 0.0008 - 0.0001) / plant_gain,
        )
        self.assertAlmostEqual(result.ki, omega * omega * 0.0008 / plant_gain)
        self.assertEqual(result.kd, 0.0)

    def test_position_loop_returns_standard_position_p_gain(self):
        result = tune_position_loop(2.0)
        self.assertAlmostEqual(result.kp, 120.0)
        self.assertEqual((result.ki, result.kd), (0.0, 0.0))

    def test_speed_loop_rejects_nonpositive_proportional_gain(self):
        with self.assertRaises(ValueError):
            tune_speed_loop(0.000001, 1.0, 1, 0.001, 0.01, 0.01)


if __name__ == "__main__":
    unittest.main()
