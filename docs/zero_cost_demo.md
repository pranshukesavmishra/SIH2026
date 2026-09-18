# Zero-cost physical demo (₹0) — optional, NOT in the pitch deck

The pitch is software-only and the deck never mentions hardware — that is
deliberate and stays. But if judges at a table ask "can it see a *real*
light?", this five-minute demo answers with equipment you already own.

## What you need (₹0)
- Any laptop with a webcam (or a USB webcam).
- Any smartphone with a flashlight **strobe/blink app** set near **4 Hz**
  (search the app store for "strobe light" / "flashlight blink"; most
  torch apps have a strobe slider). A smartwatch torch also works.
- Optional decoy: a second phone with its torch **steady on**.

## Run it
```
pip install opencv-python numpy
python tools/webcam_beacon_demo.py --blink 4
```
Stand 3–6 m away, point the blinking phone at the webcam.

## What the audience sees
- The blinking phone gets a **green ring: BEACON CONFIRMED** with its
  blink score.
- The steady phone / room lights / a window get a **red ring** — bright,
  but rejected, because they carry no 4 Hz signature.

## What to SAY while it runs (the whole point)
> "This is the same identity test our tracker uses in the simulator.
> Brightness is not identity — *modulation* is. A star, a sun glint, a
> decoy can all be brighter than the beacon; none of them blink at the
> agreed rate. In 64 randomised campaign runs the tracker locked a wrong
> target **zero** times, and this is why."

Keep it framed as a *principle demo*, not the product: the product is the
full virtual testbed with the closed loop, the mount model and the
measured campaign.

## Why we did not buy the ₹6–7k rig
The problem statement asks for algorithm development and validation
**without optical hardware** — a pan-tilt rig demonstrates a servo, not
the algorithm. The webcam demo shows the one physical claim worth
proving (blink-signature identity) for free. If a physical pointing stage
is ever wanted later: the cheapest respectable route is a laser pointer
on the phone + this script driving a screen crosshair (still ₹0), before
any motorised mount.

## Video references (search these — links rot, terms don't)
- YouTube: "free space optical communication demo laser"  
- YouTube: "Li-Fi flashlight data transmission demo"  
- YouTube: "laser communication between two Arduino" (shows the beacon/
  modulation idea with hobby parts, if you ever want the next step)
