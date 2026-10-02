"""The candidate producer supplies this file; Forge evaluates a snapshot."""

import numpy as np
from numpy.typing import NDArray


def run(size: int) -> NDArray[np.float64]:
    return np.square(np.arange(size, dtype=np.float64))
