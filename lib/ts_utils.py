"""Pure stdlib transformation helpers for fertilizer dataset engineering."""


def month_index(date_str):
    """'YYYY-MM-DD' -> integer count of months since year 0 (month-aligned)."""
    year, month, _day = date_str.split("-")
    return int(year) * 12 + (int(month) - 1)


def index_to_month(idx):
    """Inverse of month_index -> 'YYYY-MM-01'."""
    year, month0 = divmod(idx, 12)
    return f"{year:04d}-{month0 + 1:02d}-01"


def mean(values):
    values = list(values)
    return sum(values) / len(values)


def median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def percentile(values, p):
    """Nearest-rank percentile. p in [0, 100]. Raises ValueError on empty input."""
    s = sorted(values)
    if not s:
        raise ValueError("percentile() of empty sequence")
    if len(s) == 1:
        return s[0]
    k = (p / 100.0) * len(s)
    rank = int(k)
    if rank < k:  # ceil without math module
        rank += 1
    rank = max(1, min(rank, len(s)))
    return s[rank - 1]
