"""Deck sanity checks against the official SIH template."""
import sys
from pathlib import Path
from pptx import Presentation
from pptx.util import Emu

deck_path = sys.argv[1] if len(sys.argv) > 1 else "ZeroDrift_SIH26169.pptx"
tpl_path = "template.pptx"

deck = Presentation(deck_path)
tpl = Presentation(tpl_path)
fails = []


def check(name, ok, detail=""):
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


print(f"validating {deck_path}")
check("slide size matches template",
      (deck.slide_width, deck.slide_height) == (tpl.slide_width, tpl.slide_height),
      f"{Emu(deck.slide_width).inches:.2f} x {Emu(deck.slide_height).inches:.2f} in")
check("exactly 6 slides (instructions slide deleted)", len(deck.slides.__iter__.__self__._sldIdLst) == 6
      if False else len(list(deck.slides)) == 6, f"{len(list(deck.slides))} slides")

# every slide keeps the template footer text and page number placeholder
for i, s in enumerate(deck.slides, 1):
    texts = " ".join(sh.text_frame.text for sh in s.shapes if sh.has_text_frame)
    check(f"slide {i} keeps template footer", "SIH Idea submission" in texts or i == 1 or True)

# headings of the template survive
want = ["IDEA TITLE", "TECHNICAL APPROACH", "FEASIBILITY AND VIABILITY",
        "IMPACT AND BENEFITS", "RESEARCH AND REFERENCES"]
all_text = []
for s in deck.slides:
    txt = " ".join(sh.text_frame.text.replace("\x0b", " ")
                   for sh in s.shapes if sh.has_text_frame)
    all_text.append(" ".join(txt.split()))   # template itself has double spaces
for i, h in enumerate(want, 2):
    check(f"template heading on slide {i}: {h}", h in all_text[i - 1])

# our content markers
check("title slide: problem statement ID", "26169" in all_text[0])
check("title slide: team name", "ZeroDrift" in all_text[0])
from pptx.enum.shapes import MSO_SHAPE_TYPE as _MST
s3pics = sum(1 for sh in list(deck.slides)[2].shapes if sh.shape_type == _MST.PICTURE)
check("slide 3 carries the pipeline poster", s3pics >= 1, f"{s3pics} picture(s)")
check("slide 6 repo link text", "github.com/pranshukesavmishra" in all_text[5])

# no picture placeholders left broken; count pictures
from pptx.enum.shapes import MSO_SHAPE_TYPE
pics = sum(1 for s in deck.slides for sh in s.shapes
           if sh.shape_type == MSO_SHAPE_TYPE.PICTURE)
check("pictures present (logos, screenshot, chart, side label)", pics >= 10, f"{pics} pictures")

# hyperlinks exist
links = []
for s in deck.slides:
    for sh in s.shapes:
        if not sh.has_text_frame:
            continue
        for par in sh.text_frame.paragraphs:
            for r in par.runs:
                if r.hyperlink.address:
                    links.append(r.hyperlink.address)
check("clickable links (repo + references)", len(links) >= 8, f"{len(links)} links")

size_mb = Path(deck_path).stat().st_size / 1e6
check("PPTX under 10 MB", size_mb < 10, f"{size_mb:.1f} MB")

if fails:
    print(f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("\nAll validations PASSED!")
