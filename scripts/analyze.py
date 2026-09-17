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
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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


def probe(video):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(video)])
    d = json.loads(r.stdout)
    s = d["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"width": s["width"], "height": s["height"], "fps": round(int(num) / int(den), 3),
            "duration": float(d["format"]["duration"])}


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
    # saturation per second: the surgical field is saturated (iris/red reflex); off the eye it drops
    rb = run(["ffmpeg", "-v", "info", "-i", str(video), "-vf", "fps=1,scale=160:-1,signalstats,metadata=print:file=-", "-f", "null", "-"])
    sat = []
    t = None
    for ln in rb.stdout.splitlines():
        if "pts_time" in ln:
            t = float(ln.split("pts_time:")[1].split()[0])
        elif "signalstats.SATAVG" in ln and t is not None:
            sat.append([round(t), round(float(ln.split("=")[1]), 1)])
    sat_ref = sorted(v for _, v in sat)[len(sat) // 2] if sat else 0
    off_eye = [t for t, v in sat if v < sat_ref * 0.45]
    out = {"threshold": round(threshold, 2), "samples": [[round(t, 1), round(v, 2)] for t, v in vals], "idle": idle,
           "scene_cuts": cuts, "median_saturation": sat_ref, "off_eye_candidate_seconds": off_eye}
    Path(out_json).write_text(json.dumps(out, ensure_ascii=False))
    return out


def sheets(video, folder, interval, per_sheet):
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "tmp"; tmp.mkdir(exist_ok=True)
    for p in tmp.glob("*.jpg"):
        p.unlink()
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps=1/{interval},scale=480:-1", "-q:v", "3",
         str(tmp / "f_%05d.jpg")])
    frames = sorted(tmp.glob("f_*.jpg"))
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
    info = probe(video)
    mov = motion(video, folder / "motion.json")
    outputs = sheets(video, folder / "sheets", a.interval, a.per_sheet)
    info.update({"video": str(video), "interval": a.interval, "sheets": outputs, "idle": mov["idle"],
                 "scene_cuts": mov["scene_cuts"], "off_eye_candidates": mov["off_eye_candidate_seconds"]})
    (folder / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1))
    print(json.dumps({"duration_s": round(info["duration"], 1), "fps": info["fps"], "resolution": f"{info['width']}x{info['height']}",
                      "sheets": len(outputs), "idle": mov["idle"], "scene_cuts": mov["scene_cuts"],
                      "off_eye_candidates_s": mov["off_eye_candidate_seconds"]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
