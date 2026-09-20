#!/usr/bin/env python3
"""Step 3.5 of the cataract-surgery-cuts skill: move every cut off the action.

A phase boundary read off a frame sheet is only as precise as the sheet interval, so a cut often
lands in the middle of a manoeuvre - mid-chop, mid-rhexis. This snaps each boundary to the calmest
instant nearby (the natural pause between manoeuvres, from motion.json), keeps consecutive phases
touching so nothing is dropped between them, and leaves a short handle around the cut.

Usage: python refine.py edl.json motion.json [--window 2.0] [--handle 0.3] [--out edl.json]
"""
import argparse
import json
from pathlib import Path


def quietest(samples, target, window, lo, hi):
    """Instant of least motion within +/- window of target, clamped to [lo, hi]."""
    near = [(v, t) for t, v in samples if abs(t - target) <= window and lo <= t <= hi]
    if not near:
        return target
    floor = min(v for v, _ in near)
    # among the calm instants, keep the one closest to where the phase was said to change
    calm = [t for v, t in near if v <= floor * 1.15]
    return min(calm, key=lambda t: abs(t - target))


def refine(edl, motion, window=2.0, handle=0.3):
    samples = [(float(t), float(v)) for t, v in motion.get("samples", [])]
    segs = [dict(s) for s in edl["segments"]]
    if not samples:
        return segs, []
    span = max(t for t, _ in samples)
    moved = []
    for i, s in enumerate(segs):
        for edge in ("start", "end"):
            t = float(s[edge])
            # do not let a boundary wander into the neighbouring phase
            lo = float(segs[i - 1]["start"]) + 1 if edge == "start" and i else 0.0
            hi = float(segs[i + 1]["end"]) - 1 if edge == "end" and i + 1 < len(segs) else span
            q = quietest(samples, t, window, lo, min(hi, span))
            q = q - handle if edge == "start" else q + handle
            q = max(0.0, min(span, round(q, 2)))
            if abs(q - t) >= 0.05:
                moved.append({"segment": i, "edge": edge, "from": t, "to": q,
                              "title": s.get("title", "")})
                s[edge] = q
    # phases that were meant to run into each other should still touch after snapping
    for a, b in zip(segs, segs[1:]):
        if 0 < b["start"] - a["end"] <= 2 * handle + 0.2:
            mid = round((a["end"] + b["start"]) / 2, 2)
            a["end"] = b["start"] = mid
        if b["start"] < a["end"]:
            b["start"] = a["end"]
    return [s for s in segs if s["end"] - s["start"] > 0.2], moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl"); ap.add_argument("motion")
    ap.add_argument("--window", type=float, default=2.0, help="how far a cut may move, in seconds")
    ap.add_argument("--handle", type=float, default=0.3, help="breathing room kept around each cut")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    edl = json.loads(Path(a.edl).read_text())
    motion = json.loads(Path(a.motion).read_text())
    segs, moved = refine(edl, motion, a.window, a.handle)
    edl["segments"] = segs
    Path(a.out or a.edl).write_text(json.dumps(edl, ensure_ascii=False, indent=1))
    print(json.dumps({"segments": len(segs), "boundaries_moved": len(moved),
                      "max_shift_s": round(max((abs(m["to"] - m["from"]) for m in moved), default=0), 2),
                      "moves": moved[:20]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
