# cataract-surgery-cuts

A [Claude Code](https://claude.com/claude-code) skill that edits raw cataract surgery video with Claude as the editor.

You drop a 10-minute microscope recording into Claude Code and say "cut this cataract surgery". The skill:

1. **Maps** the video into timestamped frame sheets and measures motion, scene cuts and colour saturation per second.
2. **Looks** at the sheets (Claude's vision) and lists which phases are present, with start and end: paracentesis, main incision, viscoelastic, capsulorhexis, hydrodissection, phaco, I/A, IOL implantation, wound hydration. Off-eye time and idle stretches are flagged.
3. **Asks you**, phase by phase, which speed you want: 1x real time, 2x, 4x or cut. Closed options, one click each. A lecture preset and an "everything 4x" preset exist if you don't want to go phase by phase.
4. **Renders** a 16:9 lecture version with the phase name burned in at the start of each segment, and a 9:16 reel built from the phases you kept in real time.

Nothing is decided for you except removing time when the camera is off the eye, and even that is a question. Patient identifiers on microscope overlays are masked before any export.

Example run on a 9:47 phaco: 13 phases detected, 44 s of dead time removed, 3:18 lecture and 46 s reel. Total interaction: 4 rounds of clicks.

## Install

Requires macOS or Linux with `ffmpeg` and Python 3.10+.

```bash
git clone https://github.com/maurogobira19-png/cataract-surgery-cuts ~/.claude/skills/cataract-surgery-cuts
python3 -m venv ~/.claude/skills/cataract-surgery-cuts/venv
~/.claude/skills/cataract-surgery-cuts/venv/bin/pip install pillow
```

Or, in the Claude desktop app: Settings → Skills → Add → upload `SKILL.md` (the scripts still need to live in the folder above).

## Use

In Claude Code, attach or reference the raw surgery video and say any of:

- "cut my cataract surgery"
- "edit this phaco, lecture and reel"
- "speed up the phaco, keep the rhexis in real time"

Claude runs `scripts/analyze.py`, reads the sheets, asks the questions, writes `edl.json` and runs `scripts/render.py`.

You can also use the scripts by hand:

```bash
venv/bin/python scripts/analyze.py raw.mp4 ~/Documents/Surgeries/CASE-01 --interval 5
# read the sheets, write edl.json (see assets/edl_example.json)
venv/bin/python scripts/render.py ~/Documents/Surgeries/CASE-01/edl.json
```

## Structure

```
SKILL.md                 workflow Claude follows (map → look → ask → render → check)
scripts/analyze.py       frame sheets with timestamps, motion, scene cuts, off-eye candidates
scripts/render.py        EDL → segments at chosen speeds with burned titles → concat (16:9 or 9:16)
assets/phases.md         how each phaco phase looks on a frame, suggested speeds, titles
assets/edl_example.json  EDL of a routine phaco
```

## Rules baked into the skill

- No patient identification leaves the pipeline. Overlays are masked or cropped; output names are case codes.
- No phase is invented. Ambiguous ranges get a denser sheet before anything is listed.
- Speed is the surgeon's decision. Suggested defaults are marked "Recommended" but always asked.
- The surgeon approves the cut list before the final render.

## License

MIT. This is a video-editing aid; it does not make clinical decisions.
