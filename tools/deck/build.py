"""Rebuild slides 2, 4 and 5 of the ZeroDrift SIH deck.

Pages 1, 3 and 6 of the team's latest deck are kept as they are; the body area
of pages 2, 4 and 5 is replaced with freshly rendered artwork. The official
template's header band, section title, logos and page numbers all survive
untouched, so template integrity is preserved.

Images that the new artwork completely covers are stubbed out, otherwise the
file keeps carrying megabytes of pixels nobody will ever see.
"""
import pymupdf

SRC = "/tmp/deckwork/latest.pdf"
OUT = "/tmp/deckwork/ZeroDrift_SIH26169.pdf"

# body area, in points, on the 960x540 page: below the template header band
# and above the page number in the bottom-right corner.
BODY = pymupdf.Rect(16, 94, 944, 510)
WIPE = pymupdf.Rect(13, 91, 947, 513)

ART = {1: "/tmp/deckwork/art/slide2.png",
       3: "/tmp/deckwork/art/slide4.png",
       4: "/tmp/deckwork/art/slide5.png"}

doc = pymupdf.open(SRC)

# 1x1 white pixel that stands in for every image the artwork hides
stub = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1, 1), False)
stub.set_rect(stub.irect, (255, 255, 255))

hidden = set()
for idx in ART:
    for info in doc[idx].get_image_info(xrefs=True):
        xref = info.get("xref", 0)
        if xref and pymupdf.Rect(info["bbox"]) in WIPE:
            hidden.add(xref)

# never stub anything the preserved pages still rely on
keep = set()
for idx in (0, 2, 5):
    for info in doc[idx].get_image_info(xrefs=True):
        keep.add(info.get("xref", 0))
hidden -= keep

freed = 0
for xref in sorted(hidden):
    try:
        freed += len(doc.extract_image(xref)["image"])
        doc[min(ART)].replace_image(xref, pixmap=stub)
    except Exception as exc:
        print("  skipped xref", xref, exc)

# the artwork is raster, so mirror its wording as an invisible text layer —
# the deck stays searchable and every mandatory template pointer still extracts.
LAYER = {
    1: ["Proposed Solution (Describe your Idea/Solution/Prototype)",
        "The eyes and neck of a laser-communication terminal",
        "Detailed explanation of the proposed solution",
        "1 SEE - a physics-true sky: stars, cloud, clutter and sun-glint rendered through the same "
        "optics as the beacon, on a real ISS orbit. 9.2 MPx/s, 30 fps, SGP4 orbit.",
        "2 IDENTIFY - the beacon proves who it is by blinking at an agreed 4 Hz. A brighter star "
        "cannot fake it. 0 wrong locks in 64 runs.",
        "3 PREDICT - an IMM motion model plus a Smith predictor aim where the beacon will be. "
        "40 ms of mount delay cancelled.",
        "4 STEER - pan-tilt commands go out every frame, 30 per second. 8-21 ms of the 33 ms budget.",
        "Innovation and uniqueness of the solution",
        "Brightness is not identity - modulation is. A star or sun-glint scores approximately zero on "
        "the 4 Hz gate and is rejected; the beacon scores 0.47 and is locked.",
        "How it addresses the problem",
        "Measured: 1.27 s to acquire, 98.3 % lock held, 0/64 wrong locks, median 198 urad."],
    3: ["Analysis of the feasibility of the idea",
        "73/73 automated tests pass on every push. 64/64 randomised runs acquired the beacon. "
        "0 wrong locks across all 64 runs. 8-21 ms of the 33 ms frame on two CPU cores - "
        "no GPU, no cloud, no dataset.",
        "Potential challenges and risks",
        "Heavy turbulence; bright decoys and sun-glint; 40 ms of mount latency; sharp UAV manoeuvres.",
        "Strategies for overcoming these challenges",
        "Coast through the fade then re-acquire (hard-turbulence run 1.27 s, 94.3 % lock); 4 Hz "
        "blink-signature hard gate plus AI verifier (0 wrong locks / 64, AUC 0.957 vs 0.900); "
        "two-path Smith predictor (4.2 urad steady lag at 0.75 deg/s); dual-model IMM estimator.",
        "Worst case of all 64 randomised runs: slowest acquisition 4.0 s, lowest lock retention "
        "91.6 %, a 0.53x dim beacon under 1.74x turbulence still acquired in 2.8 s. One command "
        "regenerates every figure."],
    4: ["Potential impact on the target audience",
        "Does the optical link actually close? Coarse alignment alone closes it 14.7 % of the time; "
        "coarse plus a modelled fine steering stage closes it 99.3 % - 6.8x more link time. "
        "Tracked ISS pass, 250 urad beam, 15 cm aperture, 3.1 dB mean margin, zero outages. "
        "Measured against ground truth the tracker never sees.",
        "What it replaces: an optical test bench costing lakhs of rupees, versus ZeroDrift at zero "
        "cost on a laptop you already own.",
        "Benefits of the solution (social, economic, environmental, etc.)",
        "STRATEGIC - sovereign FSOC pointing capability for India's space and defence links. "
        "ECONOMIC - a laptop replaces lakhs of rupees of hardware at zero recurring cost. "
        "RESEARCH & EDUCATION - any student or ISRO lab can develop and compare PAT algorithms. "
        "SCALABLE & GREEN - one engine covers satellite, UAV, ground and maritime links.",
        "Who it serves: ISRO / IN-SPACe optical-communication teams, DRDO, IITs and engineering "
        "colleges, India's space-tech start-ups."],
}

for idx, art in ART.items():
    page = doc[idx]
    page.draw_rect(WIPE, color=None, fill=(1, 1, 1), overlay=True)
    page.insert_image(BODY, filename=art, keep_proportion=True, overlay=True)
    y = BODY.y0 + 8
    for line in LAYER[idx]:
        page.insert_textbox(pymupdf.Rect(BODY.x0 + 6, y, BODY.x1 - 6, y + 26), line,
                            fontsize=7, fontname="helv", render_mode=3)
        y += 26

doc.save(OUT, garbage=4, deflate=True, clean=True)
print(f"stubbed {len(hidden)} hidden images, freeing {freed/1e6:.2f} MB")
print("pages:", doc.page_count)
doc.close()
