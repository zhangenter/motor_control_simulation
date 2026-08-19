import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt5.QtCore import QLocale, QPoint, QPointF, Qt
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QGroupBox, QLineEdit, QVBoxLayout, QWidget
    from servolab.app import ServoLabWindow
    from servolab.config import CurrentAxis, LoopMode, ReferenceType, SpeedEstimatorMethod
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
            self.assertEqual(len(window.plots.plots), 6)
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

    def test_manual_command_accepts_dot_decimal_in_non_dot_locale(self):
        original_locale = QLocale()
        QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
        window = ServoLabWindow()
        try:
            field = window.command_manual
            self.assertEqual(field.locale().decimalPoint(), ".")
            field.setFocus()
            field.selectAll()
            QTest.keyClicks(field, "0.25")
            QTest.keyClick(field, Qt.Key_Return)
            self.app.processEvents()
            self.assertAlmostEqual(field.value(), 0.25)
            self.assertAlmostEqual(window.config.command.manual_value, 0.25)
        finally:
            window.close()
            QLocale.setDefault(original_locale)

    def test_application_menus_expose_experiment_window_and_toolbox_actions(self):
        window = ServoLabWindow()
        try:
            menus = [action.text() for action in window.menuBar().actions()]
            self.assertEqual(menus, ["实验", "窗口", "工具箱"])
            experiment_actions = [
                action.text() for action in window.menuBar().actions()[0].menu().actions()
                if not action.isSeparator()
            ]
            window_actions = [
                action for action in window.menuBar().actions()[1].menu().actions()
                if not action.isSeparator()
            ]
            toolbox_actions = [
                action.text() for action in window.menuBar().actions()[2].menu().actions()
            ]
            self.assertEqual(experiment_actions, ["新建实验", "打开实验…", "保存实验…", "退出"])
            self.assertEqual(
                [action.text() for action in window_actions],
                ["实验参数", "实时状态", "运行日志", "自定义控制器"],
            )
            self.assertTrue(
                all(action.isCheckable() and action.isChecked() for action in window_actions)
            )
            self.assertEqual(toolbox_actions, ["PID 计算器…"])
        finally:
            window.close()

    def test_window_menu_toggles_side_panels_and_bottom_tabs(self):
        window = ServoLabWindow()
        try:
            window.show()
            self.app.processEvents()

            window.parameters_view_action.setChecked(False)
            window.realtime_view_action.setChecked(False)
            self.assertTrue(window.parameters.isHidden())
            self.assertTrue(window.right_panel.isHidden())

            window.log_view_action.setChecked(False)
            self.assertFalse(window.bottom_tabs.isTabVisible(window.log_tab_index))
            self.assertFalse(window.bottom_panel.isHidden())

            window.custom_controller_view_action.setChecked(False)
            self.assertFalse(
                window.bottom_tabs.isTabVisible(window.custom_controller_tab_index)
            )
            self.assertTrue(window.bottom_panel.isHidden())

            window.log_view_action.setChecked(True)
            self.assertTrue(window.bottom_tabs.isTabVisible(window.log_tab_index))
            self.assertFalse(window.bottom_panel.isHidden())

            window.parameters_view_action.setChecked(True)
            window.realtime_view_action.setChecked(True)
            window.custom_controller_view_action.setChecked(True)
            self.assertFalse(window.parameters.isHidden())
            self.assertFalse(window.right_panel.isHidden())
            self.assertTrue(
                window.bottom_tabs.isTabVisible(window.custom_controller_tab_index)
            )
        finally:
            window.close()

    def test_realtime_metrics_panel_can_be_dragged_wider(self):
        window = ServoLabWindow()
        try:
            window.show()
            self.app.processEvents()

            window.horizontal_splitter.setSizes([300, 650, 500])
            self.app.processEvents()

            self.assertGreater(window.right_panel.width(), 300)
            self.assertEqual(window.horizontal_splitter.handleWidth(), 5)
        finally:
            window.close()

    def test_pid_calculator_applies_selected_loop_to_current_experiment(self):
        window = ServoLabWindow()
        try:
            calculator = window.pid_calculator
            calculator.prepare(window.config.motor)
            calculator.loop_combo.setCurrentText("速度环")
            calculator.speed_frequency.setValue(18.0)
            calculator.calculate()
            expected = calculator.last_result
            self.assertIsNotNone(expected)
            calculator.apply_result()
            self.assertAlmostEqual(window.config.control.speed.kp, expected.kp, places=5)
            self.assertAlmostEqual(window.config.control.speed.ki, expected.ki, places=5)
            self.assertEqual(window.config.control.speed.kd, 0.0)
            self.assertEqual(window.parameters.tabs.currentIndex(), 2)
            self.assertEqual(window.parameters.pid_tabs.currentIndex(), 1)
        finally:
            window.close()

    def test_new_experiment_action_restores_defaults(self):
        window = ServoLabWindow()
        try:
            window.parameters.experiment_name.setText("已修改")
            window.current_pid.kp.setValue(99.0)
            window.new_experiment_action.trigger()
            self.assertEqual(window.config.name, "未命名实验")
            self.assertEqual(window.parameters.experiment_name.text(), "未命名实验")
            self.assertEqual(window.config.control.current.kp, 4.0)
            self.assertFalse(window.running)
        finally:
            window.close()

    def test_feedback_tab_separates_encoder_estimator_and_inertia(self):
        window = ServoLabWindow()
        try:
            tab_names = [window.parameters.tabs.tabText(i) for i in range(window.parameters.tabs.count())]
            self.assertIn("反馈", tab_names)
            editor = window.parameters.feedback_editor
            editor.estimator_method.setCurrentText(SpeedEstimatorMethod.IDEAL.value)
            self.assertEqual(
                window.config.feedback.speed_estimator.method,
                SpeedEstimatorMethod.IDEAL,
            )
            self.assertFalse(editor.estimator_cutoff.isEnabled())
            editor.estimator_method.setCurrentText(SpeedEstimatorMethod.FILTERED_DIFFERENCE.value)
            self.assertTrue(editor.estimator_cutoff.isEnabled())
            editor.estimator_method.setCurrentText(SpeedEstimatorMethod.PLL.value)
            self.assertTrue(editor.estimator_cutoff.isHidden())
            self.assertFalse(editor.pll_bandwidth.isHidden())
            editor.pll_bandwidth.setValue(45.0)
            self.assertEqual(window.config.feedback.speed_estimator.pll_bandwidth, 45.0)
            editor.estimator_method.setCurrentText(
                SpeedEstimatorMethod.ORTHOGONAL_PLL.value
            )
            self.assertFalse(editor.pll_speed_limit.isHidden())
            editor.pll_speed_limit.setValue(1500.0)
            self.assertEqual(window.config.feedback.speed_estimator.pll_speed_limit, 1500.0)
            editor.estimator_method.setCurrentText(SpeedEstimatorMethod.KALMAN.value)
            self.assertFalse(editor.kalman_acceleration_noise.isHidden())
            self.assertTrue(editor.pll_bandwidth.isHidden())
            self.assertTrue(editor.pll_speed_limit.isHidden())
            editor.estimator_method.setCurrentText(SpeedEstimatorMethod.STATE_OBSERVER.value)
            self.assertFalse(editor.observer_bandwidth.isHidden())
            group_titles = {
                group.title() for group in window.parameters.findChildren(QGroupBox)
            }
            self.assertIn("编码器", group_titles)
            self.assertIn("速度估算", group_titles)
            self.assertIn("组合负载与惯量", group_titles)
            self.assertIn("speed_actual", window.plots.curves)
        finally:
            window.close()

    def test_disturbance_tab_groups_mechanical_load_and_electrical_cards(self):
        window = ServoLabWindow()
        try:
            editor = window.parameters.disturbance_editor
            tab_names = [editor.tabs.tabText(i) for i in range(editor.tabs.count())]
            self.assertEqual(tab_names, ["机械", "负载", "电气"])
            group_titles = {group.title() for group in editor.findChildren(QGroupBox)}
            self.assertTrue(
                {
                    "齿槽转矩",
                    "摩擦模型",
                    "组合负载与惯量",
                    "逆变器开关与死区",
                    "直流母线波动",
                    "反电动势非正弦谐波",
                }.issubset(group_titles)
            )

            editor.pwm_enabled.setChecked(True)
            editor.dead_time_enabled.setChecked(True)
            editor.bus_voltage_enabled.setChecked(True)
            editor.back_emf_enabled.setChecked(True)
            editor.pwm_frequency.setValue(12000.0)
            editor.dead_time_us.setValue(3.0)
            editor.bus_ripple.setValue(7.0)
            editor.back_emf_amplitude.setValue(9.0)

            self.assertTrue(window.config.disturbance.pwm_enabled)
            self.assertTrue(window.config.disturbance.dead_time_enabled)
            self.assertTrue(window.config.disturbance.bus_voltage_enabled)
            self.assertTrue(window.config.disturbance.back_emf_enabled)
            self.assertEqual(window.config.disturbance.pwm_switching_frequency, 12000.0)
            self.assertEqual(window.config.disturbance.dead_time_us, 3.0)
            self.assertEqual(window.config.disturbance.bus_voltage_ripple_percent, 7.0)
            self.assertEqual(window.config.disturbance.back_emf_harmonic_percent, 9.0)
        finally:
            window.close()

    def test_disturbance_changes_preserve_plot_channel_selection(self):
        window = ServoLabWindow()
        try:
            expected = {
                "id_ref": True,
                "id": False,
                "iq_ref": True,
                "iq": False,
                "applied_vd": True,
                "applied_vq": False,
                "bus_voltage": True,
            }
            for key, checked in expected.items():
                window.plots.channel_checks[key].setChecked(checked)
            editor = window.parameters.disturbance_editor
            editor.pwm_enabled.setChecked(True)
            editor.pwm_ripple.setValue(3.5)
            editor.bus_voltage_enabled.setChecked(True)
            editor.bus_ripple.setValue(8.0)
            self.app.processEvents()
            self.assertEqual(
                {key: window.plots.channel_checks[key].isChecked() for key in expected},
                expected,
            )
        finally:
            window.close()

    def test_current_axis_change_selects_only_matching_current_channels(self):
        window = ServoLabWindow()
        try:
            window.mode_combo.setCurrentText(LoopMode.CURRENT.value)
            window.parameters.axis_d.click()
            self.app.processEvents()
            self.assertTrue(window.plots.channel_checks["id_ref"].isChecked())
            self.assertTrue(window.plots.channel_checks["id"].isChecked())
            self.assertFalse(window.plots.channel_checks["iq_ref"].isChecked())
            self.assertFalse(window.plots.channel_checks["iq"].isChecked())
            window.parameters.axis_q.click()
            self.app.processEvents()
            self.assertFalse(window.plots.channel_checks["id_ref"].isChecked())
            self.assertFalse(window.plots.channel_checks["id"].isChecked())
            self.assertTrue(window.plots.channel_checks["iq_ref"].isChecked())
            self.assertTrue(window.plots.channel_checks["iq"].isChecked())
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

    def test_current_loop_axis_selector_updates_command_and_metrics(self):
        window = ServoLabWindow()
        try:
            window.mode_combo.setCurrentText(LoopMode.CURRENT.value)
            window.parameters.axis_d.click()
            self.app.processEvents()
            self.assertEqual(window.config.command.current_axis, CurrentAxis.D)
            self.assertTrue(window.parameters.current_test.isVisibleTo(window.parameters))
            self.assertEqual(window.parameters.command_group.title(), "Id 指令发生器")
            self.assertIn("Iq* = 0.000 A", window.parameters.current_test.hint.text())
            self.assertEqual(window.parameters.current_axis_tabs.currentIndex(), 0)
            self.assertEqual(window.topology.current_axis, CurrentAxis.D)
            window.command_amplitude.setValue(0.18)
            window.simulation.run_offline(0.3)
            window._refresh_ui()
            self.assertEqual(window.metric_peak_title.text(), "Id峰值")
            self.assertAlmostEqual(window.simulation.last_sample["iq_ref"], 0.0)
            self.assertAlmostEqual(window.simulation.last_sample["speed_actual"], 0.0)
        finally:
            window.close()

    def test_d_and_q_current_pid_editors_update_independently(self):
        window = ServoLabWindow()
        try:
            original_q = window.config.control.current.kp
            window.current_d_pid.kp.setValue(6.5)
            self.assertAlmostEqual(window.config.control.current_d.kp, 6.5)
            self.assertAlmostEqual(window.config.control.current.kp, original_q)
            self.assertAlmostEqual(window.simulation.controller.current_d.config.kp, 6.5)
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
            self.assertIn("编码器位置 = 20 rad", label.toPlainText())
            self.assertNotIn("位置误差", label.toPlainText())
        finally:
            dashboard.close()


if __name__ == "__main__":
    unittest.main()
