"""Extract recording paths from Jira ticket text."""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


_PATH_RE = re.compile(
    r"(/media/hotswap[12]/echelon/(?P<vehicle>[a-z]+-\d+)/(?P<year>\d{4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<bag>[^\s\n]+))"
)

# Matches bare bag names with an embedded YYYYMMDD date, e.g.:
#   dev_kom-101_rockwell_haul_20260305_walter_call_to_load_1772733420
#   metrics_kom-101_rockwell_haul_20260305_peter_reduce_1772741277
#   perf-ver_rap-107_rockwell_haul_20260304_run1_1772662949
_BARE_BAG_RE = re.compile(
    r"(?<!\w)([a-z][a-z0-9-]*_(?P<vehicle>[a-z]+-\d+)_[a-zA-Z0-9_-]+?(?P<date>20\d{6})[a-zA-Z0-9_-]*?(?:_(?P<ts>\d{10}))?)\b"
)

# Matches bare bag names with NO embedded YYYYMMDD date but a trailing Unix timestamp, e.g.:
#   dev_rap-107_rockwell_haul_peterr_test_lightweight_trajectories_run1_1773704023
# Bags that already have a 20XXXXXX date are handled by _BARE_BAG_RE and will be
# skipped via seen_basenames deduplication if this regex also matches them.
_BARE_BAG_TS_RE = re.compile(
    r"(?<!\w)([a-z][a-z0-9-]*_(?P<vehicle>[a-z]+-\d+)_[a-zA-Z0-9_-]*?(?<!\d)(?P<ts>\d{10}))\b"
)

_HOTSWAP_MOUNTS = ["hotswap1", "hotswap2"]


@dataclass
class RecordingPath:
    path: str        # canonical path (first candidate) — used for dedup/display/stamping
    vehicle: str
    candidates: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.candidates:
            self.candidates = [self.path]


def _date_candidates(bag_name: str, vehicle: str, anchor: datetime) -> list[str]:
    """Return candidate paths for anchor date ±1 day across all mounts.

    Trying a window around the anchor date makes path resolution robust against
    local-vs-UTC timezone differences regardless of when relative to midnight
    the recording was made.
    Candidates are ordered: anchor, anchor-1, anchor+1 — each across all mounts.
    """
    dates = [anchor, anchor - timedelta(days=1), anchor + timedelta(days=1)]
    seen: set[str] = set()
    candidates = []
    for dt in dates:
        for mount in _HOTSWAP_MOUNTS:
            p = f"/media/{mount}/echelon/{vehicle}/{dt.year}/{dt.month:02d}/{dt.day:02d}/{bag_name}"
            if p not in seen:
                seen.add(p)
                candidates.append(p)
    return candidates


def _candidates_from_date(bag_name: str, vehicle: str, date_str: str) -> list[str]:
    """Candidates anchored on an embedded YYYYMMDD date."""
    anchor = datetime(
        int(date_str[:4]),
        int(date_str[4:6]),
        int(date_str[6:8]),
        tzinfo=timezone.utc,
    )
    return _date_candidates(bag_name, vehicle, anchor)


def _candidates_from_ts(bag_name: str, vehicle: str, ts: str) -> list[str]:
    """Candidates anchored on a Unix timestamp (UTC)."""
    anchor = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return _date_candidates(bag_name, vehicle, anchor)


def extract_recording_paths(text: str) -> list[RecordingPath]:
    """Return deduplicated RecordingPath list from *text*, preserving first-occurrence order."""
    seen: set[str] = set()
    results: list[RecordingPath] = []

    def _add(path: str, vehicle: str, candidates: Optional[list[str]] = None) -> None:
        path = path.removesuffix("/traces")
        path = path.removesuffix("/logs")
        if candidates is None:
            candidates = [path]
        else:
            candidates = [c.removesuffix("/traces").removesuffix("/logs") for c in candidates]
        if path not in seen:
            seen.add(path)
            results.append(RecordingPath(path=path, vehicle=vehicle, candidates=candidates))

    # Full /media/hotswap… paths: normalise date padding and try both mounts.
    for m in _PATH_RE.finditer(text):
        vehicle = m.group("vehicle")
        year, month, day, bag = m.group("year"), m.group("month"), m.group("day"), m.group("bag")
        candidates = []
        for mount in _HOTSWAP_MOUNTS:
            p = f"/media/{mount}/echelon/{vehicle}/{year}/{int(month):02d}/{int(day):02d}/{bag}"
            if p not in candidates:
                candidates.append(p)
        _add(candidates[0], vehicle, candidates)

    # Basenames of all full paths already seen, for bare-bag deduplication below.
    seen_basenames = {p.rstrip("/").rsplit("/", 1)[-1] for p in seen}

    # Bare bag names — skipped if the bag name already appears as the basename of a full path.
    for m in _BARE_BAG_RE.finditer(text):
        bag_name = m.group(1)
        if bag_name in seen_basenames:
            continue
        vehicle = m.group("vehicle")
        ts = m.group("ts")
        # Prefer timestamp as anchor (more precise); fall back to embedded date.
        if ts:
            candidates = _candidates_from_ts(bag_name, vehicle, ts)
        else:
            candidates = _candidates_from_date(bag_name, vehicle, m.group("date"))
        _add(candidates[0], vehicle, candidates)

    # Bags with no embedded date but a trailing Unix timestamp.
    seen_basenames = {p.rstrip("/").rsplit("/", 1)[-1] for p in seen}
    for m in _BARE_BAG_TS_RE.finditer(text):
        bag_name = m.group(1)
        if bag_name in seen_basenames:
            continue
        vehicle = m.group("vehicle")
        candidates = _candidates_from_ts(bag_name, vehicle, m.group("ts"))
        _add(candidates[0], vehicle, candidates)

    return results
