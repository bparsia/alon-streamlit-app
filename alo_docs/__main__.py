"""CLI entry point: python -m alo_docs <subcommand> [options]

Subcommands
-----------
build   Parse + resolve + render a document to stdout or a file.
extract Extract self-contained mermaid blocks from a document.

Examples
--------
    python -m alo_docs build paper.md                   # markdown to stdout
    python -m alo_docs build paper.md -f html -o out.html
    python -m alo_docs extract paper.md                 # all models to stdout
    python -m alo_docs extract paper.md -o models/      # one file per model
"""

from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_') or 'model'


def _load(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


# ──────────────────────────────────────────────────────────────────────────────
# build
# ──────────────────────────────────────────────────────────────────────────────

def cmd_build(args: argparse.Namespace) -> None:
    from . import parser as _parser, resolver as _resolver
    from .renderers import markdown as _md_renderer, html as _html_renderer

    text = _load(args.input)
    doc  = _resolver.resolve(_parser.parse(text))

    analysis = None
    if args.run_analysis:
        from ._runner import run_doc_analysis
        print("Running analysis…", file=sys.stderr)
        analysis = run_doc_analysis(doc)

    fmt = args.format.lower()
    if fmt == 'html':
        title = Path(args.input).stem.replace('_', ' ').title()
        rendered = _html_renderer.render(doc, title=title, analysis=analysis)
    else:
        rendered = _md_renderer.render(doc, show_context=args.show_context,
                                       analysis=analysis)

    if args.output:
        Path(args.output).write_text(rendered, encoding='utf-8')
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(rendered)


# ──────────────────────────────────────────────────────────────────────────────
# extract
# ──────────────────────────────────────────────────────────────────────────────

def cmd_extract(args: argparse.Namespace) -> None:
    from ._extract import extract_models
    from . import parser as _parser, resolver as _resolver

    text    = _load(args.input)
    doc     = _resolver.resolve(_parser.parse(text))
    models  = doc.models()
    mmds    = extract_models(text)   # pre-rendered strings

    if not models:
        print("No ALOn models found.", file=sys.stderr)
        return

    out_dir = Path(args.output) if args.output else None

    for idx, (block, mmd) in enumerate(zip(models, mmds)):
        name = _slugify(block.title) if block.title else f"model_{idx+1}"
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = out_dir / f"{name}.mmd"
            dest.write_text(mmd, encoding='utf-8')
            print(f"  {dest}", file=sys.stderr)
        else:
            header = f"# {block.title or name}" if len(models) > 1 else ""
            if header:
                print(header)
            print(mmd)
            if idx < len(models) - 1:
                print()


# ──────────────────────────────────────────────────────────────────────────────
# argument parser
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        prog='python -m alo_docs',
        description='ALOn document preprocessor',
    )
    sub = ap.add_subparsers(dest='cmd', required=True)

    # build
    bp = sub.add_parser('build', help='Render a document')
    bp.add_argument('input', help='Input markdown file')
    bp.add_argument('-f', '--format', default='markdown',
                    choices=['markdown', 'html'],
                    help='Output format (default: markdown)')
    bp.add_argument('-o', '--output', default=None,
                    help='Output file (default: stdout)')
    bp.add_argument('--show-context', action='store_true',
                    help='Include alon-context blocks as HTML comments')
    bp.add_argument('--run-analysis', action='store_true',
                    help='Run responsibility analysis and expand {{results}} shortcodes')
    bp.set_defaults(func=cmd_build)

    # extract
    ep = sub.add_parser('extract', help='Extract self-contained model blocks')
    ep.add_argument('input', help='Input markdown file')
    ep.add_argument('-o', '--output', default=None,
                    help='Output directory (default: print to stdout)')
    ep.set_defaults(func=cmd_extract)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
