"""Convert duration_ns to a human-readable minutes string."""


def format_minutes(duration_ns: int) -> tuple:
    """Return (formatted_minutes_string, total_seconds).

    Thresholds:
      < 1,000       → "2.00 minutes"
      1,000–999,999 → "12.34K minutes"
      ≥ 1,000,000   → "29.54M minutes"
    """
    minutes = duration_ns / (60 * 1_000_000_000)

    if minutes < 1_000:
        label = f"{minutes:.2f} minutes"
    elif minutes < 1_000_000:
        label = f"{minutes / 1_000:.2f}K minutes"
    else:
        label = f"{minutes / 1_000_000:.2f}M minutes"

    seconds = round(minutes * 60)
    return label, seconds
