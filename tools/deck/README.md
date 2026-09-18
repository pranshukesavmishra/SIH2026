# Deck artwork — slides 2, 4 and 5

The submission deck (`docs/submission/ZeroDrift_SIH26169.pdf`) is six pages on
the official SIH 2026 Idea template. Slides 1, 3 and 6 are the team's own
PowerPoint work and are carried through untouched. Slides 2, 4 and 5 are
rendered here instead, because they needed to be diagram-led rather than
paragraph-led.

| File | What it is |
|---|---|
| `slide2.html` | IDEA TITLE — four-step SEE / IDENTIFY / PREDICT / STEER strip, the 4 Hz blink gate, live-console proof |
| `slide4.html` | FEASIBILITY AND VIABILITY — proof tiles, risk → strategy pairs with measured evidence, worst-case band |
| `slide5.html` | IMPACT AND BENEFITS — link-closure hero (14.7 % → 99.3 %), what it replaces, benefit tiles |
| `console.png` | Replay console at a locked TRACK frame, 198 µrad — captured by `shoot_console.js` |
| `render_art.js` | Renders one `slideN.html` to `slideN.png` at 2320×1040 CSS px, ×2 (≈360 dpi on the slide) |
| `shoot_console.js` | Drives `docs/console.html`, seeks to a TRACK frame nearest the 198 µrad median, screenshots it |
| `build.py` | Drops the three PNGs into the deck's body area and writes the final PDF |

## Rebuilding

```sh
python -m http.server 8123 --directory docs &     # shoot_console.js needs this
node tools/deck/shoot_console.js                  # → console screenshot
node tools/deck/render_art.js slide2              # also slide4, slide5
python tools/deck/build.py                        # → ZeroDrift_SIH26169.pdf
```

`build.py` takes the previous submission PDF as its base, wipes the body area
of pages 2, 4 and 5 (16, 94)–(944, 510) pt and inserts the new artwork. The
template's header band, section title, logos and page numbers are never
touched, so every mandatory pointer and section header survives. Those pointers
are also written as an invisible text layer, so the rasterised slides still
extract as text.

Two rules the artwork must keep obeying:

- **Six pages.** The "Important Pointers" slide stays out of the exported PDF.
- **Every number traces to a shipped measurement** — see the table in
  `PROJECT_MEMORY.md`. Nothing on these slides is projected.
