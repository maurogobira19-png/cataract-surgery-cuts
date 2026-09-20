---
name: cataract-surgery-cuts
description: Edits raw cataract (phaco) surgery video with Claude as the editor. Maps the raw microscope recording into timestamped frame sheets, identifies which surgical phases are present (paracentesis, main incision, viscoelastic, capsulorhexis, hydrodissection, phaco, I/A, IOL implantation, wound hydration) and where the camera leaves the eye, then ASKS the surgeon, phase by phase, which speed they want (real time, 2x, 4x, cut). Removes dead time, optionally burns a title for each phase (the surgeon chooses), masks any patient identifier, takes any specific request the surgeon has, and exports a horizontal 16:9 version and a vertical 9:16 version. Accepts corrections on the finished video and re-renders only what changed. Use whenever the user mentions editing a surgery video, phaco video, "cut my cataract surgery", "make a vertical version of my surgery", "speed up the phaco", "label the steps", or attaches a surgical microscope .mp4/.mov.
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
- **Never cut in the middle of a manoeuvre.** A boundary read off a sheet is only as precise as the
  sheet interval. Refine every boundary on a dense sheet, then run `refine.py`, which moves each cut
  to the nearest pause. A cut inside a chop, a rhexis pull or an injection is a defect, not a style.
- **Titles are optional.** Ask before rendering. Many surgeons want the video clean, or want to add
  their own captions later.
- **Off-eye time is removed by default.** Camera off the field, microscope adjustments, hands out of
  the field for more than 3 s. It is the only automatic decision, and it is reported in the summary
  before rendering.

## Workflow

### 1. Map (automatic)
```
SKILL_DIR/venv/bin/python SKILL_DIR/scripts/analyze.py <video> ~/Documents/Surgeries/<code> --interval 5
```
Produces `sheets/sheet_XX.jpg` (12 frames per sheet, yellow timestamp), `info.json`,
`motion.json` (motion twice a second, idle stretches, scene cuts - this is what `refine.py` reads)
and `track.json` (position of the lit field and its saturation, twice a second; the "off-eye"
candidates come from the saturation dropping when the camera leaves the eye). The `cx`/`cy` in
`track.json` are a rough hint only - they are no better than the middle of the frame, so never use
them to frame the vertical export. Read the sheets for that. Videos over 15 min: `--interval 10`
on the first pass and `--interval 2` on ambiguous ranges.

### 2. Classify (Claude looks)
Read **every** sheet with the Read tool. Build the table of phases found, with start and end
(`assets/phases.md` explains how to recognize each one). Also note:
- position of any patient-data overlay (px, using the resolution in `info.json`);
- off-eye stretches and dead time, confirming the script's candidates on the image;
- where the eye sits in the frame, per phase, as a fraction of the width (`0.5` = middle). This is
  what frames the vertical export, and only the image tells you - read it off the sheet;
- any out-of-the-ordinary event (rhexis running out, posterior capsule rupture, iris prolapse,
  dropped fragment), which becomes its own phase.

### 2b. Refine the boundaries (this is what keeps cuts off the action)
For every boundary, regenerate a dense sheet of the 6 s around it and look again:
```
SKILL_DIR/venv/bin/python SKILL_DIR/scripts/analyze.py <video> <folder>/edge_<t> --interval 1
```
Correct the timestamp to the real transition, then let `refine.py` (step 4) snap it to the pause.

### 3. Ask (one round per block of 4 phases)
Use `AskUserQuestion`. First call, always:
1. **Format**: "Horizontal 16:9 (1920x1080)" / "Vertical 9:16 (1080x1920)" / "Both (Recommended)".
2. **Titles on screen**: "No titles, clean image (Recommended)" / "Title for each phase".
3. **Audio**: "No audio (Recommended)" / "Keep original audio".
4. **Off-eye time**: "Cut (Recommended)" / "Keep at 8x" / "Keep in real time".

