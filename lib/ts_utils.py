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
    if not values:
        raise ValueError("mean() of empty sequence")
    return sum(values) / len(values)


def median(values):
    s = sorted(values)
    if not s:
        raise ValueError("median() of empty sequence")
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def percentile(values, p):
    """Nearest-rank percentile. p in [0, 100]. Raises ValueError on empty input."""
    if not (0 <= p <= 100):
        raise ValueError("percentile p must be in [0, 100]")
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


def flag_low_price(price, floor=0.10):
    """True when price is below the implausible-low floor (USD/kg PPP)."""
    price = float(price)
    if price != price:  # NaN self-inequality idiom
        return True
    return price < floor


def collapse_duplicate_towns(rows):
    """Collapse duplicate (ISO, year, Town) rows by averaging price.

    rows: list of dict (csv.DictReader rows) with str 'price_usd_per_kg_ppp'.
    Returns (collapsed_rows, collapsed_keys) where collapsed_keys lists the
    (ISO, year, Town) tuples that had >1 source row. Output preserves first-seen
    order; the averaged price is written back as a string.

    For duplicate (ISO, year, Town) rows, non-price fields are taken from the
    first row (duplicate towns share identical geo by design); only the price
    is averaged.
    """
    groups = {}
    order = []
    for r in rows:
        key = (r["ISO"], r["year"], r["Town"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    collapsed = []
    collapsed_keys = []
    for key in order:
        members = groups[key]
        base = dict(members[0])
        if len(members) > 1:
            avg = mean(float(m["price_usd_per_kg_ppp"]) for m in members)
            base["price_usd_per_kg_ppp"] = f"{avg:.6g}"
            collapsed_keys.append(key)
        collapsed.append(base)
    return collapsed, collapsed_keys


def detect_flat_tail(series, min_run=4):
    """Length of the trailing run of identical values if >= min_run, else 0."""
    ordered = sorted(series.items(), key=lambda kv: month_index(kv[0]))
    if not ordered:
        return 0
    last = ordered[-1][1]
    run = 0
    for _date, v in reversed(ordered):
        if v == last:
            run += 1
        else:
            break
    return run if run >= min_run else 0


def detect_outlier_jumps(series, floor_pct=40.0):
    """Flag dates whose |month-over-month %| exceeds max(floor_pct, p99 of history).

    series: {'YYYY-MM-DD': float}. Returns sorted list of flagged date keys.

    A month whose previous value is 0 is skipped (no MoM % can be computed).
    On small series the adaptive p99 threshold can mask a secondary outlier
    that falls below the largest jump.
    """
    ordered = sorted(series.items(), key=lambda kv: month_index(kv[0]))
    moms = []  # (date, abs_pct)
    for i in range(1, len(ordered)):
        prev_v = ordered[i - 1][1]
        if prev_v == 0:
            continue
        pct = abs((ordered[i][1] / prev_v - 1.0) * 100.0)
        moms.append((ordered[i][0], pct))
    if not moms:
        return []
    p99 = percentile([m[1] for m in moms], 99)
    threshold = max(floor_pct, p99)
    return sorted(d for d, pct in moms if pct >= threshold)


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
    earlier and a later present key. All keys (including missing_date) must be
    first-of-month strings in 'YYYY-MM-01' format.
    """
    if not missing_date.endswith("-01"):
        raise ValueError("missing_date must be month-aligned 'YYYY-MM-01'")
    target = month_index(missing_date)
    before = [(month_index(d), v) for d, v in series.items() if month_index(d) < target]
    after = [(month_index(d), v) for d, v in series.items() if month_index(d) > target]
    if not before or not after:
        raise ValueError(f"cannot interpolate {missing_date}: missing a side neighbour")
    pi, pv = max(before)
    ni, nv = min(after)
    frac = (target - pi) / (ni - pi)
    return pv + (nv - pv) * frac
