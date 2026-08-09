import math
import unittest

from servolab.units import rad_s_to_rpm, rpm_to_rad_s


class UnitConversionTests(unittest.TestCase):
    def test_rotational_speed_conversions(self):
        self.assertAlmostEqual(rpm_to_rad_s(60.0), 2.0 * math.pi)
        self.assertAlmostEqual(rad_s_to_rpm(2.0 * math.pi), 60.0)
        self.assertAlmostEqual(rad_s_to_rpm(rpm_to_rad_s(-1234.5)), -1234.5)


if __name__ == "__main__":
    unittest.main()
