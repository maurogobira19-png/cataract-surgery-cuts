---
name: cataract-surgery-cuts
description: Edits raw cataract (phaco) surgery video with Claude as the editor. Maps the raw microscope recording into timestamped frame sheets, identifies which surgical phases are present (paracentesis, main incision, viscoelastic, capsulorhexis, hydrodissection, phaco, I/A, IOL implantation, wound hydration) and where the camera leaves the eye, then ASKS the surgeon, phase by phase, which speed they want (real time, 2x, 4x, cut). Removes dead time, burns a title for each phase, masks any patient identifier, and exports a 16:9 lecture version and a 9:16 reel. Use whenever the user mentions editing a surgery video, phaco video, "cut my cataract surgery", "make a reel from my surgery", "speed up the phaco", "label the steps", or attaches a surgical microscope .mp4/.mov.
---

# Cataract surgery cuts: the surgeon decides, Claude executes

The skill has no editorial opinion. It does the grunt work (finding where each phase starts and
ends, where the camera left the eye, where the patient's name is on screen) and hands the speed
decision back to the surgeon, **phase by phase, with closed options to click**. Then it renders.

Base: `~/.claude/skills/cataract-surgery-cuts/` (SKILL_DIR). Case folder: `~/Documents/Surgeries/<code>/`.
Requirements: ffmpeg (Homebrew) and the venv `SKILL_DIR/venv` with Pillow
(`python3 -m venv SKILL_DIR/venv && SKILL_DIR/venv/bin/pip install pillow`).

## Non-negotiable rules
- **Zero identification.** Microscope overlays (name, date of birth, record number) are located on
  the frame sheets and covered with `mask` or removed with `crop` before any export. Output file
  names carry a case code only.
- **Never invent a phase.** If a sheet is ambiguous, generate a denser sheet for that range
  (`--interval 1`) before listing. Only phases actually seen go into the question round.
- **Speed is the surgeon's choice.** The skill suggests a default (marked "Recommended") but always
  asks. Never render without the question round, unless the user already stated everything in the
  message ("everything 4x, rhexis and IOL in real time").
- **Off-eye time is removed by default.** Camera off the field, microscope adjustments, hands out of
  the field for more than 3 s. It is the only automatic decision, and it is reported in the summary
  before rendering.

## Workflow

### 1. Map (automatic)
```
SKILL_DIR/venv/bin/python SKILL_DIR/scripts/analyze.py <video> ~/Documents/Surgeries/<code> --interval 5
```
Produces `sheets/sheet_XX.jpg` (12 frames per sheet, yellow timestamp), `info.json` and
`motion.json` with: idle stretches, scene cuts and per-second "off-eye" candidates (color
saturation drops when the surgical field leaves the frame). Videos over 15 min: `--interval 10`
on the first pass and `--interval 2` on ambiguous ranges.

### 2. Classify (Claude looks)
Read **every** sheet with the Read tool. Build the table of phases found, with start and end
(`assets/phases.md` explains how to recognize each one). Also note:
- position of any patient-data overlay (px, using the resolution in `info.json`);
- off-eye stretches and dead time, confirming the script's candidates on the image;
- any out-of-the-ordinary event (rhexis running out, posterior capsule rupture, iris prolapse,
  dropped fragment), which becomes its own phase.

### 3. Ask (one round per block of 4 phases)
Use `AskUserQuestion`. First call, always:
1. **Format**: "Lecture 16:9" / "Reel 9:16" / "Both (Recommended)".
2. **Audio**: "No audio (Recommended)" / "Keep original audio".
3. **Off-eye time**: "Cut (Recommended)" / "Keep at 8x" / "Keep in real time".
4. **How to choose speeds**: "Phase by phase (Recommended)" / "Lecture preset: teaching phases in real time, the rest sped up" / "Everything 4x except what I mark".

If "phase by phase": following calls with **up to 4 phases each**, in surgical order, only the
phases present in the video. Each question: `"<Phase> (mm:ss–mm:ss, X s)"`, options
**"1x real time" / "2x" / "4x" / "Cut"**, with the suggestion from `assets/phases.md` marked
"(Recommended)". The "Other" field covers 3x, 8x or "1x only on the first chop".
Out-of-the-ordinary events enter as their own phase with "1x real time (Recommended)".

If "lecture preset" or "everything 4x": apply `assets/phases.md` (or 4x) and show the resulting
table in ONE final question: "Looks right?" with "Render" / "I want to adjust a phase".

### 4. Write the EDL and render
`edl.json` in the format of `scripts/render.py`: one segment per phase, in order, with the chosen
speed, a short title ("Capsulorhexis", "Phaco", "IOL implantation"), `mask` or `crop` for the
overlay, off-eye time excluded (or at 8x if the surgeon chose to keep it).
```
SKILL_DIR/venv/bin/python SKILL_DIR/scripts/render.py ~/Documents/Surgeries/<code>/edl.json
```
The script validates the EDL before encoding (segment out of order, `end` before `start`, speed of
zero, a timestamp past the end of the video, a malformed `mask`/`crop`) and stops with the list of
errors instead of rendering something wrong. Default quality is `crf 23` capped at 3 Mbit/s, which
keeps a 30 min lecture around 700 MB — shareable. If the surgeon asks for an archival master, put
`"quality": {"crf": 19, "maxrate": "50M"}` in the EDL (roughly double the size).
Reel: copy to `edl_reel.json` with `format: "vertical"`, `crop` centered on the eye, and only the
phases marked 1x (or the ones the surgeon points to); first segment = the most striking moment.

### 5. Check and deliver
Contact sheet of the result (`fps=1/10,tile=6x4`), Read it, check the mask and the absence of
patient data. Deliver file paths, final duration and the table: phase, original time, chosen
speed, time in the final video, plus total seconds of off-eye time removed.

## References
- `assets/phases.md`: how to recognize each phase on the image, suggested speed (suggestion only), titles.
- `assets/edl_example.json`: EDL of a routine phaco.
