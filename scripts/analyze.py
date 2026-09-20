#!/usr/bin/env python3
"""Step 1 of the cataract-surgery-cuts skill: map the surgical video.
- Builds contact sheets (frames with burned-in timestamp) for Claude to classify the phases.
- Measures motion per second (frame difference) and lists idle stretches (cut candidates).
- Detects scene cuts and per-second "off-eye" candidates (color saturation drop).
Usage: python analyze.py <video> <case_folder> [--interval 5] [--per-sheet 12]
Output: <case_folder>/sheets/sheet_XX.jpg, <case_folder>/motion.json, <case_folder>/info.json
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TRACK_FPS = 2

FONT_CANDIDATES = ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def load_font(size):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size, index=1 if f.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def need_tools():
    for t in ("ffmpeg", "ffprobe"):
        if not shutil.which(t):
            raise SystemExit(f"{t} not found in PATH (install with: brew install ffmpeg)")


def probe(video):
    if not Path(video).is_file():
        raise SystemExit(f"video not found: {video}")
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate,duration:format=duration", "-of", "json", str(video)])
    try:
        d = json.loads(r.stdout)
        s = d["streams"][0]
    except (ValueError, KeyError, IndexError):
        raise SystemExit(f"could not read a video stream from {video}")
    num, den = s["r_frame_rate"].split("/")
    dur = d.get("format", {}).get("duration") or s.get("duration")
    if dur is None:
        raise SystemExit(f"could not read the duration of {video}")
    return {"width": s["width"], "height": s["height"], "fps": round(int(num) / int(den or 1), 3),
            "duration": float(dur)}


def motion(video, out_json):
    """Mean difference between consecutive frames, 2 samples/s, 0-255 scale."""
    r = run(["ffmpeg", "-v", "info", "-i", str(video), "-vf",
             "fps=2,scale=160:-1,format=gray,tblend=all_mode=difference,signalstats,metadata=print:file=-",
             "-f", "null", "-"])
    vals = []
    t = None
    for ln in r.stdout.splitlines():
        if "pts_time" in ln:
            t = float(ln.split("pts_time:")[1].split()[0])
        elif "signalstats.YAVG" in ln and t is not None:
            vals.append((t, float(ln.split("=")[1]))); t = None
    # idle stretches: motion below a threshold for >= 4 s
    threshold = max(0.6, sorted(v for _, v in vals)[len(vals) // 4] * 0.8) if vals else 1.0
    idle, start = [], None
    for t, v in vals:
        if v < threshold and start is None:
            start = t
        elif v >= threshold and start is not None:
            if t - start >= 4:
                idle.append({"start": round(start, 1), "end": round(t, 1), "seconds": round(t - start, 1)})
            start = None
    if start is not None and vals and vals[-1][0] - start >= 4:
        idle.append({"start": round(start, 1), "end": round(vals[-1][0], 1), "seconds": round(vals[-1][0] - start, 1)})
    # scene cuts: abrupt image change (camera leaves the eye, zoom, field change)
    rs = run(["ffmpeg", "-v", "info", "-i", str(video), "-vf", "fps=4,scale=320:-1,select='gt(scene,0.25)',metadata=print:file=-", "-f", "null", "-"])
    cuts = [round(float(m.group(1)), 1) for m in re.finditer(r"pts_time:([\d.]+)", rs.stdout)]
    out = {"threshold": round(threshold, 2), "samples": [[round(t, 1), round(v, 2)] for t, v in vals], "idle": idle,
           "scene_cuts": cuts}
    Path(out_json).write_text(json.dumps(out, ensure_ascii=False))
    return out


def field_track(video, folder, out_json, sample_fps=TRACK_FPS):
    """Where the surgical field sits in each frame, and how saturated it is.

    The microscope lights a circle over the eye: the bright, colored pixels are the field. Its
    centroid drives the crop of the vertical export (so it stays on the eye when the scope drifts),
    and the mean saturation tells us when the camera left the eye altogether.
    """
    tmp = folder / "tmp_track"; tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps={sample_fps},scale=120:-1",
             "-q:v", "6", str(tmp / "g_%06d.jpg")])
    files = sorted(tmp.glob("g_*.jpg"))
    if not files:
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit("ffmpeg extracted no frames for tracking")
    points, sats = [], []
    for i, fp in enumerate(files):
        im = Image.open(fp).convert("HSV")
        w, h = im.size
        sat = im.getchannel("S").tobytes()
        val = im.getchannel("V").tobytes()
        vmax = max(val)
        # the lit field: bright relative to this frame's own maximum, and not grey (drape/metal).
        # Weighting by saturation pulls the centroid onto the eye itself (conjunctiva, iris, red
        # reflex) instead of the middle of the whole lit drape.
        v_thr, s_thr = vmax * 0.45, 40
        n = sx = sy = cov = 0
        for k in range(0, len(val), 2):  # every other pixel is plenty at 120 px wide
            if val[k] > v_thr and sat[k] > s_thr:
                wgt = sat[k] - s_thr
                n += wgt; sx += (k % w) * wgt; sy += (k // w) * wgt
                cov += 1
        t = round(i / sample_fps, 2)
        mean_sat = sum(sat) / len(sat)
        sats.append(mean_sat)
        if n:
            points.append([t, round(sx / n / w, 4), round(sy / n / h, 4), round(cov * 2 / (w * h), 3),
                           round(mean_sat, 1)])
        else:
            points.append([t, 0.5, 0.5, 0.0, round(mean_sat, 1)])
    for f in tmp.glob("*.jpg"):
        f.unlink()
    tmp.rmdir()
    sat_ref = sorted(sats)[len(sats) // 2] if sats else 0
    off_eye = sorted({int(p[0]) for p in points if p[4] < sat_ref * 0.45})
    track = {"sample_fps": sample_fps, "median_saturation": round(sat_ref, 1),
             "columns": ["t", "cx", "cy", "coverage", "saturation"], "points": points,
             "off_eye_candidate_seconds": off_eye}
    Path(out_json).write_text(json.dumps(track, ensure_ascii=False))
    return track


def sheets(video, folder, interval, per_sheet):
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "tmp"; tmp.mkdir(exist_ok=True)
    for p in tmp.glob("*.jpg"):
        p.unlink()
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps=1/{interval},scale=480:-1", "-q:v", "3",
             str(tmp / "f_%05d.jpg")])
    frames = sorted(tmp.glob("f_*.jpg"))
    if not frames:
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit("ffmpeg extracted no frames - the sheets would be empty")
    f = load_font(26)
    cols = 4
    outputs = []
    for k in range(0, len(frames), per_sheet):
        batch = frames[k:k + per_sheet]
        w, h = Image.open(batch[0]).size
        rows = (len(batch) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * w, rows * h), "black")
        for i, fp in enumerate(batch):
            im = Image.open(fp).convert("RGB")
            t = (k + i) * interval
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, 120, 38), fill="black"); d.text((8, 4), f"{t // 60:02d}:{t % 60:02d}", font=f, fill="yellow")
            sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        out = folder / f"sheet_{k // per_sheet + 1:02d}.jpg"
        sheet.save(out, quality=82); outputs.append(str(out))
    for p in tmp.glob("*.jpg"):
        p.unlink()
    tmp.rmdir()
    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("folder")
    ap.add_argument("--interval", type=int, default=5, help="seconds between frames")
    ap.add_argument("--per-sheet", type=int, default=12)
    a = ap.parse_args()
    video, folder = Path(a.video), Path(a.folder)
    folder.mkdir(parents=True, exist_ok=True)
    need_tools()
    info = probe(video)
    mov = motion(video, folder / "motion.json")
    trk = field_track(video, folder, folder / "track.json")
    outputs = sheets(video, folder / "sheets", a.interval, a.per_sheet)
    info.update({"video": str(video), "interval": a.interval, "sheets": outputs, "idle": mov["idle"],
                 "scene_cuts": mov["scene_cuts"], "off_eye_candidates": trk["off_eye_candidate_seconds"],
                 "track": str(folder / "track.json"), "motion": str(folder / "motion.json")})
    (folder / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1))
    def head(seq, n=12):
        """Summarize long lists: the caller reads this output, motion.json keeps everything."""
        return seq if len(seq) <= n else seq[:n] + [f"... +{len(seq) - n} more (see motion.json)"]

    off = trk["off_eye_candidate_seconds"]
    print(json.dumps({"duration_s": round(info["duration"], 1), "fps": info["fps"],
                      "resolution": f"{info['width']}x{info['height']}",
                      "interval_s": a.interval, "sheets": len(outputs),
                      "idle_count": len(mov["idle"]), "idle": head(mov["idle"]),
                      "scene_cuts_count": len(mov["scene_cuts"]), "scene_cuts": head(mov["scene_cuts"]),
                      "off_eye_candidates_count": len(off), "off_eye_candidates_s": head(off),
                      "off_eye_total_s": len(off)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
