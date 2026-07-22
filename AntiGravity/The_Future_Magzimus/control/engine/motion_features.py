"""Motion feature extraction — 48-dim per-axis statistics for the trigger
classifier. Ported 1:1 from the old Smart Staff project's archive
`motion_model.js` (`MotionModel.Features`, the 6-raw-axis variant, not the
magnitude-collapsed one that shipped in Ver_Beta) — see
docs/agent/DONE.md for why per-axis beats magnitude-collapsed here: this
project's own axis-mapping tests this session established that WHICH axis
rotates (not just how much) is exactly the signal that distinguishes the
Bank triggers from each other.

Pure functions, no I/O, no framework dependency — operates on plain dicts
shaped like a recorded StaffTelemetry frame (the `data` field of a
docs/measurements/*.jsonl "telemetry" line).
"""
from __future__ import annotations
import math

AXES = ('accX', 'accY', 'accZ', 'gyroX', 'gyroY', 'gyroZ')
STATS_PER_AXIS = 8
FEATURE_SIZE = len(AXES) * STATS_PER_AXIS  # 48


def _axis_features(values: list[float]) -> list[float]:
    """The 8 stats for one axis's window of values, in a fixed order:
    [mean, std, max_abs, energy, zero_crossings, dominant_freq, skewness, iqr]."""
    n = len(values)
    if n == 0:
        return [0.0] * STATS_PER_AXIS

    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    std = math.sqrt(variance)
    max_abs = max((abs(x) for x in values), default=0.0)
    energy = sum(x * x for x in values) / n

    zero_crossings = 0
    for i in range(1, n):
        if (values[i - 1] >= 0) != (values[i] >= 0):
            zero_crossings += 1

    dom_freq = _dominant_freq(values)

    skew = 0.0
    if std > 1e-9:
        skew = sum(((x - mean) / std) ** 3 for x in values) / n

    sorted_vals = sorted(values)
    q1 = sorted_vals[int(n * 0.25)] if n else 0.0
    q3 = sorted_vals[int(n * 0.75)] if n else 0.0
    iqr = q3 - q1

    return [mean, std, max_abs, energy, float(zero_crossings), dom_freq, skew, iqr]


def _dominant_freq(values: list[float]) -> float:
    """Brute-force DFT (not FFT — fine for n<=60), returns the dominant bin
    index normalized to 0..1 (not a Hz value). O(n^2) per axis, matching the
    original JS implementation exactly."""
    n = len(values)
    if n < 4:
        return 0.0
    half = n // 2
    max_pow = 0.0
    dom_bin = 0
    for k in range(1, half):
        re = 0.0
        im = 0.0
        for t in range(n):
            angle = (2 * math.pi * k * t) / n
            re += values[t] * math.cos(angle)
            im -= values[t] * math.sin(angle)
        power = re * re + im * im
        if power > max_pow:
            max_pow = power
            dom_bin = k
    return dom_bin / half if half else 0.0


def extract(frames: list[dict]) -> list[float]:
    """frames: a window of telemetry data dicts (each with accX/Y/Z, gyroX/Y/Z
    keys, matching StaffTelemetry / docs/measurements JSONL `data` shape).
    Returns a 48-dim feature vector, always finite (NaN/inf clamped to 0)."""
    if not frames or len(frames) < 2:
        return [0.0] * FEATURE_SIZE

    out: list[float] = []
    for axis in AXES:
        values = [float(f.get(axis, 0) or 0) for f in frames]
        for v in _axis_features(values):
            out.append(v if math.isfinite(v) else 0.0)
    return out
