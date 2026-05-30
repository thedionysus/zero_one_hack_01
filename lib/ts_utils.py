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


def detect_gaps(dates):
    """Return month-aligned 'YYYY-MM-01' strings missing between min and max."""
    if not dates:
        return []
    idxs = sorted(month_index(d) for d in dates)
    present = set(idxs)
    return [index_to_month(i) for i in range(idxs[0], idxs[-1] + 1) if i not in present]


def linear_interpolate_gap(series, missing_date):
    """Linear value at missing_date from nearest present neighbours on each side.

    series: {'YYYY-MM-DD': float}. missing_date must lie strictly between an
    earlier and a later present key.
    """
    target = month_index(missing_date)
    before = [(month_index(d), v) for d, v in series.items() if month_index(d) < target]
    after = [(month_index(d), v) for d, v in series.items() if month_index(d) > target]
    if not before or not after:
        raise ValueError(f"cannot interpolate {missing_date}: missing a side neighbour")
    pi, pv = max(before)
    ni, nv = min(after)
    frac = (target - pi) / (ni - pi)
    return pv + (nv - pv) * frac
