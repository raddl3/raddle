"""Explicit product accelerator registry; fixtures are never registered."""

from collections.abc import Callable
from dataclasses import dataclass

from raddle import orbit
from raddle.contracts import (
    AcceleratorDescriptor,
    BenchmarkReceipt,
    TimingScope,
    ValidationReceipt,
)


@dataclass(frozen=True)
class RegisteredAccelerator:
    descriptor: AcceleratorDescriptor
    verify: Callable[[str, str], ValidationReceipt]
    benchmark: Callable[[str, int, int, str, TimingScope, str], BenchmarkReceipt]
    availability: Callable[[str], tuple[bool, str]]


_PRODUCTS = {
    orbit.DESCRIPTOR.id: RegisteredAccelerator(
        orbit.DESCRIPTOR, orbit.verify, orbit.benchmark, orbit.availability
    )
}


def list_accelerators() -> tuple[AcceleratorDescriptor, ...]:
    return tuple(item.descriptor for item in _PRODUCTS.values())


def get_accelerator(accelerator_id: str) -> RegisteredAccelerator:
    return _PRODUCTS[accelerator_id]
