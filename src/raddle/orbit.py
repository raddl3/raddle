"""Batched point-mass two-body propagation with independent RK4 paths."""

import math
import statistics
import time
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from raddle.contracts import (
    AcceleratorDescriptor,
    BenchmarkReceipt,
    CaseDescriptor,
    ExecutionProvenance,
    ImplementationIdentity,
    ValidationPolicy,
    ValidationReceipt,
)

StateBatch = NDArray[np.float64]


@dataclass(frozen=True)
class PropagationInput:
    initial_states: ArrayLike
    mu: float
    dt: float
    steps: int

    def __post_init__(self) -> None:
        try:
            states = np.array(self.initial_states, dtype=np.float64, copy=True)
        except (TypeError, ValueError) as error:
            raise ValueError("initial_states must contain float64 values") from error
        if states.ndim != 2 or states.shape[0] < 1 or states.shape[1] != 6:
            raise ValueError("initial_states must have shape (batch >= 1, 6)")
        if not np.isfinite(states).all():
            raise ValueError("initial_states must be finite")
        if np.any(np.linalg.norm(states[:, :3], axis=1) == 0):
            raise ValueError("initial_states must have nonzero radius")
        if not math.isfinite(self.mu) or self.mu <= 0:
            raise ValueError("mu must be finite and positive")
        if not math.isfinite(self.dt) or self.dt <= 0:
            raise ValueError("dt must be finite and positive")
        if type(self.steps) is not int or self.steps <= 0:
            raise ValueError("steps must be a positive integer")
        states.flags.writeable = False
        object.__setattr__(self, "initial_states", states)


POLICY = ValidationPolicy(
    id="float64.state_elementwise.v1",
    absolute_tolerance=1e-11,
    relative_tolerance=1e-10,
)
DESCRIPTOR = AcceleratorDescriptor(
    id="orbit.two_body_rk4",
    version="0.1.0",
    name="Batched two-body propagation",
    reference=ImplementationIdentity("python.scalar", "1"),
    candidate=ImplementationIdentity("numpy.vectorized", "1"),
    input_contract=(
        "Finite float64 (batch >= 1, 6) Cartesian states; "
        "positive mu, dt, steps in consistent units"
    ),
    output_contract=(
        "Finite float64 (batch, 6) final Cartesian states after exactly steps RK4 steps"
    ),
    precision="float64",
    supported_environment="CPython >=3.12, NumPy >=2,<3, CPU",
    validation_policy=POLICY,
    cases=(
        CaseDescriptor("circular.small", 4, 1.0, math.tau / 256, 256),
        CaseDescriptor("batch.standard", 256, 1.0, 0.01, 128),
    ),
)


def case(case_id: str) -> PropagationInput:
    definition = next((item for item in DESCRIPTOR.cases if item.id == case_id), None)
    if definition is None:
        raise KeyError(case_id)
    states = np.empty((definition.trajectories, 6), dtype=np.float64)
    for index in range(definition.trajectories):
        phase = math.tau * index / definition.trajectories
        radius = 1.0 + 0.1 * (index % 7)
        speed = math.sqrt(definition.mu / radius)
        states[index] = (
            radius * math.cos(phase),
            radius * math.sin(phase),
            0.0,
            -speed * math.sin(phase),
            speed * math.cos(phase),
            0.0,
        )
    return PropagationInput(states, definition.mu, definition.dt, definition.steps)


def reference(inputs: PropagationInput) -> StateBatch:
    """Legible scalar RK4, one trajectory at a time."""

    def derivative(state: list[float]) -> list[float]:
        x, y, z, vx, vy, vz = state
        radius = math.sqrt(x * x + y * y + z * z)
        if radius == 0 or not math.isfinite(radius):
            raise ValueError("integration reached singular or non-finite radius")
        scale = -inputs.mu / (radius * radius * radius)
        return [vx, vy, vz, scale * x, scale * y, scale * z]

    result: list[list[float]] = []
    for row in np.asarray(inputs.initial_states):
        state = [float(value) for value in row]
        for _ in range(inputs.steps):
            k1 = derivative(state)
            k2 = derivative(
                [
                    value + inputs.dt * slope / 2
                    for value, slope in zip(state, k1, strict=True)
                ]
            )
            k3 = derivative(
                [
                    value + inputs.dt * slope / 2
                    for value, slope in zip(state, k2, strict=True)
                ]
            )
            k4 = derivative(
                [
                    value + inputs.dt * slope
                    for value, slope in zip(state, k3, strict=True)
                ]
            )
            state = [
                value + inputs.dt * (a + 2 * b + 2 * c + d) / 6
                for value, a, b, c, d in zip(state, k1, k2, k3, k4, strict=True)
            ]
            if not all(map(math.isfinite, state)):
                raise ValueError("integration produced a non-finite state")
        result.append(state)
    return np.asarray(result, dtype=np.float64)


