import math
import tempfile
import unittest
from pathlib import Path

from servolab.commands import command_value, load_trajectory_csv
from servolab.config import CommandConfig, CommandType


class CommandTests(unittest.TestCase):
    def test_step_and_ramp(self):
        cfg = CommandConfig(kind=CommandType.STEP, amplitude=3.0, offset=1.0, start_time=0.2)
        self.assertEqual(command_value(cfg, 0.1), 1.0)
        self.assertEqual(command_value(cfg, 0.2), 4.0)
        cfg.kind = CommandType.RAMP
        cfg.rise_time = 2.0
        self.assertAlmostEqual(command_value(cfg, 1.2), 2.5)

    def test_s_curve_endpoints(self):
        cfg = CommandConfig(kind=CommandType.S_CURVE, amplitude=2.0, start_time=1.0, rise_time=2.0)
        self.assertAlmostEqual(command_value(cfg, 1.0), 0.0)
        self.assertAlmostEqual(command_value(cfg, 3.0), 2.0)

    def test_trajectory_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trajectory.csv"
            path.write_text("time,value\n0,0\n1,2\n", encoding="utf-8")
            times, values = load_trajectory_csv(path)
        self.assertEqual(times, [0.0, 1.0])
        self.assertEqual(values, [0.0, 2.0])


if __name__ == "__main__":
    unittest.main()

