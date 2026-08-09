import math
import tempfile
import unittest
from pathlib import Path

from servolab.config import (
    CommandType,
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
        cfg.disturbance.cogging_enabled = True
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
        self.assertTrue(loaded.disturbance.cogging_enabled)
        self.assertEqual(loaded.feedback.encoder.resolution, 4096)
        self.assertEqual(loaded.feedback.speed_estimator.method, SpeedEstimatorMethod.KALMAN)
        self.assertEqual(loaded.feedback.speed_estimator.kalman_acceleration_noise, 750.0)
        self.assertEqual(loaded.speed_unit, "rpm")

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


if __name__ == "__main__":
    unittest.main()
