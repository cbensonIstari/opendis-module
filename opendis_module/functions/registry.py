"""Simple function registry for Istari functions."""

from typing import Callable, Dict

from opendis_module.functions.base.function_io import Output

FunctionType = Callable[[str, str], list[Output]]

FUNCTIONS: Dict[str, FunctionType] = {}


def register(name: str, func: FunctionType) -> None:
    """Register a function with the given name."""
    FUNCTIONS[name] = func


def get_function(name: str) -> FunctionType:
    """Get a function by name."""
    if name not in FUNCTIONS:
        raise ValueError(f'Function "{name}" is not registered.')
    return FUNCTIONS[name]
