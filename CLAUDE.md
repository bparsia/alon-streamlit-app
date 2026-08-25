# Instructions for Claude

## Reasoner performance — do not hypothesize

Do not speculate about *why* a reasoner (Konclude, pyDatalog, or any other)
is fast, slow, or behaves a certain way. You do not have good instincts
here and have been wrong repeatedly and confidently (e.g. claiming Rosetta
translation explained a performance change, when the "fast" baseline was
*also* under Rosetta; claiming a small ontology "shouldn't" benefit from
multithreading, when a direct test showed it did, ~3x).

- If a timing or behavior needs explaining, run the actual isolated
  comparison and report the measured numbers. Don't reach for a plausible-
  sounding cause first.
- If you haven't tested something, say "I don't know, want me to test it"
  — not "this is probably because X."
- The user will ask for a hypothesis if they want one. Don't volunteer one.
