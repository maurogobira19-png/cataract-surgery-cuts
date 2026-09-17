#!/usr/bin/env python3
"""Step 4 of the cataract-surgery-cuts skill: render the edit from an EDL (JSON).
Usage: python render.py edl.json
EDL:
{
 "video": "/path/surgery.mp4",
 "output": "/path/surgery_edited.mp4",
 "format": "horizontal" | "vertical",           # vertical = 1080x1920 with a centered crop (or "crop" below)
 "crop": [x, y, w, h],                            # optional: fixed crop of the surgical field (removes patient name)
 "mask": [x, y, w, h],                            # optional: black box over an overlay with identifiers
 "audio": false,                                  # keep original audio?
 "title_style": {"size": 54},                     # optional
 "segments": [
   {"start": 12.0, "end": 48.5, "speed": 1.0, "title": "Main incision 2.2 mm"},
   {"start": 60.0, "end": 130.0, "speed": 3.0, "title": "Capsulorhexis"}
 ]
}
Each segment becomes a clip at the requested speed, with the title burned in for the first 3 s (fade). Then concatenated.
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
FPS = 30


def load_font(size, bold=True):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size, index=(4 if bold else 10) if f.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-3000:], file=sys.stderr); raise SystemExit("ffmpeg failed")
    return r


def title_png(text, W, H, path, size=54, speed=1.0):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f = load_font(size); sub = load_font(int(size * 0.55), bold=False)
    tw = d.textlength(text, font=f); pad = 22
    x, y = 60, H - size - 120
    d.rounded_rectangle((x - pad, y - 10, x + tw + pad, y + size + 12), 14, fill=(0, 0, 0, 200))
    d.text((x, y), text, font=f, fill="white")
    if speed != 1.0:
        lab = f"{speed:g}x"; lw = d.textlength(lab, font=sub)
        d.rounded_rectangle((x + tw + pad + 14, y + 4, x + tw + pad + 14 + lw + 24, y + 4 + sub.size + 14), 10, fill=(255, 214, 0, 235))
        d.text((x + tw + pad + 26, y + 8), lab, font=sub, fill="black")
    img.save(path)


def main(edl_path):
    edl = json.loads(Path(edl_path).read_text())
    video, output = edl["video"], edl["output"]
    vertical = edl.get("format") == "vertical"
    W, H = (1080, 1920) if vertical else (1920, 1080)
    work = Path(output).with_suffix(""); work.mkdir(parents=True, exist_ok=True)
    pre = []
    if edl.get("mask"):
        x, y, w, h = edl["mask"]; pre.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill")
    if edl.get("crop"):
        x, y, w, h = edl["crop"]; pre.append(f"crop={w}:{h}:{x}:{y}")
    pre.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    segs = []
    for i, s in enumerate(edl["segments"]):
        v = float(s.get("speed", 1.0)); dur = (s["end"] - s["start"]) / v
        seg = work / f"seg_{i:02d}.mp4"
        chain = ",".join(pre) + f",setpts=PTS/{v},fps={FPS}"
        inputs = ["-ss", str(s["start"]), "-to", str(s["end"]), "-i", video]
        if s.get("title"):
            png = work / f"t_{i:02d}.png"; title_png(s["title"], W, H, png, edl.get("title_style", {}).get("size", 54), v)
            inputs += ["-loop", "1", "-i", str(png)]
            show = min(3.5, dur)
            chain = f"[0:v]{chain}[v0];[1:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,fade=t=out:st={show-0.4:.2f}:d=0.4:alpha=1[t];[v0][t]overlay=0:0:shortest=1[v]"
        else:
            chain = f"[0:v]{chain}[v]"
        audio = ["-map", "0:a?", "-af", f"atempo={min(v, 2.0)}" + (f",atempo={v/2.0}" if v > 2.0 else ""), "-c:a", "aac"] if edl.get("audio") else ["-an"]
        run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", chain, "-map", "[v]", *audio,
             "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), str(seg)])
        segs.append(seg); print(f"seg {i:02d}: {s['start']:.1f}-{s['end']:.1f}s x{v:g} -> {dur:.1f}s  {s.get('title','')}")
    lst = work / "concat.txt"; lst.write_text("".join(f"file '{p}'\n" for p in segs))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", output])
    total = sum((s["end"] - s["start"]) / float(s.get("speed", 1)) for s in edl["segments"])
    print(f"OK {output}  {total/60:.1f} min ({len(segs)} segments)")


if __name__ == "__main__":
    main(sys.argv[1])
