"""Optional CUDA 12 implementation of the orbit RK4 candidate."""

import importlib
import importlib.util
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from numpy.typing import NDArray

from raddle.contracts import GPUProvenance, TimingScope

if TYPE_CHECKING:
    from raddle.orbit import PropagationInput


class BackendUnavailable(RuntimeError):
    """CuPy or a usable CUDA device is unavailable on this host."""


def load() -> Any:
    if importlib.util.find_spec("cupy") is None:
        raise BackendUnavailable("CuPy CUDA 12 extra is not installed")
    try:
        cupy = importlib.import_module("cupy")
    except (ImportError, OSError) as error:
        raise BackendUnavailable("CuPy installation cannot load") from error
    try:
        if cupy.cuda.runtime.getDeviceCount() < 1:
            raise BackendUnavailable("no CUDA device is available")
    except cupy.cuda.runtime.CUDARuntimeError as error:
        raise BackendUnavailable("CUDA device or driver is unavailable") from error
    return cupy


def availability() -> tuple[bool, str]:
    try:
        load()
    except BackendUnavailable as error:
        return False, str(error)
    return True, "available on this host"


def provenance(cupy: Any) -> GPUProvenance:
    device = cupy.cuda.runtime.getDevice()
    name = cupy.cuda.runtime.getDeviceProperties(device)["name"]
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    return GPUProvenance(
        model=str(name),
        gpu_count_used=1,
        cuda_runtime_version=int(cupy.cuda.runtime.runtimeGetVersion()),
        cuda_driver_version=int(cupy.cuda.runtime.driverGetVersion()),
        cupy_version=str(cupy.__version__),
    )


def propagate_device(
    device_input: Any,
    mu: float,
    dt: float,
    steps: int,
    cupy: Any,
    check_finite: bool = True,
) -> Any:
    """RK4 stages on device arrays; only the final validity check synchronizes."""

    def derivative(states: Any) -> Any:
        position = states[:, :3]
        radius_squared = cupy.sum(position * position, axis=1)
        scale = -mu / (radius_squared * cupy.sqrt(radius_squared))
        return cupy.concatenate((states[:, 3:], position * scale[:, None]), axis=1)

    states = cupy.array(device_input, dtype=cupy.float64, copy=True)
    for _ in range(steps):
        k1 = derivative(states)
        k2 = derivative(states + dt * k1 / 2)
        k3 = derivative(states + dt * k2 / 2)
        k4 = derivative(states + dt * k3)
        states += dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
    if check_finite and not bool(cupy.isfinite(states).all()):
        raise ValueError("integration produced a singular or non-finite state")
    return states


def accelerated(
    inputs: "PropagationInput", cupy: Any | None = None
) -> NDArray[np.float64]:
    cupy = load() if cupy is None else cupy
    device_input = cupy.asarray(inputs.initial_states, dtype=cupy.float64)
    output = propagate_device(device_input, inputs.mu, inputs.dt, inputs.steps, cupy)
    return cast(NDArray[np.float64], cupy.asnumpy(output))


def prepare_benchmark(
    inputs: "PropagationInput", scope: TimingScope, cupy: Any
) -> tuple[Callable[[], object], Callable[[], None]]:
    stream = cupy.cuda.get_current_stream()
    synchronize: Callable[[], None] = stream.synchronize
    if scope == TimingScope.COMPUTE_ONLY:
        device_input = cupy.asarray(inputs.initial_states, dtype=cupy.float64)
        synchronize()

        def run_compute() -> object:
            return propagate_device(
                device_input,
                inputs.mu,
                inputs.dt,
                inputs.steps,
                cupy,
                check_finite=False,
            )

        return run_compute, synchronize

    def run_end_to_end() -> object:
        device_input = cupy.asarray(inputs.initial_states, dtype=cupy.float64)
        output = propagate_device(
            device_input, inputs.mu, inputs.dt, inputs.steps, cupy
        )
        return cupy.asnumpy(output)

    return run_end_to_end, synchronize
