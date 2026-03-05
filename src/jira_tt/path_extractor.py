"""Extract recording paths from Jira ticket text."""
import re
from dataclasses import dataclass


_PATH_RE = re.compile(
    r"(/media/hotswap[12]/(?P<vehicle>[a-z]+-\d+)/\d{4}/\d{1,2}/\d{1,2}/[^\s\n]+)"
)


@dataclass
class RecordingPath:
    path: str
    vehicle: str


def extract_recording_paths(text: str) -> list[RecordingPath]:
    """Return deduplicated RecordingPath list from *text*, preserving first-occurrence order."""
    seen: set[str] = set()
    results: list[RecordingPath] = []
    for m in _PATH_RE.finditer(text):
        path = m.group(1).removesuffix("/logs")
        if path not in seen:
            seen.add(path)
            results.append(RecordingPath(path=path, vehicle=m.group("vehicle")))
    return results
