from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_IMAGES = ROOT / "static" / "images" / "public"


MAX_WIDTHS = {
    "principal-portrait.jpeg": 960,
    "principal-portrait-large.jpeg": 1200,
}


def optimized_width(path: Path, width: int) -> int:
    if path.name in MAX_WIDTHS:
        return min(width, MAX_WIDTHS[path.name])
    if width > 1800:
        return 1600
    if width > 1400:
        return 1440
    return width


def optimize_image(path: Path) -> dict[str, int | str]:
    before = path.stat().st_size
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        width, height = image.size
        target_width = optimized_width(path, width)
        if target_width < width:
            target_height = int(height * (target_width / width))
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

        suffix = path.suffix.lower()
        if suffix == ".png":
            image.save(path, optimize=True)
        else:
            image.save(
                path,
                quality=84,
                optimize=True,
                progressive=True,
                subsampling="4:2:0",
            )
    after = path.stat().st_size
    return {
        "name": path.name,
        "before": before,
        "after": after,
        "saved": before - after,
    }


def main() -> None:
    targets = sorted(
        path for path in PUBLIC_IMAGES.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    results = [optimize_image(path) for path in targets]
    total_before = sum(item["before"] for item in results)
    total_after = sum(item["after"] for item in results)
    print(
        {
            "files": len(results),
            "before": total_before,
            "after": total_after,
            "saved": total_before - total_after,
            "largest_savings": sorted(results, key=lambda item: item["saved"], reverse=True)[:8],
        }
    )


if __name__ == "__main__":
    main()
