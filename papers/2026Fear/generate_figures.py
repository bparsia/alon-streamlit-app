"""
Regenerate paper figure images from their source .mmd model files via
mermaid-cli (mmdc), so the images in a paper's images/ directory are
pipeline-sourced rather than one-off manual exports.

FIGURES below maps each output image (relative to a target images/ dir)
to the source model file (relative to MODELS_DIR) that generates it,
which named style to render with (see figure_styles/), and any mmdc
flags specific to that figure (e.g. --scale).

Styles live in figure_styles/*.yaml, loaded by STYLES below:
- "mermaid_default": no config injected, mermaid.js's own defaults.
- "latex_matched": neutral/serif polish with a `font` field, meant to
  match whatever font the target paper's LaTeX actually renders with
  -- NOT always Computer Modern; use detect_tex_font() or pass a font
  explicitly, don't assume. See figure_styles/latex_matched.yaml and
  project_mermaid_render_pipeline memory for the full recipe/gotchas
  (fontFamily must be a top-level config: key, not nested under
  themeVariables -- silently ignored there).

FONT_FOR_TEX_PACKAGE maps a LaTeX font package (detected via regex
against a .tex file's \\usepackage/\\RequirePackage lines) to an
installed system font name mermaid can use. Deliberately small and
explicit -- an unrecognized/uninstalled font fails loudly rather than
silently substituting something wrong (this bit us once already: an
earlier version of this script defaulted every paper to
NewComputerModern without checking, which was simply wrong for a
mathptmx/Times paper).

Usage:
  cd papers/2026Fear && ../../.venv/bin/python3 generate_figures.py <images_dir> [--tex-font-from <main.tex>]

Requires `npx @mermaid-js/mermaid-cli` to be available.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

MODELS_DIR = Path(__file__).parent / "models"
STYLES_DIR = Path(__file__).parent / "figure_styles"

FIGURES = {
    "example_3.1_diagram.png": {
        "source": "3.1.mmd",
        "style": "latex_matched",
        "scale": "2",
    },
}

# LaTeX font package -> installed system font name for mermaid's fontFamily.
# Only fonts actually confirmed installed (via `fc-list`) belong here.
FONT_FOR_TEX_PACKAGE = {
    "mathptmx": "Times New Roman",
    "newtxtext": "Times New Roman",
    "mathpazo": "Palatino",
    "newpxtext": "Palatino",
    "libertine": None,  # not installed -- add here once it is
    "charter": "Charter",
    "newtx": "Times New Roman",
}

# No font package found at all -> plain LaTeX default (Computer Modern).
DEFAULT_TEX_FONT = "NewComputerModern"


def detect_tex_font(tex_path: Path) -> str:
    """Scan a .tex file's \\usepackage/\\RequirePackage lines (and, for a
    main.tex, any \\input/\\documentclass-referenced .cls in the same dir)
    for a known font package, return the matching installed font name.

    Raises if a font package is found but has no known/installed mapping
    -- silently falling back to a wrong font is worse than erroring.
    """
    texts = [tex_path.read_text()]
    cls_match = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", texts[0])
    if cls_match:
        cls_path = tex_path.parent / f"{cls_match.group(1)}.cls"
        if cls_path.exists():
            texts.append(cls_path.read_text())

    pkg_re = re.compile(r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]+)\}")
    found = []
    for text in texts:
        for line in text.splitlines():
            for m in pkg_re.finditer(line):
                for pkg in m.group(1).split(","):
                    found.append(pkg.strip())

    for pkg in found:
        if pkg in FONT_FOR_TEX_PACKAGE:
            font = FONT_FOR_TEX_PACKAGE[pkg]
            if font is None:
                raise ValueError(
                    f"Detected font package {pkg!r} but no installed font is "
                    f"mapped for it in FONT_FOR_TEX_PACKAGE -- install one and "
                    f"add the mapping, or pass --font explicitly."
                )
            return font

    return DEFAULT_TEX_FONT


def load_style(name: str, font_override: str = None) -> str:
    """Return the mermaid config block (verbatim YAML text, or "" for no
    config) for a named style, with {font} substituted if the style has
    a `font` field.
    """
    path = STYLES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No such figure style: {path}")
    spec = yaml.safe_load(path.read_text()) or {}
    config_text = spec.get("config", "")
    if not config_text:
        return ""
    font = font_override or spec.get("font", DEFAULT_TEX_FONT)
    return config_text.format(font=font)


def with_config(mmd_text: str, config_block: str) -> str:
    """Insert a mermaid config: block into the model's existing YAML
    frontmatter. ALOn .mmd files start with
    `---\\n<frontmatter>\\n---\\n<diagram body>`. mermaid.js merges its
    own `config:` key alongside ALOn's own keys (title/description/
    opposings/aliases/etc.) in the same frontmatter block without
    conflict -- confirmed in project_mermaid_render_pipeline memory.
    """
    if not config_block:
        return mmd_text
    if not mmd_text.startswith("---\n"):
        raise ValueError("Expected .mmd file to start with '---' frontmatter delimiter")
    end = mmd_text.index("\n---\n", 4)
    frontmatter, rest = mmd_text[4:end], mmd_text[end:]
    return f"---\n{frontmatter}\n{config_block}{rest}"


def render(source: Path, out_path: Path, scale: str, config_block: str) -> None:
    configured = with_config(source.read_text(), config_block)
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
    args = sys.argv[1:]
    if not args:
        print("Usage: generate_figures.py <images_dir> [--tex-font-from <main.tex>]", file=sys.stderr)
        sys.exit(1)

    images_dir = Path(args[0])
    images_dir.mkdir(parents=True, exist_ok=True)

    font_override = None
    if len(args) > 1:
        if args[1] != "--tex-font-from" or len(args) < 3:
            print("Usage: generate_figures.py <images_dir> [--tex-font-from <main.tex>]", file=sys.stderr)
            sys.exit(1)
        font_override = detect_tex_font(Path(args[2]))
        print(f"Detected font: {font_override}", file=sys.stderr)

    for image_name, spec in FIGURES.items():
        source = MODELS_DIR / spec["source"]
        if not source.exists():
            raise FileNotFoundError(f"Model source not found: {source}")
        out_path = images_dir / image_name
        config_block = load_style(spec.get("style", "mermaid_default"), font_override)
        print(f"Rendering {source.name} -> {out_path} (style={spec.get('style', 'mermaid_default')})...", file=sys.stderr)
        render(source, out_path, spec.get("scale", "1"), config_block)

    print(f"Wrote {len(FIGURES)} figure(s) to {images_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
