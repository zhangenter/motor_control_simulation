import math
import unittest

from servolab.config import CommandType, ExperimentConfig, LoopMode, ReferenceType
from servolab.simulation import ServoSimulation


class SimulationTests(unittest.TestCase):
    def test_all_control_topologies_remain_finite(self):
        for mode in LoopMode:
            with self.subTest(mode=mode):
                cfg = ExperimentConfig()
                cfg.control.mode = mode
                sim = ServoSimulation(cfg)
                sim.run_offline(0.35)
                for key in ("position", "speed", "id", "iq", "torque", "vd", "vq"):
                    self.assertTrue(math.isfinite(sim.last_sample[key]), key)

    def test_default_cascade_tracks_position_step(self):
        sim = ServoSimulation()
        sim.run_offline(1.2)
        self.assertLess(abs(sim.last_sample["position_error"]), 0.08)

    def test_combined_disturbances_are_recorded(self):
        cfg = ExperimentConfig()
        cfg.disturbance.cogging_enabled = True
        cfg.disturbance.friction_enabled = True
        cfg.disturbance.load_enabled = True
        cfg.disturbance.load_sine_amplitude = 0.02
        sim = ServoSimulation(cfg)
        sim.run_offline(0.6)
        self.assertTrue(any(abs(v) > 0 for v in sim.history.data["cogging_torque"]))
        self.assertTrue(any(abs(v) > 0 for v in sim.history.data["friction_torque"]))
        self.assertTrue(any(abs(v) > 0 for v in sim.history.data["load_torque"]))

    def test_speed_input_is_integrated_for_position_outer_loop(self):
        cfg = ExperimentConfig()
        cfg.control.mode = LoopMode.CASCADE
        cfg.command.reference_type = ReferenceType.SPEED
        cfg.command.kind = CommandType.STEP
        cfg.command.amplitude = 120.0
        cfg.command.start_time = 0.0
        sim = ServoSimulation(cfg)
        sim.run_offline(0.5)
        self.assertAlmostEqual(sim.last_sample["command"], 120.0)
        self.assertAlmostEqual(sim.last_sample["user_speed_ref"], 120.0)
        self.assertAlmostEqual(sim.last_sample["position_ref"], 2.0 * math.pi, delta=0.002)


if __name__ == "__main__":
    unittest.main()
