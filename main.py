"""Forecast GTA VI's launch-day Twitch viewers, hour by hour (quantiles).

Entry for make.fun competition gta6-twitch-ccu-forecast-01.

The program reads one case per file from the input directory
(/input/<id>.in, or $MAKEFUN_INPUT_DIR) and writes one forecast per case to
the output directory (/output/<id>.out, or $MAKEFUN_OUTPUT_DIR).

A case gives everything known up to the end of release day's first hour:
hour 1's print (the mean concurrent viewers in the Twitch category during
00:00-01:00 UTC), plus the full hourly curves of 42 past big game launches
("comparables", from SullyGnome's hourly Twitch category averages, 14 days
before each launch to 3 days after it). The forecast is five quantiles
(5%, 25%, 50%, 75%, 95%) of the viewer count for each of hours 2..24.

Method (see STRATEGY.md for the validation)
--------------------------------------------
Work in log space. For a past launch, define the log-ratio curve

    L_h = ln(viewers_h / viewers_1),   h = 2..24,

the shape of release day relative to its first hour. The shape depends
strongly on how big hour 1 already is: launches whose hour 1 is huge have
already captured the global audience, so their day stays flat or dips and
only recovers to about hour 1's level in the evening (peak / hour-1 is
~1.0-1.3 for the biggest launches); launches with a small hour 1 grow
several-fold as regions unlock through the day (correlation between
ln(hour-1) and L_h reaches about -0.89 by hour 20). A plain linear fit of
L_h on ln(hour-1) extrapolates badly at GTA VI scale (it would predict an
evening collapse to ~0.2x hour 1), so the forecast blends two estimators
that both respect that saturation:

  A. Kernel-weighted quantiles. For each hour, the quantiles of L_h across
     past launches, weighted by a Gaussian kernel on the distance between
     ln(hour-1) of the past launch and ln(hour-1) of this case
     (bandwidth 1.0 in log units), so the forecast is anchored on launches
     of a similar size. Launches flagged early-access-contaminated or weak
     in the case data count half.
  B. Rolling-launch regression. An ordinary least squares fit of L_h on
     ln(hour-1), fitted only on "rolling" launches (peak / hour-1 <= 6,
     the midnight-local rolling unlocks like GTA VI's), with quantiles from
     the empirical quantiles of its residuals.

The two are blended 50/50 in log space and the spread around the median
is widened by a factor of 1.1, which brings the 90% band's empirical
coverage to ~0.90 in leave-one-out validation.

Validation (leave-one-out over 41 past launches; 4 practice cases scored
against SullyGnome's actual release-day counts):
  - big rolling launches (hour-1 >= 100k, n=19): pinball 0.209 vs house
    baseline 0.262; typical median miss ~40% vs baseline ~56%.
  - practice cases p00-p03: pinball 0.230 vs house baseline 0.387.
  - all 41 launches: pinball 0.47 vs baseline 0.88.

The program is deterministic (no randomness, no clock, no network) and
uses only the Python standard library, so two runs are byte-identical.
If the comparables are too thin to fit either component, that component
falls back to the house baseline's persistence shape; if both fail, the
whole forecast is the baseline shape.
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import. (This entry is a single file.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

DEFAULT_LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles at the default levels (only used by the
# persistence fallback).
Z_FALLBACK = [-1.645, -0.674, 0.0, 0.674, 1.645]
FALLBACK_SIGMA = 0.15

# Model constants, tuned by leave-one-out validation on the comparables.
KERNEL_BANDWIDTH = 1.0    # log units of hour-1 viewers
BLEND_KERNEL = 0.5        # weight of the kernel component in log space
SPREAD_WIDEN = 1.1        # spread widening around the median
ROLLING_MAX_PEAK_RATIO = 6.0  # peak / hour-1 at most this: rolling unlock
TIER_WEIGHTS = {"comparable": 1.0, "early-access-contaminated": 0.5, "weak": 0.5}
MIN_POOL = 3              # launches needed before a component is trusted


def interp_quantile(sorted_values, p):
    """Linear-interpolation quantile of a sorted list (type 7)."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("quantile of empty list")
    if n == 1:
        return sorted_values[0]
    pos = p * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def weighted_quantile(pairs, p):
    """Weighted quantile of [(value, weight)] with linear interpolation."""
    ordered = sorted(pairs, key=lambda vw: vw[0])
    total = sum(w for _, w in ordered)
    if total <= 0:
        return ordered[len(ordered) // 2][0]
    threshold = p * total
    seen = 0.0
    for i, (value, weight) in enumerate(ordered):
        before = seen
        seen += weight
        if seen >= threshold:
            if i == 0 or weight <= 0:
                return value
            frac = (threshold - before) / weight
            return ordered[i - 1][0] * (1.0 - frac) + value * frac
    return ordered[-1][0]


def ols(xs, ys):
    """Least-squares fit y ~ a + b*x; returns (a, b)."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx > 0 else 0.0
    return my - b * mx, b


def round_half_up_2(x):
    """Round to 2 decimals, half up; whole numbers come back as int."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100.0
    return int(value) if float(value).is_integer() else value


def parse_hourly(rows, day_start):
    """Release-day hours 1..24 -> viewers, from a comparable's hourly rows.

    A row's hour is its offset from the release day's start, computed from
    the full timestamps (all UTC), so rows are placed correctly even if a
    comparable's window straddles a date boundary.
    """
    from datetime import datetime

    def parse_time(text):
        return datetime.fromisoformat(text.replace("Z", "+00:00"))

    start = parse_time(day_start)
    hours = {}
    for row in rows:
        try:
            at = parse_time(row["from"])
            viewers = float(row["viewers"])
        except (KeyError, TypeError, ValueError):
            continue
        if viewers <= 0:
            continue
        offset = (at - start).total_seconds()
        hour = int(offset // 3600) + 1
        if 1 <= hour <= 24:
            hours[hour] = viewers
    return hours


def launch_tier(unlock_text):
    """Tier weight class from the comparable's unlock note."""
    text = unlock_text or ""
    if "early-access-contaminated" in text:
        return "early-access-contaminated"
    if "Tier: weak" in text:
        return "weak"
    return "comparable"


def collect_launches(case):
    """Usable past launches: {log_h1, weight, tier, curve, rolling}."""
    launches = []
    for comp in case.get("comparables") or []:
        day_start = comp.get("day_start", "")
        hours = parse_hourly(comp.get("hourly") or [], day_start)
        if 1 not in hours or len(hours) < 24:
            continue
        h1 = hours[1]
        peak = max(hours.values())
        tier = launch_tier(comp.get("unlock", ""))
        launches.append(
            {
                "log_h1": math.log(h1),
                "weight": TIER_WEIGHTS[tier],
                "tier": tier,
                "curve": hours,
                "rolling": peak / h1 <= ROLLING_MAX_PEAK_RATIO,
            }
        )
    return launches


def kernel_component(launches, log_p1, levels):
    """Per-hour weighted quantiles of log-ratios, kernel on ln(hour-1)."""
    if len(launches) < MIN_POOL:
        return None
    out = {}
    for h in range(2, 25):
        pairs = []
        for launch in launches:
            curve = launch["curve"]
            if h not in curve:
                continue
            dist = (launch["log_h1"] - log_p1) / KERNEL_BANDWIDTH
            w = math.exp(-0.5 * dist * dist) * launch["weight"]
            if w > 0:
                pairs.append((math.log(curve[h] / curve[1]), w))
        if len(pairs) < MIN_POOL:
            return None
        out[h] = [weighted_quantile(pairs, tau) for tau in levels]
    return out


def regression_component(launches, log_p1, levels):
    """Per-hour OLS of log-ratio on ln(hour-1) over rolling launches."""
    rolling = [item for item in launches if item["rolling"]]
    if len(rolling) < MIN_POOL:
        return None
    out = {}
    for h in range(2, 25):
        xs = []
        ys = []
        for launch in rolling:
            curve = launch["curve"]
            if h not in curve:
                continue
            xs.append(launch["log_h1"])
            ys.append(math.log(curve[h] / curve[1]))
        if len(xs) < MIN_POOL:
            return None
        a, b = ols(xs, ys)
        centre = a + b * log_p1
        residuals = sorted(y - (a + b * x) for x, y in zip(xs, ys))
        out[h] = [centre + interp_quantile(residuals, tau) for tau in levels]
    return out


def fallback_component(levels):
    """House baseline shape: persistence with a widening random-walk spread."""
    table = {}
    for h in range(2, 25):
        spread = FALLBACK_SIGMA * math.sqrt(h - 1)
        table[h] = [z * spread for z, tau in zip(Z_FALLBACK, levels)]
    return table


def blend_components(kernel_q, regression_q, levels):
    """50/50 log-space blend of the two components, spread widened 1.1x."""
    blended = {}
    median_i = min(range(len(levels)), key=lambda i: abs(levels[i] - 0.5))
    for h in range(2, 25):
        row = []
        for i, tau in enumerate(levels):
            a = kernel_q[h][i]
            b = regression_q[h][i]
            row.append(BLEND_KERNEL * a + (1.0 - BLEND_KERNEL) * b)
        median = row[median_i]
        row = [median + (q - median) * SPREAD_WIDEN for q in row]
        blended[h] = row
    return blended


def forecast_case(case, name):
    """One case -> {"hours": [{"hour": h, "q": [5 quantiles]}, ...]}."""
    levels = list(case.get("levels") or DEFAULT_LEVELS)
    known = case.get("known") or []
    first = next((k for k in known if k.get("hour") == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1.0, float(first["viewers"]))
    log_p1 = math.log(p1)

    launches = collect_launches(case)
    kernel_q = kernel_component(launches, log_p1, levels)
    regression_q = regression_component(launches, log_p1, levels)

    if kernel_q is None and regression_q is None:
        log_quantiles = fallback_component(levels)
    elif kernel_q is None:
        log_quantiles = regression_q
    elif regression_q is None:
        log_quantiles = kernel_q
    else:
        log_quantiles = blend_components(kernel_q, regression_q, levels)

    rows = []
    for row in case["forecast"]:
        h = int(row["hour"])
        qs = []
        prev = 0.0
        for q in log_quantiles[h]:
            value = p1 * math.exp(q)
            value = min(max(value, 1.0), 1e9)
            value = round_half_up_2(value)
            # Keep the row non-decreasing after rounding.
            if value < prev:
                value = prev
            prev = value
            qs.append(value)
        rows.append({"hour": h, "q": qs})
    rows.sort(key=lambda r: r["hour"])
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        out_path = OUTPUT_DIR / f"{path.stem}.out"
        out_path.write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
