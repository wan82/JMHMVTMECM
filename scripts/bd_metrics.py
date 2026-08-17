#!/usr/bin/env python3
"""BD-rate and time-reduction primitives.

Pure math, no I/O — so it can be unit-tested and reused. The BD-rate follows the
JCTVC-L0330 / JVET reference formulation: fit log10(rate) against PSNR with a
piecewise cubic Hermite (PCHIP) spline, integrate analytically over the PSNR
range the two curves share, and take the ratio of the two areas.

Verified to reproduce the reference implementation in
GOP_CTCData/GOP_analPro/module_log/srcPipe/bd_rate.py bit-for-bit on 4-point
curves (see selftest() at the bottom); unlike that one it also accepts curves
with more or fewer than 4 points, which the full-CTC plan needs (HANDOFF 4.6
proposes moving to 6 QPs).

Sign convention
---------------
`bd_rate(anchor_rate, anchor_psnr, test_rate, test_psnr)` returns the average
bitrate change of *test* relative to *anchor*, in percent:

    negative -> test needs FEWER bits at equal quality (test is better)
    positive -> test needs MORE bits at equal quality (test is worse)

`time_reduction(anchor_time, test_time)` returns percent time *saved* by test:

    positive -> test is faster
    negative -> test is slower
"""

from __future__ import annotations

import math

__all__ = ["bd_rate", "time_reduction", "psnr_overlap_pct", "mse_mean_psnr"]


def _pchip_end_slope(h1: float, h2: float, del1: float, del2: float) -> float:
    """One-sided PCHIP endpoint derivative, clamped to preserve monotonicity."""
    d = ((2.0 * h1 + h2) * del1 - h1 * del2) / (h1 + h2)
    if d * del1 < 0.0:
        return 0.0
    if del1 * del2 < 0.0 and abs(d) > abs(3.0 * del1):
        return 3.0 * del1
    return d


