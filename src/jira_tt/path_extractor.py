"""Extract recording paths from Jira ticket text."""
import re
from dataclasses import dataclass
from typing import Optional


_PATH_RE = re.compile(
    r"(/media/hotswap[12]/(?P<vehicle>[a-z]+-\d+)/\d{4}/\d{1,2}/\d{1,2}/[^\s\n]+)"
)

# Matches bare bag names like:
#   dev_kom-101_rockwell_haul_20260305_walter_call_to_load_1772733420
#   metrics_kom-101_rockwell_haul_20260305_peter_reduce_1772741277
#   perf-ver_rap-107_rockwell_haul_20260304_run1_1772662949
# The vehicle appears right after the prefix; the date is an embedded YYYYMMDD block.
_BARE_BAG_RE = re.compile(
    r"(?<!\w)([a-z][a-z0-9-]*_(?P<vehicle>[a-z]+-\d+)_[a-z0-9_]+?(?P<date>\d{8})[^\s\n]*)"
)

# Vehicle → /media/<mount> mapping.  Extend as new vehicles are added.
_VEHICLE_HOTSWAP: dict[str, str] = {
    "kom-101": "hotswap2",
    "rap-107": "hotswap1",
}


@dataclass
class RecordingPath:
    path: str
    vehicle: str


def _resolve_bare_bag(bag_name: str, vehicle: str, date_str: str) -> Optional[str]:
    """Build a full /media/hotswap… path from a bare bag name.

    Returns None if the vehicle isn't in the known mapping.
    """
    hotswap = _VEHICLE_HOTSWAP.get(vehicle)
    if hotswap is None:
        return None
    year = date_str[:4]
    month = str(int(date_str[4:6]))   # strip leading zero (3 not 03)
    day = str(int(date_str[6:8]))     # strip leading zero
    return f"/media/{hotswap}/{vehicle}/{year}/{month}/{day}/{bag_name}"


def extract_recording_paths(text: str) -> list[RecordingPath]:
    """Return deduplicated RecordingPath list from *text*, preserving first-occurrence order."""
    seen: set[str] = set()
    results: list[RecordingPath] = []

    def _add(path: str, vehicle: str) -> None:
        path = path.removesuffix("/logs")
        if path not in seen:
            seen.add(path)
            results.append(RecordingPath(path=path, vehicle=vehicle))

    # Full /media/hotswap… paths take priority.
    for m in _PATH_RE.finditer(text):
        _add(m.group(1), m.group("vehicle"))

    # Bare bag names — skipped if the resolved path was already captured above.
    for m in _BARE_BAG_RE.finditer(text):
        bag_name = m.group(1)
        vehicle = m.group("vehicle")
        date_str = m.group("date")
        full_path = _resolve_bare_bag(bag_name, vehicle, date_str)
        if full_path is not None:
            _add(full_path, vehicle)

    return results
