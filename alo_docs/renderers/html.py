"""HTML renderer — standalone HTML document with mermaid.js diagrams
and per-model copy buttons.
"""

from __future__ import annotations
import html as _html

import markdown as _md

from ..document import ALOnDocument, ContextBlock, ModelBlock, TextBlock, HeadingBlock, FenceBlock
from .. import shortcodes
from .._extract import model_to_mmd


_MERMAID_SCRIPT = """\
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    mermaid.initialize({startOnLoad: false, theme: 'neutral'});
    mermaid.run();
  });
</script>"""

_COPY_BUTTON_SCRIPT = """\
<script>
function alonCopy(btn) {
  const src = btn.getAttribute('data-mmd');
  navigator.clipboard.writeText(src).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}
</script>"""

_STYLE = """\
<style>
body { max-width: 900px; margin: auto; padding: 2em; font-family: sans-serif; }
h1, h2, h3, h4, h5, h6 { margin-top: 1.4em; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #ccc; padding: 4px 10px; }
th { background: #f4f4f4; }
code { background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }
pre { background: #f4f4f4; padding: 1em; border-radius: 4px; overflow-x: auto; }
.alon-model-wrap { position: relative; margin: 1.5em 0; }
.alon-copy-btn {
  position: absolute; top: 4px; right: 4px;
  font-size: 0.75em; padding: 2px 8px;
  background: #f0f0f0; border: 1px solid #ccc;
  border-radius: 3px; cursor: pointer; z-index: 10;
}
.alon-copy-btn:hover { background: #e0e0e0; }
pre.mermaid { background: none; padding: 0; }
</style>"""

_MD = _md.Markdown(extensions=["tables", "fenced_code"])


def _md_to_html(text: str) -> str:
    _MD.reset()
    return _MD.convert(text)


def render(doc: ALOnDocument, title: str = "ALOn Document", analysis=None) -> str:
    """Render *doc* as a standalone HTML document."""
    parts = [
        "<!DOCTYPE html>",
        "<html><head>",
        f"<title>{_html.escape(title)}</title>",
        '<meta charset="utf-8">',
        _STYLE,
        _MERMAID_SCRIPT,
        _COPY_BUTTON_SCRIPT,
        "</head>",
        "<body>",
    ]

    for idx, block in enumerate(doc.blocks):

        if isinstance(block, ContextBlock):
            pass  # suppress

        elif isinstance(block, ModelBlock):
            if block.display:
                mmd_src = model_to_mmd(block)
                escaped = _html.escape(mmd_src).replace("'", "&#39;")
                parts.append(
                    f'<div class="alon-model-wrap">\n'
                    f'<button class="alon-copy-btn" '
                    f'data-mmd=\'{escaped}\' '
                    f'onclick="alonCopy(this)">Copy .mmd</button>\n'
                    f'<pre class="mermaid">\n{block.diagram}\n</pre>\n'
                    f'</div>'
                )
            # else: hidden model — available for analysis/reference, not rendered

        elif isinstance(block, HeadingBlock):
            text = _html.escape(block.text)
            parts.append(f"<h{block.level}>{text}</h{block.level}>")

        elif isinstance(block, FenceBlock):
            parts.append(block.raw)

        elif isinstance(block, TextBlock):
            expanded = shortcodes.expand(block.content, doc, idx, analysis=analysis)
            parts.append(_md_to_html(expanded))

    parts.append("</body></html>")
    return "\n".join(parts)
