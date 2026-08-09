import math
import unittest

from servolab.config import EncoderConfig, SpeedEstimatorConfig, SpeedEstimatorMethod
from servolab.feedback import EncoderModel, SpeedEstimator


class FeedbackTests(unittest.TestCase):
    def test_encoder_quantizes_and_delays_position(self):
        encoder = EncoderModel(EncoderConfig(resolution=4, delay=0.1), dt=0.1)
        first = encoder.measure(0.2)
        second = encoder.measure(2.0)
        third = encoder.measure(3.4)
        self.assertAlmostEqual(first, 0.0)
        self.assertAlmostEqual(second, 0.0)
        self.assertAlmostEqual(third, math.pi / 2.0)

    def test_position_difference_recovers_constant_speed(self):
        estimator = SpeedEstimator(
            SpeedEstimatorConfig(method=SpeedEstimatorMethod.DIFFERENCE)
        )
        dt = 0.01
        estimator.update(0.0, dt)
        speed = estimator.update(2.0 * math.pi * dt, dt)
        self.assertAlmostEqual(speed, 60.0)

    def test_filtered_difference_uses_cutoff_frequency(self):
        estimator = SpeedEstimator(
            SpeedEstimatorConfig(
                method=SpeedEstimatorMethod.FILTERED_DIFFERENCE,
                cutoff_frequency=10.0,
            )
        )
        estimator.update(0.0, 0.01)
        speed = estimator.update(2.0 * math.pi * 0.01, 0.01)
        expected_alpha = 1.0 - math.exp(-2.0 * math.pi * 10.0 * 0.01)
        self.assertAlmostEqual(speed, expected_alpha * 60.0)

    def test_ideal_method_is_explicit_ground_truth_bypass(self):
        estimator = SpeedEstimator(SpeedEstimatorConfig(method=SpeedEstimatorMethod.IDEAL))
        self.assertEqual(estimator.update(123.0, 0.01, true_speed=456.0), 456.0)

    def test_model_based_estimators_track_constant_speed(self):
        dt = 0.001
        methods = (
            SpeedEstimatorMethod.PLL,
            SpeedEstimatorMethod.KALMAN,
            SpeedEstimatorMethod.STATE_OBSERVER,
        )
        for method in methods:
            with self.subTest(method=method):
                estimator = SpeedEstimator(
                    SpeedEstimatorConfig(method=method),
                    EncoderConfig(noise_std=0.0001, resolution=65536),
                )
                speed = 0.0
                for index in range(2000):
                    position = 2.0 * math.pi * index * dt
                    speed = estimator.update(position, dt)
                self.assertAlmostEqual(speed, 60.0, delta=0.2)

    def test_kalman_measurement_variance_includes_noise_and_quantization(self):
        encoder = EncoderConfig(noise_std=0.001, resolution=1024)
        estimator = SpeedEstimator(
            SpeedEstimatorConfig(method=SpeedEstimatorMethod.KALMAN),
            encoder,
        )
        quantum = 2.0 * math.pi / encoder.resolution
        expected = encoder.noise_std**2 + quantum**2 / 12.0
        self.assertAlmostEqual(estimator._measurement_variance(), expected)


if __name__ == "__main__":
    unittest.main()
