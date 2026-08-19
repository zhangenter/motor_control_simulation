"""Configuration models, topology rules, and persistence helpers."""

from .models import (
    CommandConfig,
    ControlConfig,
    DisturbanceConfig,
    EncoderConfig,
    ExperimentConfig,
    FeedbackConfig,
    MotorConfig,
    PIDConfig,
    SimulationConfig,
    SpeedEstimatorConfig,
    SpeedEstimatorMethod,
)
from .serialization import (
    experiment_from_dict,
    experiment_to_dict,
    load_experiment,
    save_experiment,
)
from .topology import (
    CommandType,
    CurrentAxis,
    LoopMode,
    POSITION_OUTER_MODES,
    ReferenceType,
    allowed_reference_types,
    default_reference_type,
    has_position_outer_loop,
)

__all__ = [
    "CommandConfig",
    "CommandType",
    "CurrentAxis",
    "ControlConfig",
    "DisturbanceConfig",
    "EncoderConfig",
    "ExperimentConfig",
    "FeedbackConfig",
    "LoopMode",
    "MotorConfig",
    "PIDConfig",
    "POSITION_OUTER_MODES",
    "ReferenceType",
    "SimulationConfig",
    "SpeedEstimatorConfig",
    "SpeedEstimatorMethod",
    "allowed_reference_types",
    "default_reference_type",
    "experiment_from_dict",
    "experiment_to_dict",
    "has_position_outer_loop",
    "load_experiment",
    "save_experiment",
]
