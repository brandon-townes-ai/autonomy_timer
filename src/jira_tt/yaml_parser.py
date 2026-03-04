"""YAML file discovery and duration_ns extraction."""
from pathlib import Path

import yaml


def find_yaml_file(directory: str) -> Path:
    """Return the most recently modified YAML file in *directory*."""
    d = Path(directory)
    if not d.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    candidates = list(d.glob("*.yaml")) + list(d.glob("*.yml"))
    if not candidates:
        raise FileNotFoundError(f"No YAML files found in {directory}")

    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_value(yaml_path: Path, key: str) -> int:
    """Load *yaml_path* and return the numeric value at *key*."""
    with open(yaml_path, "r") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping at the top level of {yaml_path}")

    if key not in data:
        raise KeyError(f"Key '{key}' not found in {yaml_path}. Available keys: {list(data.keys())}")

    value = data[key]
    if not isinstance(value, (int, float)):
        raise TypeError(f"Key '{key}' must be numeric, got {type(value).__name__}: {value!r}")

    return int(value)