def accelerated(inputs: PropagationInput) -> StateBatch:
    """The same RK4 stages, vectorized across independent trajectories."""

    def derivative(states: StateBatch) -> StateBatch:
        position = states[:, :3]
        radius_squared = np.sum(position * position, axis=1)
        if np.any(radius_squared == 0) or not np.isfinite(radius_squared).all():
            raise ValueError("integration reached singular or non-finite radius")
        scale = -inputs.mu / (radius_squared * np.sqrt(radius_squared))
        return np.concatenate((states[:, 3:], position * scale[:, None]), axis=1)

    states = np.array(inputs.initial_states, dtype=np.float64, copy=True)
    for _ in range(inputs.steps):
        k1 = derivative(states)
        k2 = derivative(states + inputs.dt * k1 / 2)
        k3 = derivative(states + inputs.dt * k2 / 2)
        k4 = derivative(states + inputs.dt * k3)
        states += inputs.dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        if not np.isfinite(states).all():
            raise ValueError("integration produced a non-finite state")
    return states


def validate(
    case_id: str, expected: StateBatch, actual: StateBatch
) -> ValidationReceipt:
    if expected.shape != actual.shape or not np.isfinite(actual).all():
        raise ValueError("candidate output must be finite and match reference shape")
    difference = np.abs(expected - actual)
    threshold = POLICY.absolute_tolerance + POLICY.relative_tolerance * np.abs(expected)
    relative_region = np.abs(expected) >= (
        POLICY.absolute_tolerance / POLICY.relative_tolerance
    )
    max_relative_error = (
        float(np.max(difference[relative_region] / np.abs(expected[relative_region])))
        if np.any(relative_region)
        else 0.0
    )
    return ValidationReceipt(
        schema_version=1,
        accelerator_id=DESCRIPTOR.id,
        accelerator_version=DESCRIPTOR.version,
        case_id=case_id,
        reference=DESCRIPTOR.reference,
        candidate=DESCRIPTOR.candidate,
        precision=DESCRIPTOR.precision,
        policy=POLICY,
        status="matched" if np.all(difference <= threshold) else "mismatched",
        compared_values=int(difference.size),
        max_absolute_error=float(np.max(difference)),
        max_relative_error=max_relative_error,
        provenance=ExecutionProvenance.current(),
    )


def verify(case_id: str) -> ValidationReceipt:
    inputs = case(case_id)
    return validate(case_id, reference(inputs), accelerated(inputs))


def benchmark(case_id: str, repeat: int, warmup: int = 1) -> BenchmarkReceipt:
    if type(repeat) is not int or repeat <= 0:
        raise ValueError("repeat must be a positive integer")
    if type(warmup) is not int or warmup < 0:
        raise ValueError("warmup must be a nonnegative integer")
    inputs = case(case_id)
    validation = validate(case_id, reference(inputs), accelerated(inputs))
    if validation.status != "matched":
        raise ValueError("benchmark validation failed")
    for _ in range(warmup):
        reference(inputs)
        accelerated(inputs)
    reference_times: list[int] = []
    candidate_times: list[int] = []
    for _ in range(repeat):
        start = time.perf_counter_ns()
        reference(inputs)
        reference_times.append(time.perf_counter_ns() - start)
        start = time.perf_counter_ns()
        accelerated(inputs)
        candidate_times.append(time.perf_counter_ns() - start)
    median_reference = statistics.median(reference_times)
    median_candidate = statistics.median(candidate_times)
    return BenchmarkReceipt(
        schema_version=1,
        accelerator_id=DESCRIPTOR.id,
        accelerator_version=DESCRIPTOR.version,
        case_id=case_id,
        validation=validation,
        clock="perf_counter_ns",
        warmup=warmup,
        repeat=repeat,
        reference_times_ns=tuple(reference_times),
        candidate_times_ns=tuple(candidate_times),
        median_reference_ns=median_reference,
        median_candidate_ns=median_candidate,
        speedup=median_reference / median_candidate,
        provenance=ExecutionProvenance.current(),
    )
