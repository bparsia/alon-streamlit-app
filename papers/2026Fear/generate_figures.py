"""
Regenerate paper figure images from their source .mmd model files via
mermaid-cli (mmdc), so the images in a paper's images/ directory are
pipeline-sourced rather than one-off manual exports.

FIGURES below maps each output image (relative to a target images/ dir)
to the source model file (relative to MODELS_DIR) that generates it, plus
any mmdc flags specific to that figure (e.g. --scale). Add an entry here
whenever a new model needs a rendered diagram in the paper.

Usage:
  cd papers/2026Fear && ../../.venv/bin/python3 generate_figures.py <images_dir>

Requires `npx @mermaid-js/mermaid-cli` to be available (same as the
confirmed-working mmdc recipe used elsewhere in this project).
"""

import subprocess
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

FIGURES = {
    "example_3.1_diagram.png": {
        "source": "3.1.mmd",
        "scale": "2",
    },
}


def render(source: Path, out_path: Path, scale: str) -> None:
    cmd = [
        "npx", "@mermaid-js/mermaid-cli",
        "-i", str(source),
        "-o", str(out_path),
        "-s", scale,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"mmdc failed on {source} -> {out_path}:\n{result.stdout}\n{result.stderr}"
        )


def main():
    if len(sys.argv) != 2:
        print("Usage: generate_figures.py <images_dir>", file=sys.stderr)
        sys.exit(1)

    images_dir = Path(sys.argv[1])
    images_dir.mkdir(parents=True, exist_ok=True)

    for image_name, spec in FIGURES.items():
        source = MODELS_DIR / spec["source"]
        if not source.exists():
            raise FileNotFoundError(f"Model source not found: {source}")
        out_path = images_dir / image_name
        print(f"Rendering {source.name} -> {out_path}...", file=sys.stderr)
        render(source, out_path, spec.get("scale", "1"))

    print(f"Wrote {len(FIGURES)} figure(s) to {images_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