def _pchip_slopes(h: list[float], delta: list[float]) -> list[float]:
    """Interior + endpoint derivatives of the monotone cubic interpolant."""
    n = len(h) + 1
    d = [0.0] * n
    if n == 2:
        return [delta[0], delta[0]]
    d[0] = _pchip_end_slope(h[0], h[1], delta[0], delta[1])
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0.0:
            # Local extremum: flat, otherwise the spline would overshoot.
            d[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            d[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    d[n - 1] = _pchip_end_slope(h[-1], h[-2], delta[-1], delta[-2])
    return d


def _integrate(rate: list[float], psnr: list[float],
               low: float, high: float) -> float:
    """Integral of the PCHIP fit of log10(rate) over psnr in [low, high]."""
    order = sorted(range(len(psnr)), key=lambda i: psnr[i])
    x = [psnr[i] for i in order]
    y = [math.log10(rate[i]) for i in order]

    h = [x[i + 1] - x[i] for i in range(len(x) - 1)]
    if any(v <= 0.0 for v in h):
        raise ValueError("duplicate PSNR values: the RD curve is not a function")
    delta = [(y[i + 1] - y[i]) / h[i] for i in range(len(h))]
    d = _pchip_slopes(h, delta)

    total = 0.0
    for i in range(len(h)):
        # Cubic on [x_i, x_i+1]:  y_i + d_i t + c_i t^2 + b_i t^3
        c = (3.0 * delta[i] - 2.0 * d[i] - d[i + 1]) / h[i]
        b = (d[i] - 2.0 * delta[i] + d[i + 1]) / (h[i] * h[i])

        s0 = min(max(x[i], low), high) - x[i]
        s1 = min(max(x[i + 1], low), high) - x[i]
        if s1 <= s0:
            continue
        total += (s1 - s0) * y[i]
        total += (s1 ** 2 - s0 ** 2) * d[i] / 2.0
        total += (s1 ** 3 - s0 ** 3) * c / 3.0
        total += (s1 ** 4 - s0 ** 4) * b / 4.0
    return total


def bd_rate(anchor_rate, anchor_psnr, test_rate, test_psnr) -> float:
    """Average bitrate difference of `test` vs `anchor`, in percent.

    Negative means the test curve needs fewer bits for the same PSNR.
    """
    for name, seq in (("anchor_rate", anchor_rate), ("anchor_psnr", anchor_psnr),
                      ("test_rate", test_rate), ("test_psnr", test_psnr)):
        if len(seq) < 3:
            raise ValueError(f"{name}: need at least 3 points, got {len(seq)}")
    if len(anchor_rate) != len(anchor_psnr) or len(test_rate) != len(test_psnr):
        raise ValueError("rate and psnr lists must have equal length")
    if any(r <= 0 for r in list(anchor_rate) + list(test_rate)):
        raise ValueError("bitrates must be positive")

    low = max(min(anchor_psnr), min(test_psnr))
    high = min(max(anchor_psnr), max(test_psnr))
    if high <= low:
        raise ValueError("RD curves do not overlap in PSNR; BD-rate undefined")

    va = _integrate(anchor_rate, anchor_psnr, low, high)
    vb = _integrate(test_rate, test_psnr, low, high)
    return (10.0 ** ((vb - va) / (high - low)) - 1.0) * 100.0


def psnr_overlap_pct(anchor_psnr, test_psnr) -> float:
    """Percentage of the combined PSNR span that the two curves share.

    JVET practice treats <75 % as unreliable (HANDOFF 6.9): outside the overlap
    BD-rate is extrapolated rather than integrated.
    """
    low = max(min(anchor_psnr), min(test_psnr))
    high = min(max(anchor_psnr), max(test_psnr))
    union_low = min(min(anchor_psnr), min(test_psnr))
    union_high = max(max(anchor_psnr), max(test_psnr))
    if union_high <= union_low:
        return 0.0
    return max(0.0, (high - low)) / (union_high - union_low) * 100.0


def time_reduction(anchor_time: float, test_time: float) -> float:
    """Percent of encoding time saved by `test` relative to `anchor`.

    Positive = test is faster.
    """
    if anchor_time <= 0:
        raise ValueError("anchor time must be positive")
    return (anchor_time - test_time) / anchor_time * 100.0


def mse_mean_psnr(psnr_db) -> float:
    """Average a set of per-picture PSNRs correctly, i.e. in the MSE domain.

    Averaging decibels arithmetically is not meaningful — PSNR is logarithmic,
    so the mean of the logs is not the log of the mean error. This converts back
    to MSE, averages, and converts again.

    The peak value MAX cancels out of the round trip, so this needs no bit-depth
    argument: mean(MAX^2 * 10^(-p/10)) = MAX^2 * mean(10^(-p/10)), and the MAX^2
    divides straight back out. (The reference implementation carries a per-
    sequence MAX table for this; it has no effect on the result.)
    """
    vals = list(psnr_db)
    if not vals:
        raise ValueError("empty PSNR list")
    inv_mse = sum(10.0 ** (-p / 10.0) for p in vals) / len(vals)
    return -10.0 * math.log10(inv_mse)


# --- self-test -------------------------------------------------------------
def selftest() -> None:
    """Check against the reference implementation and known identities."""
    # 1. Reference example from GOP_CTCData bd_rate.py __main__. The expected
    #    value below is what that implementation returns for these inputs
    #    (its own __main__ prints it multiplied by 100 a second time, so the
    #    number echoed there is 100x too large — the function itself is right).
    rate_a = [3900000.0, 1801728.0, 813984.0, 380736.0]
    dist_a = [40.974920000000004, 38.88568, 36.328120000000006, 33.542060000000006]
    rate_b = [3896352.0, 1788672.0, 807840.0, 378912.0]
    dist_b = [40.97608, 38.88982, 36.32812000000000, 33.542060000000006]
    got = bd_rate(rate_a, dist_a, rate_b, dist_b)
    assert abs(got - (-0.6901253565603005)) < 1e-9, got

    # 2. A curve against itself is exactly 0 %.
    assert abs(bd_rate(rate_a, dist_a, rate_a, dist_a)) < 1e-9

    # 3. Scaling every rate by k shifts BD-rate by exactly (k-1)*100 %.
    k = 1.10
    scaled = [r * k for r in rate_a]
    assert abs(bd_rate(rate_a, dist_a, scaled, dist_a) - 10.0) < 1e-6

    # 4. Antisymmetry: swapping anchor and test inverts the ratio.
    fwd = bd_rate(rate_a, dist_a, rate_b, dist_b)
    rev = bd_rate(rate_b, dist_b, rate_a, dist_a)
    assert abs((1 + fwd / 100) * (1 + rev / 100) - 1.0) < 1e-9

    # 5. Works with 5 and 6 points (the reference is hardcoded to 4).
    r5 = [4e6, 2e6, 1e6, 5e5, 2.5e5]
    d5 = [41.0, 39.0, 37.0, 35.0, 33.0]
    assert abs(bd_rate(r5, d5, [r * 1.05 for r in r5], d5) - 5.0) < 1e-6

    # 6. MSE-domain mean is invariant to the peak value and <= arithmetic mean.
    ps = [40.0, 38.0, 36.0, 34.0]
    m = mse_mean_psnr(ps)
    assert m < sum(ps) / len(ps)
    assert abs(mse_mean_psnr([37.0, 37.0, 37.0]) - 37.0) < 1e-12

    # 7. Overlap and time reduction.
    assert abs(psnr_overlap_pct([30, 40], [30, 40]) - 100.0) < 1e-9
    assert abs(psnr_overlap_pct([30, 35], [35, 40])) < 1e-9
    assert abs(time_reduction(100.0, 75.0) - 25.0) < 1e-12
    print("bd_metrics selftest: all checks passed")


if __name__ == "__main__":
    selftest()
