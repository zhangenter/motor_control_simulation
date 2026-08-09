import tempfile
import unittest
from pathlib import Path

from servolab.config import ExperimentConfig
from servolab.services import (
    ControllerSourceService,
    ExperimentService,
    ExportService,
    SimulationSession,
)


class FakeControllerRuntime:
    def __init__(self):
        self.running = False

    def start(self, code):
        self.running = True

    def update(self, state, reference, dt):
        return 0.0, 0.0

    def stop(self):
        self.running = False


class ServiceTests(unittest.TestCase):
    def test_headless_persistence_services(self):
        config = ExperimentConfig(name="service-test")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config_path = root / "experiment.json"
            source_path = ControllerSourceService.save(root / "controller", "def control():\n    pass\n")
            trajectory_path = root / "trajectory.csv"
            trajectory_path.write_text("time,value\n0,1\n0.1,2\n", encoding="utf-8")

            ExperimentService.save(config, config_path)
            loaded = ExperimentService.load(config_path)
            times, values = ExperimentService.load_trajectory(trajectory_path)

            self.assertEqual(loaded.name, config.name)
            self.assertEqual(source_path.suffix, ".py")
            self.assertIn("def control", ControllerSourceService.load(source_path))
            self.assertEqual(times, [0.0, 0.1])
            self.assertEqual(values, [1.0, 2.0])

    def test_simulation_session_lifecycle(self):
        config = ExperimentConfig(name="session-test")
        config.simulation.dt = 0.001
        config.simulation.plot_interval = 0.001
        config.simulation.duration = 0.004
        runtime = FakeControllerRuntime()
        session = SimulationSession(config, runtime)

        session.start()
        self.assertTrue(session.running)
        session.step(4)
        self.assertIsNotNone(session.keep_comparison())
        session.start_custom_controller("ignored by fake")
        self.assertTrue(session.simulation.use_custom_controller)
        session.stop_custom_controller()
        self.assertFalse(session.simulation.use_custom_controller)
        session.reset()
        self.assertFalse(session.running)

    def test_export_service_writes_history(self):
        config = ExperimentConfig()
        config.simulation.dt = 0.001
        config.simulation.plot_interval = 0.001
        session = SimulationSession(config, FakeControllerRuntime())
        session.run_offline(0.004)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.csv"
            ExportService.export_csv(session.simulation.history, path)
            content = path.read_text(encoding="utf-8")
        self.assertIn("time", content.splitlines()[0])
        self.assertGreater(len(content.splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
