# ServoLab PMSM 伺服电机控制示教器

ServoLab 是一个面向控制算法教学和实验对比的 PyQt5 桌面仿真软件。它以永磁同步伺服电机（PMSM）的 dq 数学模型为对象，提供电流、速度、位置单环与多环串级控制、常见机械/测量干扰、实时曲线、离线仿真以及自定义控制器接口。

## 主要功能

- PMSM dq 电气模型、机械模型、编码器采样、母线电压与电流限幅
- 电流环、速度环、位置环和多种组合/串级控制拓扑
- PI/PID 参数在线修改，支持前馈、积分限幅、输出限幅和测量低通滤波
- 阶跃、斜坡、正弦、梯形、S 曲线、手动给定和 CSV 轨迹
- 位置外环可独立选择位置输入或速度输入；速度输入自动积分为连续位置指令
- 齿槽转矩、Stribeck/静摩擦/库仑摩擦/黏性摩擦、组合负载、编码器噪声/量化/延迟、负载惯量变化
- 实时、暂停、单步、离线高速仿真和多次实验曲线叠加
- 曲线通道选择、十字游标读数、滚轮缩放、拖动平移和手动给定线拖动
- CSV 数据、PNG 曲线和 JSON 实验配置导入导出
- 独立进程运行的 Python 自定义控制器，带超时和异常处理

## 运行

推荐 Python 3.10 或 3.11。

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

仓库已提供一个复合干扰实验和一条轨迹文件：

- `examples/combined_disturbance.json`
- `examples/trajectory.csv`

指令幅值的单位由“用户输入”决定。含位置外环的拓扑可选择位置输入（rad）或速度输入（rpm）；速度输入会在每个仿真步内换算并积分成位置指令。纯速度拓扑固定为 rpm，纯电流拓扑固定为 A。速度指令、反馈、误差、曲线、CSV 数据及自定义控制器接口均统一使用 rpm；PMSM 物理方程内部会在需要时显式换算为 rad/s。

运行全部测试（包含桌面 UI、核心无界面运行和架构约束）：

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

## 架构与复用

`servolab` 已按职责拆为独立子包：

```text
servolab/
├── config/       # 配置模型、序列化和旧单位迁移
├── control/      # PID、伺服控制和自定义控制器进程
├── plant/        # PMSM 与扰动模型
├── simulation/   # 指令、历史数据和仿真引擎
├── services/     # 仿真会话、实验读写、导出和代码生成
└── ui/           # PyQt5/pyqtgraph 桌面适配层
```

`config`、`control`、`plant`、`simulation` 和 `services` 均不依赖 PyQt5、pyqtgraph 或 `servolab.ui`。未来的 Web、CLI 或后台任务可以直接复用这些模块。例如：

```python
from servolab.config import ExperimentConfig
from servolab.services import SimulationSession

session = SimulationSession(ExperimentConfig())
history = session.run_offline(0.1)
```

`tests/test_architecture.py` 会持续检查项目 Python 文件不超过 500 行、函数不超过 100 行、核心层不反向依赖 UI，以及旧公共导入仍保持为薄兼容入口。

## 自定义控制器

在底部“自定义控制器”页签中打开独立编辑器。编辑器窗口可自由缩放，可打开或保存 `.py` 代码。代码生成器会读取主界面当前的控制方式、控制目标、PID 和电机参数，并可选生成参考前馈、反电动势补偿、dq 解耦、黏性摩擦补偿和抗积分饱和逻辑。按 `Ctrl+S` 可保存，按 `Ctrl+Enter` 可编译并启动当前代码。代码需要定义：

```python
def control(state, reference, params, dt):
    return {"vd": 0.0, "vq": 0.0}
```

也可以仅返回一个数值，此时它会作为 `vq`。`state` 提供 `id`、`iq`、`theta`、`omega`（rpm）、`torque` 和时间 `t`；`reference` 提供 `user_input` 原始用户输入、`command` 转换后的外环指令以及位置/速度（rpm）/电流内部目标；`params` 是一个可由脚本持续修改的字典。

自定义代码在独立进程中运行并限制单次响应时间，但它不是用于运行不可信代码的安全沙箱。