Second call:
5. **How to choose speeds**: "Phase by phase (Recommended)" / "Teaching preset: teaching phases in real time, the rest sped up" / "Everything 4x except what I mark".
6. **Anything specific for this edit?** - free text. Options are only examples ("Nothing specific
   (Recommended)" / "Start on the capsulorhexis" / "Keep the whole event in real time"), and what
   the surgeon types in "Other" is the instruction: an opening or closing frame, a phase to leave
   out, a maximum duration, a technique name in the first title, a moment to hold on. Write it into
   the EDL and repeat it back in the summary before rendering. If it cannot be done, say so then,
   not after rendering.
7. **Vertical framing** (only if a vertical version was asked for): "Whole frame on a blurred
   backdrop, never loses the eye" / "3:4 window on a blurred backdrop (Recommended)" / "Strict 9:16
   crop, biggest image, can lose the eye" -> `vertical_fit` of `fit` / `hybrid` / `crop`.

If "phase by phase": following calls with **up to 4 phases each**, in surgical order, only the
phases present in the video. Each question: `"<Phase> (mm:ss-mm:ss, X s)"`, options
**"1x real time" / "2x" / "4x" / "Cut"**, with the suggestion from `assets/phases.md` marked
"(Recommended)". The "Other" field covers 3x, 8x or "1x only on the first chop".
Out-of-the-ordinary events enter as their own phase with "1x real time (Recommended)".

If "teaching preset" or "everything 4x": apply `assets/phases.md` (or 4x) and show the resulting
table in ONE final question: "Looks right?" with "Render" / "I want to adjust a phase".

### 4. Write the EDL, snap the cuts, render
`edl.json` in the format of `scripts/render.py`: one segment per phase, in order, with the chosen
speed, a short title, `mask` or `crop` for the overlay, off-eye time excluded (or at 8x if the
surgeon chose to keep it), `"titles": false` unless titles were asked for, and whatever the surgeon
asked for in question 6.

Snap every cut to the nearest pause before rendering:
```
SKILL_DIR/venv/bin/python SKILL_DIR/scripts/refine.py <folder>/edl.json <folder>/motion.json
```
It reports how far each boundary moved. A move larger than ~2 s means the phase was read wrong on
the sheet - go back to step 2b for that boundary instead of accepting it.

```
SKILL_DIR/venv/bin/python SKILL_DIR/scripts/render.py <folder>/edl.json
```
The script validates the EDL before encoding (segment out of order, `end` before `start`, speed of
zero, a timestamp past the end of the video, a malformed `mask`/`crop`) and stops with the list of
errors instead of rendering something wrong. Default quality is `crf 23` capped at 3 Mbit/s, which
keeps a 30 min horizontal export around 700 MB - shareable. If the surgeon asks for an archival
master, put `"quality": {"crf": 19, "maxrate": "50M"}` in the EDL (roughly double the size).

**Vertical 9:16**: copy to `edl_9x16.json` with `"format": "vertical"`, the chosen `vertical_fit`,
and a `"center": [cx, cy]` **per segment** - the fraction of the width where the eye sits in that
phase, read off the sheets in step 2. That per-phase centre is the whole game: the frame stays put
inside a phase (no drifting or jitter) and only moves at a cut. Keep the phases the surgeon pointed
to, or the ones marked 1x; first segment = the most striking moment.

Output names carry the format, never the word "reel": `<code>_16x9.mp4` and `<code>_9x16.mp4`.

### 5. Check and deliver
Contact sheet of each result (`fps=1/10,tile=6x4`), Read it, and check three things: the mask still
covers the patient data, no cut landed mid-manoeuvre, and **in the vertical version the eye is in
frame on every tile**. If a phase is badly framed, fix its `center` (or drop that phase to
`"vertical_fit": "fit"`) and re-render only it:
```
SKILL_DIR/venv/bin/python SKILL_DIR/scripts/render.py <folder>/edl_9x16.json --segments 3,4
```
Deliver file paths, final duration and the table: phase, original time, chosen speed, time in the
final video, plus total seconds of off-eye time removed.

### 6. Corrections (always offer this)
After delivering, ask what the surgeon wants changed, in free text. Map the answer onto the EDL and
re-render **only the affected segments** with `--segments`, which reuses everything already encoded:

| What the surgeon says | What changes in the EDL |
|---|---|
| "the phaco is still too long" | `speed` of that segment |
| "it cuts before I finish the rhexis" | `end` of that segment (and `start` of the next) |
| "put the titles back" / "take the titles off" | `titles` |
| "the eye is off to the side in the vertical" | `center` of that segment, or `vertical_fit` |
| "start on the rhexis" | drop the earlier segments |
| "I want the full resolution for the congress" | `quality` |

Never re-render everything when a single phase changed, and never re-cut a phase the surgeon did
not mention.

## References
- `assets/phases.md`: how to recognize each phase on the image, suggested speed (suggestion only), titles.
- `assets/edl_example.json`: EDL of a routine phaco.
- `scripts/refine.py`: moves each cut to the nearest pause, keeps consecutive phases touching.
