"""Extract recording paths from Jira ticket text."""
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


_PATH_RE = re.compile(
    r"(/media/hotswap[12]/(?P<vehicle>[a-z]+-\d+)/\d{4}/\d{1,2}/\d{1,2}/[^\s\n]+)"
)

# Matches bare bag names with an embedded YYYYMMDD date, e.g.:
#   dev_kom-101_rockwell_haul_20260305_walter_call_to_load_1772733420
#   metrics_kom-101_rockwell_haul_20260305_peter_reduce_1772741277
#   perf-ver_rap-107_rockwell_haul_20260304_run1_1772662949
_BARE_BAG_RE = re.compile(
    r"(?<!\w)([a-z][a-z0-9-]*_(?P<vehicle>[a-z]+-\d+)_[a-z0-9_]+?(?P<date>20\d{6})[^\s\n]*)"
)

# Matches bare bag names with NO embedded YYYYMMDD date but a trailing Unix timestamp, e.g.:
#   dev_rap-107_rockwell_haul_peterr_test_lightweight_trajectories_run1_1773704023
# Bags that already have a 20XXXXXX date are handled by _BARE_BAG_RE and will be
# skipped via seen_basenames deduplication if this regex also matches them.
_BARE_BAG_TS_RE = re.compile(
    r"(?<!\w)([a-z][a-z0-9-]*_(?P<vehicle>[a-z]+-\d+)_[a-z0-9_]*?(?<!\d)(?P<ts>\d{10}))\b"
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


def _resolve_bare_bag_ts(bag_name: str, vehicle: str, ts: str) -> Optional[str]:
    """Like _resolve_bare_bag but derives the date from a Unix timestamp suffix."""
    hotswap = _VEHICLE_HOTSWAP.get(vehicle)
    if hotswap is None:
        return None
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return f"/media/{hotswap}/{vehicle}/{dt.year}/{dt.month}/{dt.day}/{bag_name}"


def extract_recording_paths(text: str) -> list[RecordingPath]:
    """Return deduplicated RecordingPath list from *text*, preserving first-occurrence order."""
    seen: set[str] = set()
    results: list[RecordingPath] = []

    def _add(path: str, vehicle: str) -> None:
        path = path.removesuffix("/traces")
        path = path.removesuffix("/logs")
        if path not in seen:
            seen.add(path)
            results.append(RecordingPath(path=path, vehicle=vehicle))

    # Full /media/hotswap… paths take priority.
    for m in _PATH_RE.finditer(text):
        _add(m.group(1), m.group("vehicle"))

    # Basenames of all full paths already seen, for bare-bag deduplication below.
    seen_basenames = {p.rstrip("/").rsplit("/", 1)[-1] for p in seen}

    # Bare bag names — skipped if the resolved path was already captured above,
    # OR if the bag name already appears as the basename of a full path (handles
    # the case where the full path date-directory differs from the embedded date).
    for m in _BARE_BAG_RE.finditer(text):
        bag_name = m.group(1)
        if bag_name in seen_basenames:
            continue
        vehicle = m.group("vehicle")
        date_str = m.group("date")
        full_path = _resolve_bare_bag(bag_name, vehicle, date_str)
        if full_path is not None:
            _add(full_path, vehicle)

    # Bags with no embedded date but a trailing Unix timestamp.
    seen_basenames = {p.rstrip("/").rsplit("/", 1)[-1] for p in seen}
    for m in _BARE_BAG_TS_RE.finditer(text):
        bag_name = m.group(1)
        if bag_name in seen_basenames:
            continue
        vehicle = m.group("vehicle")
        full_path = _resolve_bare_bag_ts(bag_name, vehicle, m.group("ts"))
        if full_path is not None:
            _add(full_path, vehicle)

    return results
