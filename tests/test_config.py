import math
import tempfile
import unittest
from pathlib import Path

from servolab.config import (
    CommandType,
    CurrentAxis,
    ExperimentConfig,
    LoopMode,
    ReferenceType,
    SpeedEstimatorMethod,
)


class ConfigTests(unittest.TestCase):
    def test_json_roundtrip(self):
        cfg = ExperimentConfig(name="干扰实验")
        cfg.control.mode = LoopMode.CURRENT_SPEED
        cfg.command.kind = CommandType.SINE
        cfg.command.reference_type = ReferenceType.SPEED
        cfg.command.current_axis = CurrentAxis.D
        cfg.command.lock_rotor = False
        cfg.control.current_d.kp = 2.75
        cfg.disturbance.cogging_enabled = True
        cfg.disturbance.pwm_enabled = True
        cfg.disturbance.pwm_switching_frequency = 16000.0
        cfg.disturbance.dead_time_enabled = True
        cfg.disturbance.dead_time_us = 1.5
        cfg.disturbance.bus_voltage_enabled = True
        cfg.disturbance.bus_voltage_ripple_percent = 8.0
        cfg.disturbance.back_emf_enabled = True
        cfg.disturbance.back_emf_harmonic_order = 12
        cfg.feedback.encoder.resolution = 4096
        cfg.feedback.speed_estimator.method = SpeedEstimatorMethod.KALMAN
        cfg.feedback.speed_estimator.kalman_acceleration_noise = 750.0
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "experiment.json"
            cfg.save(path)
            loaded = ExperimentConfig.load(path)
        self.assertEqual(loaded.name, cfg.name)
        self.assertEqual(loaded.control.mode, LoopMode.CURRENT_SPEED)
        self.assertEqual(loaded.command.kind, CommandType.SINE)
        self.assertEqual(loaded.command.reference_type, ReferenceType.SPEED)
        self.assertEqual(loaded.command.current_axis, CurrentAxis.D)
        self.assertFalse(loaded.command.lock_rotor)
        self.assertEqual(loaded.control.current_d.kp, 2.75)
        self.assertTrue(loaded.disturbance.cogging_enabled)
        self.assertTrue(loaded.disturbance.pwm_enabled)
        self.assertEqual(loaded.disturbance.pwm_switching_frequency, 16000.0)
        self.assertTrue(loaded.disturbance.dead_time_enabled)
        self.assertEqual(loaded.disturbance.dead_time_us, 1.5)
        self.assertTrue(loaded.disturbance.bus_voltage_enabled)
        self.assertEqual(loaded.disturbance.bus_voltage_ripple_percent, 8.0)
        self.assertTrue(loaded.disturbance.back_emf_enabled)
        self.assertEqual(loaded.disturbance.back_emf_harmonic_order, 12)
        self.assertEqual(loaded.feedback.encoder.resolution, 4096)
        self.assertEqual(loaded.feedback.speed_estimator.method, SpeedEstimatorMethod.KALMAN)
        self.assertEqual(loaded.feedback.speed_estimator.kalman_acceleration_noise, 750.0)
        self.assertEqual(loaded.speed_unit, "rpm")

    def test_orthogonal_pll_config_roundtrip(self):
        cfg = ExperimentConfig()
        cfg.feedback.speed_estimator.method = SpeedEstimatorMethod.ORTHOGONAL_PLL
        cfg.feedback.speed_estimator.pll_speed_limit = 1800.0
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "orthogonal-pll.json"
            cfg.save(path)
            loaded = ExperimentConfig.load(path)

        self.assertEqual(
            loaded.feedback.speed_estimator.method,
            SpeedEstimatorMethod.ORTHOGONAL_PLL,
        )
        self.assertEqual(loaded.feedback.speed_estimator.pll_speed_limit, 1800.0)

    def test_legacy_encoder_fields_are_migrated_with_ideal_speed_feedback(self):
        loaded = ExperimentConfig.from_dict(
            {
                "speed_unit": "rpm",
                "disturbance": {
                    "encoder_noise_std": 0.001,
                    "encoder_resolution": 2048,
                    "encoder_delay": 0.003,
                },
            }
        )
        self.assertEqual(loaded.feedback.encoder.noise_std, 0.001)
        self.assertEqual(loaded.feedback.encoder.resolution, 2048)
        self.assertEqual(loaded.feedback.encoder.delay, 0.003)
        self.assertEqual(loaded.feedback.speed_estimator.method, SpeedEstimatorMethod.IDEAL)
        self.assertNotIn("encoder_resolution", loaded.to_dict()["disturbance"])

    def test_legacy_rad_s_config_is_migrated_to_rpm(self):
        loaded = ExperimentConfig.from_dict(
            {
                "control": {
                    "mode": LoopMode.CURRENT_SPEED.value,
                    "speed": {
                        "kp": 0.08,
                        "ki": 1.8,
                        "kd": 0.0,
                        "kff": 0.0,
                        "output_limit": 12.0,
                        "integral_limit": 8.0,
                    },
                },
                "command": {
                    "reference_type": ReferenceType.SPEED.value,
                    "amplitude": 2.0 * math.pi,
                    "trajectory_value": [0.0, 2.0 * math.pi],
                },
                "disturbance": {"stribeck_velocity": 0.5},
            }
        )
        self.assertEqual(loaded.speed_unit, "rpm")
        self.assertAlmostEqual(loaded.command.amplitude, 60.0)
        self.assertAlmostEqual(loaded.command.trajectory_value[-1], 60.0)
        self.assertAlmostEqual(loaded.control.speed.kp, 0.08 * 2.0 * math.pi / 60.0)
        self.assertAlmostEqual(loaded.disturbance.stribeck_velocity, 15.0 / math.pi)

    def test_legacy_current_config_defaults_to_q_axis_and_copies_d_axis_pid(self):
        loaded = ExperimentConfig.from_dict(
            {
                "speed_unit": "rpm",
                "control": {
                    "mode": LoopMode.CURRENT.value,
                    "current": {"kp": 5.0, "ki": 900.0},
                },
                "command": {"reference_type": ReferenceType.CURRENT.value},
            }
        )
        self.assertEqual(loaded.command.current_axis, CurrentAxis.Q)
        self.assertFalse(loaded.command.lock_rotor)
        self.assertEqual(loaded.control.current_d.kp, 5.0)
        self.assertEqual(loaded.control.current_d.ki, 900.0)


if __name__ == "__main__":
    unittest.main()
