"""
Generate ultra-clean, studio-quality transparent PNGs from image.png:
- Perfectly cuts the circular radar scope at radius 264px centered at (400, 400) with 2px anti-aliased edge.
- Perfectly cuts the text 'ZERODRIFT' and subtitle with anti-aliased edge and color restoration.
"""
from PIL import Image
import numpy as np

def process_logo(input_path):
    img = Image.open(input_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    h, w, _ = arr.shape

    # Background color baseline
    bg = np.array([0.6, 3.6, 15.6], dtype=np.float32)

    # 1. Radar Scope Mask (Center: 400, 400, Radius: 263.5 px)
    cx, cy = 400.0, 400.0
    Y, X = np.ogrid[:h, :w]
    dist_from_radar = np.sqrt((X - cx)**2 + (Y - cy)**2)
    
    # Smooth anti-aliasing edge between 262.5 and 264.5
    radar_alpha = np.clip((264.0 - dist_from_radar) / 1.5, 0.0, 1.0)
    radar_alpha = np.where(X < 680, radar_alpha, 0.0)

    # 2. Text Mask (Right Side: x >= 680)
    rgb = arr[:, :, :3]
    diff = np.linalg.norm(rgb - bg, axis=2)
    
    # Soft alpha for text with smooth anti-aliased transition
    text_alpha = np.clip((diff - 6.0) / 15.0, 0.0, 1.0)
    text_alpha = np.where(X >= 680, text_alpha, 0.0)

    # Un-multiply foreground color on text to prevent dark fringe
    unmixed_rgb = np.zeros_like(rgb)
    for c in range(3):
        a_norm = np.clip(text_alpha, 0.01, 1.0)
        unmixed = (rgb[:, :, c] - bg[c] * (1.0 - a_norm)) / a_norm
        unmixed_rgb[:, :, c] = np.clip(unmixed, 0.0, 255.0)

    # Combine alpha & RGB
    final_alpha = np.maximum(radar_alpha, text_alpha)
    final_rgb = np.where(X[:, :, None] < 680, rgb, unmixed_rgb)
    
    rgba_arr = np.dstack([
        final_rgb.astype(np.uint8),
        (final_alpha * 255.0).astype(np.uint8)
    ])
    full_logo = Image.fromarray(rgba_arr, mode="RGBA")

    # Crop full logo to content bounding box
    bbox = full_logo.getbbox()
    print(f"Content bbox: {bbox}")
    pad = 16
    cropped_bbox = (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(w, bbox[2] + pad),
        min(h, bbox[3] + pad)
    )
    cropped_logo = full_logo.crop(cropped_bbox)

    # Extract clean square emblem of the radar (padded)
    emblem_pad = 10
    emblem_bbox = (
        max(0, int(cx - 264 - emblem_pad)),
        max(0, int(cy - 264 - emblem_pad)),
        min(w, int(cx + 264 + emblem_pad)),
        min(h, int(cy + 264 + emblem_pad))
    )
    emblem = full_logo.crop(emblem_bbox)

    # Save to all target locations
    targets = [
        "src/fsoc_pat/web/logo.png",
        "public/logo.png",
        "docs/brand/logo_banner.png",
        "docs/media/logo_full.png"
    ]
    for p in targets:
        cropped_logo.save(p, "PNG")
        print(f"Saved full banner logo to {p} (size: {cropped_logo.size})")

    emblem_targets = [
        "src/fsoc_pat/web/logo_emblem.png",
        "public/logo_emblem.png",
        "docs/brand/logo_emblem.png",
        "docs/media/logo_emblem.png"
    ]
    for p in emblem_targets:
        emblem.save(p, "PNG")
        print(f"Saved emblem to {p} (size: {emblem.size})")

    fav_targets = [
        "src/fsoc_pat/web/favicon.png",
        "public/favicon.png"
    ]
    fav = emblem.resize((64, 64), Image.Resampling.LANCZOS)
    for p in fav_targets:
        fav.save(p, "PNG")
        print(f"Saved favicon to {p}")

if __name__ == "__main__":
    process_logo("image.png")
