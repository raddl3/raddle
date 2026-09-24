"""Explicit product accelerator registry; fixtures are never registered."""

from collections.abc import Callable
from dataclasses import dataclass

from raddle import orbit
from raddle.contracts import AcceleratorDescriptor, BenchmarkReceipt, ValidationReceipt


@dataclass(frozen=True)
class RegisteredAccelerator:
    descriptor: AcceleratorDescriptor
    verify: Callable[[str], ValidationReceipt]
    benchmark: Callable[[str, int, int], BenchmarkReceipt]


_PRODUCTS = {
    orbit.DESCRIPTOR.id: RegisteredAccelerator(
        orbit.DESCRIPTOR, orbit.verify, orbit.benchmark
    )
}


def list_accelerators() -> tuple[AcceleratorDescriptor, ...]:
    return tuple(item.descriptor for item in _PRODUCTS.values())


def get_accelerator(accelerator_id: str) -> RegisteredAccelerator:
    return _PRODUCTS[accelerator_id]
