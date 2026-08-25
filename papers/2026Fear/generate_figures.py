"""
Regenerate paper figure images from their source .mmd model files via
mermaid-cli (mmdc), so the images in a paper's images/ directory are
pipeline-sourced rather than one-off manual exports.

FIGURES below maps each output image (relative to a target images/ dir)
to the source model file (relative to MODELS_DIR) that generates it, plus
any mmdc flags specific to that figure (e.g. --scale). Add an entry here
whenever a new model needs a rendered diagram in the paper.

PAPER_MERMAID_CONFIG is this paper's visual-polish/font-matching config,
injected into each model's mermaid frontmatter at render time (NOT baked
into the .mmd files themselves, which stay paper-agnostic/reusable).
Confirmed recipe -- see project_mermaid_render_pipeline memory:
- fontFamily must be a top-level key under config:, not nested inside
  themeVariables (silently ignored there).
- "NewComputerModern" matches the FEAR paper's plain Computer Modern
  (EPTCS class declares no font package) -- requires
  `brew install --cask font-new-computer-modern` on the rendering
  machine. A different paper with a different font package needs a
  different value here.

Usage:
  cd papers/2026Fear && ../../.venv/bin/python3 generate_figures.py <images_dir>

Requires `npx @mermaid-js/mermaid-cli` to be available (same as the
confirmed-working mmdc recipe used elsewhere in this project).
"""

import subprocess
import sys
import tempfile
from pathlib import Path

MODELS_DIR = Path(__file__).parent / "models"

FIGURES = {
    "example_3.1_diagram.png": {
        "source": "3.1.mmd",
        "scale": "2",
    },
}

PAPER_MERMAID_CONFIG = """config:
  theme: base
  fontFamily: "NewComputerModern"
  themeVariables:
    primaryColor: "#f5f5f5"
    primaryBorderColor: "#999999"
    primaryTextColor: "#1a1a1a"
    lineColor: "#666666"
    classText: "#1a1a1a"
  class:
    hideEmptyMembersBox: true"""


def with_paper_config(mmd_text: str) -> str:
    """Insert PAPER_MERMAID_CONFIG into the model's existing YAML frontmatter.

    ALOn .mmd files start with `---\\n<frontmatter>\\n---\\n<diagram body>`.
    mermaid.js merges its own `config:` key alongside ALOn's own keys
    (title/description/opposings/aliases/etc.) in the same frontmatter
    block without conflict -- confirmed in project_mermaid_render_pipeline.
    """
    if not mmd_text.startswith("---\n"):
        raise ValueError("Expected .mmd file to start with '---' frontmatter delimiter")
    end = mmd_text.index("\n---\n", 4)
    frontmatter, rest = mmd_text[4:end], mmd_text[end:]
    return f"---\n{frontmatter}\n{PAPER_MERMAID_CONFIG}{rest}"


def render(source: Path, out_path: Path, scale: str) -> None:
    configured = with_paper_config(source.read_text())
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as f:
        f.write(configured)
        temp_path = Path(f.name)
    try:
        cmd = [
            "npx", "@mermaid-js/mermaid-cli",
            "-i", str(temp_path),
            "-o", str(out_path),
            "-b", "white",
            "-s", scale,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"mmdc failed on {source} -> {out_path}:\n{result.stdout}\n{result.stderr}"
            )
    finally:
        temp_path.unlink()


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
