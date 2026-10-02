"""Small external integration: preserve scalar NumPy square semantics."""

import numpy as np
from numpy.typing import NDArray


def reference(size: int) -> NDArray[np.float64]:
    return np.array([np.square(float(i)) for i in range(size)], dtype=np.float64)
