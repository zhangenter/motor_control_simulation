from __future__ import annotations

import math
import multiprocessing as mp
from multiprocessing.connection import Connection
from typing import Any


class CustomControllerError(RuntimeError):
    pass


class CustomControllerProcess:
    def __init__(self, timeout_s: float = 0.05):
        self.timeout_s = timeout_s
        self.process: mp.Process | None = None
        self.connection: Connection | None = None

    @property
    def running(self) -> bool:
        return bool(self.process and self.process.is_alive())

    def start(self, code: str) -> None:
        self.stop()
        parent, child = mp.Pipe()
        self.process = mp.Process(target=_worker, args=(child, code), daemon=True)
        self.process.start()
        self.connection = parent
        if not parent.poll(self.timeout_s * 10.0):
            self.stop()
            raise CustomControllerError("自定义控制器启动超时")
        message = parent.recv()
        if message.get("status") != "ready":
            self.stop()
            raise CustomControllerError(message.get("error", "自定义控制器编译失败"))

    def update(
        self,
        state: dict[str, float],
        reference: dict[str, float],
        dt: float,
    ) -> tuple[float, float]:
        if not self.running or self.connection is None:
            raise CustomControllerError("自定义控制器尚未启动")
        self.connection.send({"command": "step", "state": state, "reference": reference, "dt": dt})
        if not self.connection.poll(self.timeout_s):
            self.stop()
            raise CustomControllerError(f"自定义控制器单步响应超过 {self.timeout_s * 1000:.0f} ms")
        message = self.connection.recv()
        if message.get("status") != "ok":
            raise CustomControllerError(message.get("error", "自定义控制器执行失败"))
        return float(message["vd"]), float(message["vq"])

    def stop(self) -> None:
        if self.connection is not None:
            try:
                self.connection.send({"command": "stop"})
            except (BrokenPipeError, EOFError, OSError):
                pass
            self.connection.close()
        if self.process is not None:
            self.process.join(timeout=0.2)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=0.2)
        self.connection = None
        self.process = None


def _worker(connection: Connection, code: str) -> None:
    namespace = {"__builtins__": _safe_builtins(), "math": math}
    params: dict[str, Any] = {}
    try:
        exec(compile(code, "<custom-controller>", "exec"), namespace, namespace)
        controller = namespace.get("control")
        if not callable(controller):
            raise ValueError("代码必须定义 control(state, reference, params, dt) 函数")
    except Exception as exc:  # noqa: BLE001 - error crosses process boundary
        _send_error(connection, exc)
        connection.close()
        return
    connection.send({"status": "ready"})
    _serve_steps(connection, controller, params)
    connection.close()


def _serve_steps(connection: Connection, controller, params: dict[str, Any]) -> None:
    while True:
        try:
            message = connection.recv()
        except EOFError:
            break
        if message.get("command") == "stop":
            break
        try:
            result = controller(message["state"], message["reference"], params, float(message["dt"]))
            vd, vq = _controller_voltages(result)
            connection.send({"status": "ok", "vd": vd, "vq": vq})
        except Exception as exc:  # noqa: BLE001 - error crosses process boundary
            _send_error(connection, exc)


def _controller_voltages(result: Any) -> tuple[float, float]:
    if isinstance(result, dict):
        vd, vq = float(result.get("vd", 0.0)), float(result.get("vq", 0.0))
    else:
        vd, vq = 0.0, float(result)
    if not math.isfinite(vd) or not math.isfinite(vq):
        raise ValueError("控制器输出必须是有限数值")
    return vd, vq


def _send_error(connection: Connection, error: Exception) -> None:
    connection.send({"status": "error", "error": f"{type(error).__name__}: {error}"})


def _safe_builtins() -> dict[str, Any]:
    return {
        "abs": abs,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "pow": pow,
        "range": range,
        "round": round,
        "sum": sum,
        "tuple": tuple,
    }
