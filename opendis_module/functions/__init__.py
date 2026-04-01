"""Istari functions offered by the opendis module. Uses explicit imports (no pkgutil auto-discovery)."""

# Explicit imports to register all functions
from opendis_module.functions import (  # noqa: F401
    analyze_scenario,
    convert_dis_to_json,
    extract_entity_states,
    parse_dis_stream,
    validate_dis_stream,
)
from opendis_module.functions.registry import FUNCTIONS

__all__ = ["FUNCTIONS"]
