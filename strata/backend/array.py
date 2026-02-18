# strata/backend/array.py
# Thin abstraction: prefer CuPy for batch math, fall back to NumPy.
# Always use `xp` from this module rather than importing numpy/cupy directly.

try:
    import cupy as xp  # type: ignore[import]
    _BACKEND = "cupy"
except ImportError:
    import numpy as xp  # type: ignore[assignment]
    _BACKEND = "numpy"


def to_cpu(array):
    """Move an array to a plain NumPy array on CPU regardless of backend."""
    if _BACKEND == "cupy":
        return xp.asnumpy(array)
    return array


def backend_name() -> str:
    """Return the active backend name: 'cupy' or 'numpy'."""
    return _BACKEND


__all__ = ["xp", "to_cpu", "backend_name"]
