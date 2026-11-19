"""Render brand/icon.png and icon@2x.png (generic projector glyph)."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "sony_adcp_projector" / "brand"


def render(size: int) -> Image.Image:
    scale = 4  # supersample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = s / 64
    # Light beam
    d.polygon(
        [(40 * u, 25 * u), (62 * u, 8 * u), (62 * u, 50 * u), (40 * u, 33 * u)],
        fill=(255, 196, 64, 150),
    )
    # Body
    d.rounded_rectangle([4 * u, 18 * u, 46 * u, 42 * u], radius=6 * u, fill=(36, 41, 51, 255))
    # Lens
    d.ellipse([28 * u, 21 * u, 46 * u, 39 * u], fill=(20, 24, 31, 255))
    d.ellipse([32 * u, 25 * u, 42 * u, 35 * u], fill=(90, 170, 255, 255))
    d.ellipse([34.5 * u, 27 * u, 37.5 * u, 30 * u], fill=(225, 240, 255, 255))
    # Vents and status LED
    for i in range(3):
        d.rounded_rectangle(
            [9 * u, (24 + i * 5) * u, 22 * u, (26 + i * 5) * u],
            radius=1 * u,
            fill=(80, 88, 102, 255),
        )
    d.ellipse([9 * u, 37 * u, 11.5 * u, 39.5 * u], fill=(60, 220, 120, 255))
    # Feet
    d.rounded_rectangle([9 * u, 42 * u, 15 * u, 46 * u], radius=1 * u, fill=(36, 41, 51, 255))
    d.rounded_rectangle([35 * u, 42 * u, 41 * u, 46 * u], radius=1 * u, fill=(36, 41, 51, 255))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    render(256).save(OUT / "icon.png", optimize=True)
    render(512).save(OUT / "icon@2x.png", optimize=True)
    print("wrote", OUT)
