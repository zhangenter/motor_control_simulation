import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtCore import QPoint, QPointF, Qt
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
    from servolab.app import ServoLabWindow
    from servolab.config import LoopMode, ReferenceType
    from servolab.ui_widgets import PlotDashboard, make_double, make_int
except ImportError:
    QApplication = None
    ServoLabWindow = None
    PlotDashboard = None


@unittest.skipIf(QApplication is None, "PyQt5/pyqtgraph 未安装")
class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_construction_and_step(self):
        window = ServoLabWindow()
        try:
            window.single_step()
            self.assertGreater(window.simulation.time, 0.0)
            self.assertEqual(window.topology.mode, window.config.control.mode)
            self.assertEqual(len(window.plots.plots), 5)
        finally:
            window.close()

    def test_form_updates_pid_online(self):
        window = ServoLabWindow()
        try:
            window.current_pid.kp.setValue(7.25)
            self.assertAlmostEqual(window.config.control.current.kp, 7.25)
            self.assertAlmostEqual(window.simulation.controller.current_q.config.kp, 7.25)
        finally:
            window.close()

    def test_number_fields_only_accept_wheel_events_while_focused(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        other_field = QLineEdit()
        double_box = make_double(5.0, step=0.5)
        int_box = make_int(5)
        layout.addWidget(other_field)
        layout.addWidget(double_box)
        layout.addWidget(int_box)
        container.show()
        self.app.processEvents()

        def wheel_up(widget):
            center = QPointF(widget.rect().center())
            event = QWheelEvent(
                center,
                QPointF(widget.mapToGlobal(widget.rect().center())),
                QPoint(),
                QPoint(0, 120),
                Qt.NoButton,
                Qt.NoModifier,
                Qt.NoScrollPhase,
                False,
            )
            QApplication.sendEvent(widget, event)
            return event

        try:
            for box, expected_step in ((double_box, 0.5), (int_box, 1)):
                other_field.setFocus()
                self.app.processEvents()
                initial_value = box.value()
                ignored_event = wheel_up(box)
                self.assertEqual(box.value(), initial_value)
                self.assertFalse(ignored_event.isAccepted())

                box.setFocus()
                self.app.processEvents()
                accepted_event = wheel_up(box)
                self.assertEqual(box.value(), initial_value + expected_step)
                self.assertTrue(accepted_event.isAccepted())
        finally:
            container.close()

    def test_custom_controller_can_take_over_output(self):
        window = ServoLabWindow()
        try:
            window.compile_custom_controller()
            self.assertTrue(window.simulation.use_custom_controller)
            window.simulation.step(2)
            self.assertTrue(window.custom_process.running)
            window.stop_custom_controller()
            self.assertFalse(window.simulation.use_custom_controller)
        finally:
            window.close()

    def test_position_outer_loop_accepts_speed_input(self):
        window = ServoLabWindow()
        try:
            window.mode_combo.setCurrentText(LoopMode.POSITION.value)
            choices = [window.reference_combo.itemText(i) for i in range(window.reference_combo.count())]
            self.assertEqual(choices, [ReferenceType.POSITION.value, ReferenceType.SPEED.value])
            window.reference_combo.setCurrentText(ReferenceType.SPEED.value)
            self.assertEqual(window.config.command.reference_type, ReferenceType.SPEED)
            self.assertEqual(window.command_amplitude.suffix(), " rpm")
            self.assertTrue(window.plots.channel_checks["user_speed_ref"].isChecked())
            self.assertEqual(window.topology.reference_type, ReferenceType.SPEED)
            window.simulation.run_offline(0.4)
            window._refresh_ui()
            self.assertEqual(window.metric_peak_title.text(), "速度峰值")
            self.assertIn("rpm", window.metric_rms.text())
        finally:
            window.close()

    def test_custom_controller_editor_opens_in_separate_resizable_dialog(self):
        window = ServoLabWindow()
        try:
            self.assertFalse(window.bottom_tabs.isAncestorOf(window.code_editor))
            self.assertTrue(window.custom_dialog.isAncestorOf(window.code_editor))
            self.assertGreaterEqual(window.custom_dialog.minimumWidth(), 760)
            self.assertGreaterEqual(window.custom_dialog.minimumHeight(), 520)

            window.open_custom_editor_button.click()
            self.app.processEvents()
            self.assertTrue(window.custom_dialog.isVisible())
            self.assertTrue(window.code_editor.hasFocus())
        finally:
            window.custom_dialog.close()
            window.close()

    def test_custom_controller_is_generated_from_current_configuration(self):
        window = ServoLabWindow()
        try:
            window.mode_combo.setCurrentText(LoopMode.CURRENT_SPEED.value)
            window.generator_feedforward.setChecked(True)
            window.generator_friction.setChecked(True)
            window.generate_custom_code_button.click()
            code = window.code_editor.toPlainText()
            self.assertIn(f"# 控制方式：{LoopMode.CURRENT_SPEED.value}", code)
            self.assertIn(f"# 控制目标：{ReferenceType.SPEED.value}", code)
            self.assertIn("参考前馈 Kff", code)
            self.assertIn("黏性摩擦补偿", code)
            self.assertIn("speed_output", code)
            self.assertIn("current_output", code)
            self.assertTrue(window.code_editor.document().isModified())
            self.assertTrue(window._custom_code_needs_compile)
        finally:
            window.close()

    def test_custom_controller_code_can_be_saved(self):
        window = ServoLabWindow()
        try:
            code = "def control(state, reference, params, dt):\n    return 1.25\n"
            window.code_editor.setPlainText(code)
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "saved_controller.py"
                with patch(
                    "servolab.ui.custom_controller_dialog.QFileDialog.getSaveFileName",
                    return_value=(str(target), "Python 代码 (*.py)"),
                ):
                    window.save_custom_code_button.click()
                self.assertEqual(target.read_text(encoding="utf-8"), code)
                self.assertFalse(window.code_editor.document().isModified())
                self.assertIn("saved_controller.py", window.custom_file_label.text())
        finally:
            window.close()

    def test_plot_cursor_reads_nearest_real_sample(self):
        dashboard = PlotDashboard()
        try:
            history = {"time": [0.0, 0.1, 0.2]}
            for key in dashboard.curves:
                history[key] = [0.0, 0.0, 0.0]
            history["position_ref"] = [0.0, 1.0, 2.0]
            history["position"] = [0.0, 10.0, 20.0]
            history["position_error"] = [0.0, -9.0, -18.0]
            dashboard.update_data(history)

            sample_time, readings = dashboard._cursor_readings(dashboard.plots[0], 0.16)
            self.assertAlmostEqual(sample_time, 0.2)
            self.assertEqual(
                {key: value for key, _name, value in readings},
                {"position_ref": 2.0, "position": 20.0, "position_error": -18.0},
            )

            dashboard.channel_checks["position_error"].setChecked(False)
            _sample_time, readings = dashboard._cursor_readings(dashboard.plots[0], 0.16)
            self.assertNotIn("position_error", {key for key, _name, _value in readings})

            dashboard.resize(800, 480)
            dashboard.show()
            self.app.processEvents()
            plot = dashboard.plots[0]
            scene_position = plot.plotItem.vb.mapViewToScene(QPointF(0.16, 19.0))
            dashboard._cursor_moved(plot, (scene_position,))
            vertical, horizontal, label = dashboard.cursor_items[plot]
            self.assertAlmostEqual(vertical.value(), 0.2)
            self.assertAlmostEqual(horizontal.value(), 20.0)
            self.assertIn("t = 0.2 s", label.toPlainText())
            self.assertIn("位置反馈 = 20 rad", label.toPlainText())
            self.assertNotIn("位置误差", label.toPlainText())
        finally:
            dashboard.close()


if __name__ == "__main__":
    unittest.main()
