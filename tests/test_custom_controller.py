import unittest

from servolab.config import ControlConfig, LoopMode, MotorConfig, allowed_reference_types
from servolab.custom_controller import (
    ControllerGenerationOptions,
    CustomControllerError,
    CustomControllerProcess,
    generate_custom_controller_code,
)


class CustomControllerTests(unittest.TestCase):
    def test_valid_controller(self):
        process = CustomControllerProcess(timeout_s=0.2)
        try:
            process.start("def control(state, reference, params, dt):\n    return {'vd': 1, 'vq': 2}\n")
            self.assertEqual(process.update({}, {}, 0.001), (1.0, 2.0))
        finally:
            process.stop()

    def test_missing_entrypoint(self):
        process = CustomControllerProcess(timeout_s=0.2)
        with self.assertRaises(CustomControllerError):
            process.start("value = 1")

    def test_generated_controllers_cover_every_topology_and_target(self):
        state = {"id": 0.0, "iq": 0.0, "theta": 0.0, "omega": 0.0, "torque": 0.0, "t": 0.0}
        reference = {
            "command": 0.0,
            "user_input": 0.0,
            "position": 1.0,
            "speed": 10.0,
            "current": 2.0,
        }
        options = ControllerGenerationOptions(True, True, True, True, True)
        for mode in LoopMode:
            for reference_type in allowed_reference_types(mode):
                with self.subTest(mode=mode, reference_type=reference_type):
                    control = ControlConfig(mode=mode)
                    code = generate_custom_controller_code(
                        mode,
                        reference_type,
                        control,
                        MotorConfig(),
                        options,
                    )
                    self.assertIn(f"# 控制方式：{mode.value}", code)
                    self.assertIn(f"# 控制目标：{reference_type.value}", code)
                    process = CustomControllerProcess(timeout_s=0.2)
                    try:
                        process.start(code)
                        vd, vq = process.update(state, reference, 0.001)
                        self.assertIsInstance(vd, float)
                        self.assertIsInstance(vq, float)
                    finally:
                        process.stop()

    def test_generation_options_change_emitted_code(self):
        control = ControlConfig(mode=LoopMode.CURRENT_SPEED)
        plain = generate_custom_controller_code(
            LoopMode.CURRENT_SPEED,
            allowed_reference_types(LoopMode.CURRENT_SPEED)[0],
            control,
            MotorConfig(),
            ControllerGenerationOptions(anti_windup=False),
        )
        compensated = generate_custom_controller_code(
            LoopMode.CURRENT_SPEED,
            allowed_reference_types(LoopMode.CURRENT_SPEED)[0],
            control,
            MotorConfig(),
            ControllerGenerationOptions(True, True, True, True, True),
        )
        self.assertNotIn("反电动势补偿", plain)
        self.assertIn("反电动势补偿", compensated)
        self.assertNotIn("current_kff", plain)
        self.assertIn("current_kff", compensated)
        self.assertNotIn("条件积分", plain)
        self.assertIn("条件积分", compensated)


if __name__ == "__main__":
    unittest.main()
