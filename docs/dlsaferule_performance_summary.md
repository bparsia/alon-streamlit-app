# 3.5-scale performance, all reasoning paradigms and variants (91 queries, m/h1/q eval point — 3.5's only eval point, so no eval-point-averaging mismatch between rows)

| Approach | Time | vs. pyDatalog baseline | Correctness | Source |
|---|---|---|---|---|
| **pyDatalog** | **1.423s** | **1.0x (baseline)** | baseline | existing paper table |
| `DLSafeRule` (top-level queries), fully inlined, 0 intermediates | 5.90s | 4.1x slower | exact match | perf-003 |
| SPARQL/MINUS | 7.710s | 5.4x slower | established | existing paper table |
| Plain `SubClassOf`, fully inlined, 0 intermediates | 10.06s | 7.1x slower | exact match | perf-003 |
| OWL/realization, plain `SubClassOf` + `fN` intermediates (standard pipeline) | 42.77s | 30.1x slower | established | perf-002 |
| `DLSafeRule` (top-level queries only), `fN` intermediates left plain | 49.41s | 34.7x slower | exact match | perf-002 |

Still debugging: converting the `fN` intermediate layer itself to `DLSafeRule` (as opposed to converting only top-level query classes, or inlining the intermediates away) produces an inconsistent ontology — a real correctness bug, not a timing data point, so it's excluded from this table. See perf-004.

## Notes

- All rows are the same model (`3.5.mmd`) at its one eval point (`m/h1/q`), so times are directly comparable — no per-eval-point averaging differences to account for.
- pyDatalog and SPARQL/MINUS figures are from the existing `papers/2026Fear/table_performance.tex` pipeline (established, already published/verified).
- The four OWL/realization rows are all from this session's DL-safe-rules investigation (perf-002, perf-003), single runs each (`threads="AUTO"`, arm64 native Konclude build), not repeated for variance.
- Fastest verified-correct approach overall: `DLSafeRule` + full inlining (5.90s) — faster than SPARQL/MINUS (7.71s) on this model, but still ~4x slower than pyDatalog, which remains the fastest approach by a wide margin at this scale.
- perf-002's "no speedup" conclusion (`DLSafeRule` vs plain, both with `fN` intermediates) turned out to be confounded — see perf-002's own corrected README. The real driver of the OWL-side speedup is eliminating the `fN` intermediate classes (inlining), not the `DLSafeRule`/`SubClassOf` distinction by itself; `DLSafeRule` only pulls ahead of plain `SubClassOf` once inlining is also applied (5.90s vs 10.06s).
