# Phacoemulsification phases: how to recognize them on the frame sheets

The "suggested speed" column is only what appears marked as Recommended in the question. The
surgeon decides, phase by phase.

| # | Phase | What the frame shows | Suggested speed | Suggested title |
|---|-------|----------------------|-----------------|-----------------|
| 0 | Prep / field | Speculum going in, field being positioned, microscope focusing | cut (or 8x if it is the opening) | — |
| 1 | Paracentesis | Thin 15° blade at the corneal periphery, side entry | 1x | Paracentesis |
| 2 | Main incision | 2.2/2.4/2.75 mm keratome in a corneal tunnel, usually temporal | 1x | Main incision 2.2 mm |
| 3 | Viscoelastic | Cannula injecting, anterior chamber deepening | 3x | Viscoelastic |
| 4 | Capsulorhexis | Cystotome or Utrata forceps, circular flap being pulled, sometimes trypan blue | 1x (most-watched phase) | Continuous curvilinear capsulorhexis |
| 5 | Hydrodissection | Cannula under the capsule, fluid wave passing behind the nucleus, nucleus rotates | 1x | Hydrodissection |
| 6 | Phaco (sculpt / chop) | Phaco tip, blue/grey sleeve, chopper in the other hand, groove or fragments | 2x (1x on the first chop and on any event) | Phaco: divide-and-conquer / stop-and-chop |
| 7 | Fragment removal | Quadrants being aspirated, chamber emptier | 2x | Fragments |
| 8 | Irrigation/aspiration (I/A) | I/A tip, cortex being pulled from the periphery | 4x | Cortical I/A |
| 9 | Capsule polishing | I/A on the posterior capsule, fine movement, clean chamber | 4x | Polishing |
| 10 | IOL implantation | Cartridge/injector entering, lens unfolding, haptics rotating | 1x | IOL implantation |
| 11 | Viscoelastic removal | I/A behind the lens, lens centering | 4x | Viscoelastic removal |
| 12 | Wound hydration / closure | Cannula at the incisions, stromal whitening, leak test | 2x | Wound hydration |
| 13 | End | Clean field, speculum coming out | cut | — |

## Events that become their own phase in the question round (suggestion 1x)
- Posterior capsule rupture, vitreous in the chamber, dropped fragment
- Rhexis running out and rescue (Brazilian technique, Little maneuver)
- Iris prolapse, floppy iris syndrome
- Loose zonules, capsular tension ring
- Any maneuver the surgeon asked to highlight

## Off-eye time / dead time (cut by default, the surgeon may keep it at 8x)
- Instrument exchange with hands out of the field for more than 3 s
- Microscope focus/zoom adjustment
- Repeated viscoelastic top-ups
- Irrigation pauses with no instrument in the eye

## Vertical 9:16 (1080x1920), 30 to 45 s
Order that works: 1) hook = the most striking frame (IOL unfolding, rhexis closing, or the event),
2) incision 3 s, 3) rhexis 6 s, 4) phaco 8 s at 2x, 5) IOL 6 s, 6) clean final frame.
Short titles, one line, and the technique name in the first title - if the surgeon asked for titles
at all.

Framing (`vertical_fit`): `hybrid` is the default (a 3:4 window on a blurred backdrop); `fit` puts
the whole frame on the backdrop and cannot lose the eye; `crop` gives the biggest image but throws
away 44% of the width, so it only works when the eye is genuinely centred. Whichever is used, give
each segment its own `"center": [cx, cy]`, read off the sheets: in a phaco recording the eye
routinely sits anywhere from 0.3 to 0.7 of the width, and the middle of the frame is often not the
middle of the eye.
