import math
import unittest

from servolab.config import (
    CommandType,
    CurrentAxis,
    ExperimentConfig,
    LoopMode,
    ReferenceType,
    SpeedEstimatorMethod,
)
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

    def test_electrical_disturbances_are_applied_and_recorded(self):
        cfg = ExperimentConfig()
        cfg.control.mode = LoopMode.CURRENT
        cfg.command.reference_type = ReferenceType.CURRENT
        cfg.command.kind = CommandType.STEP
        cfg.command.amplitude = 2.0
        cfg.command.start_time = 0.0
        cfg.command.lock_rotor = False
        cfg.simulation.dt = 0.0001
        cfg.simulation.plot_interval = cfg.simulation.dt
        disturbance = cfg.disturbance
        disturbance.pwm_enabled = True
        disturbance.pwm_ripple_percent = 10.0
        disturbance.dead_time_enabled = True
        disturbance.dead_time_us = 5.0
        disturbance.bus_voltage_enabled = True
        disturbance.bus_voltage_offset_percent = -20.0
        disturbance.bus_voltage_ripple_percent = 10.0
        disturbance.back_emf_enabled = True
        disturbance.back_emf_harmonic_percent = 20.0

        sim = ServoSimulation(cfg)
        sim.run_offline(0.1)
        history = sim.history.data

        self.assertGreater(max(map(abs, history["pwm_vq"])), 0.0)
        self.assertGreater(max(map(abs, history["dead_time_vq"])), 0.0)
        self.assertGreater(max(history["bus_voltage"]) - min(history["bus_voltage"]), 0.0)
        self.assertGreater(max(map(abs, history["back_emf_vq"])), 0.0)
        self.assertTrue(
            any(
                abs(commanded - applied) > 1e-6
                for commanded, applied in zip(history["vq"], history["applied_vq"])
            )
        )

    def test_disabled_electrical_disturbances_keep_nominal_applied_voltage(self):
        cfg = ExperimentConfig()
        cfg.simulation.plot_interval = cfg.simulation.dt
        sim = ServoSimulation(cfg)
        sim.run_offline(0.02)
        history = sim.history.data

        self.assertTrue(
            all(
                abs(commanded - applied) < 1e-12
                for commanded, applied in zip(history["vq"], history["applied_vq"])
            )
        )
        self.assertTrue(all(value == cfg.motor.dc_voltage for value in history["bus_voltage"]))

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

    def test_speed_feedback_is_estimated_from_quantized_encoder_position(self):
        cfg = ExperimentConfig()
        cfg.feedback.encoder.resolution = 32
        cfg.feedback.speed_estimator.method = SpeedEstimatorMethod.DIFFERENCE
        sim = ServoSimulation(cfg)
        sim.run_offline(0.4)
        differences = [
            abs(estimated - actual)
            for estimated, actual in zip(
                sim.history.data["speed"],
                sim.history.data["speed_actual"],
            )
        ]
        self.assertGreater(max(differences), 1.0)
        self.assertEqual(len(sim.history.data["position_actual"]), len(sim.history))

    def test_model_based_speed_estimators_remain_finite_in_closed_loop(self):
        methods = (
            SpeedEstimatorMethod.PLL,
            SpeedEstimatorMethod.ORTHOGONAL_PLL,
            SpeedEstimatorMethod.KALMAN,
            SpeedEstimatorMethod.STATE_OBSERVER,
        )
        for method in methods:
            with self.subTest(method=method):
                cfg = ExperimentConfig()
                cfg.feedback.speed_estimator.method = method
                sim = ServoSimulation(cfg)
                sim.run_offline(0.5)
                for key in ("position", "speed", "speed_actual", "iq", "vq"):
                    self.assertTrue(math.isfinite(sim.last_sample[key]), key)

    def test_locked_d_axis_current_step_tracks_id_without_q_current_or_motion(self):
        cfg = ExperimentConfig()
        cfg.control.mode = LoopMode.CURRENT
        cfg.command.reference_type = ReferenceType.CURRENT
        cfg.command.current_axis = CurrentAxis.D
        cfg.command.lock_rotor = True
        cfg.command.kind = CommandType.STEP
        cfg.command.amplitude = 0.18
        cfg.command.start_time = 0.0
        cfg.simulation.plot_interval = cfg.simulation.dt
        sim = ServoSimulation(cfg)
        sim.run_offline(0.2)
        self.assertAlmostEqual(sim.last_sample["id_ref"], 0.18)
        self.assertAlmostEqual(sim.last_sample["iq_ref"], 0.0)
        self.assertAlmostEqual(sim.last_sample["id"], 0.18, delta=0.002)
        self.assertAlmostEqual(sim.last_sample["iq"], 0.0, delta=1e-9)
        self.assertAlmostEqual(sim.last_sample["speed_actual"], 0.0)
        self.assertAlmostEqual(sim.last_sample["vq"], 0.0, delta=1e-9)

    def test_unlocked_q_axis_current_step_can_accelerate_rotor(self):
        cfg = ExperimentConfig()
        cfg.control.mode = LoopMode.CURRENT
        cfg.command.current_axis = CurrentAxis.Q
        cfg.command.lock_rotor = False
        cfg.command.kind = CommandType.STEP
        cfg.command.amplitude = 0.18
        cfg.command.start_time = 0.0
        sim = ServoSimulation(cfg)
        sim.run_offline(0.1)
        self.assertGreater(sim.last_sample["speed_actual"], 0.0)
        self.assertAlmostEqual(sim.last_sample["id_ref"], 0.0)
        self.assertAlmostEqual(sim.last_sample["iq_ref"], 0.18)


if __name__ == "__main__":
    unittest.main()
