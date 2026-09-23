"""Non-product fixture. These two paths make no performance claim."""

import platform

from raddle.contracts import AcceleratorDescriptor, ValidationReceipt

DESCRIPTOR = AcceleratorDescriptor(
    id="fixture.sum_squares",
    version="0.1.0",
    reference="python_loop_v1",
    accelerated="python_sum_v1",
    input_contract="tuple[int, ...]",
    output_contract="int",
    validation="exact integer equality",
    benchmark_case="fixture.small.v1",
    supported_environment="CPython >=3.12",
)
CASE: tuple[int, ...] = (1, 2, 3, 4)


def reference(values: tuple[int, ...]) -> int:
    result = 0
    for value in values:
        result += value * value
    return result


def accelerated(values: tuple[int, ...]) -> int:
    return sum(value * value for value in values)


def verify() -> ValidationReceipt:
    expected = reference(CASE)
    actual = accelerated(CASE)
    return ValidationReceipt(
        schema_version=1,
        accelerator_id=DESCRIPTOR.id,
        accelerator_version=DESCRIPTOR.version,
        case_id=DESCRIPTOR.benchmark_case,
        reference=DESCRIPTOR.reference,
        accelerated=DESCRIPTOR.accelerated,
        runtime="CPython",
        runtime_version=platform.python_version(),
        reference_result=expected,
        accelerated_result=actual,
        validation="matched" if expected == actual else "mismatched",
    )
