# Index based serialiser

**Status (January 2026)**: This is now the **only** OWL serializer. The legacy ABOX serializer (moment-based, using root individual `m`) was removed after index-based Strategy 2 achieved equivalent correctness (13/14 on key theories).

## Motivation

The old ABOX translator used a branching tree structure with a root named `m`, history properties (e.g., `h1`), and a `succ` superproperty. Successor nodes (`m1`...) represented next moments but also carried other information (e.g., their generating complete group action). Even for 1-step trees (modal depth = 1) this caused confusion. Supporting longer observable chains would have made this worse.

One solution is to use the standard Kripkeization of branching time where individuals represent moment *indicies*, i.e., moment/history pairs. This will lead to there being rather more individuals (e.g., in a 4 history model, instead of 5 individuals, (`m`, `m1`...`m4`), we would have 8 (`m/h1`, `m/h2`, `m/h3`, `m/h4`, `m1/h1`, `m2/h2`, `m3/h3`, `m4/h4`). We would (potentially) have two properties...`same_moment` and `succ` (or `next`). `same_moment` is an equivalence relation which connects all the indicies of a common moment. Thus, e.g.,

```
m/h1 same_moment m/h2.
m/h2 same_moment m/h3.
m/h3 same_moment m/h4.
```

(Since `same_moment` needs to be transitive, reflexive, and symmetric, we just need to connect all indices in the same class.)

And:

```
m/h1 succ m1/h1.
m/h2 succ m2/h2.
m/h3 succ m3/h3.
m/h4 succ m4/h4.
```

Propositions, as before, would occur at the index they were true in. Unlike our prior approach, indicies are members of the action class which happen at them.

So in our one step model, our complete group action class for `h1` would have `m/h1` as an instance, not `m1/h1`, which is more intuitive.

We'd have to adjust our formulae we test against the model. For example,

`do(a)`

Is now just (the class) `a`.

`Xq` goes to `succ some q` (I still think it needs to be `only` but there's some trickery here; `succ` should be serial and functional (I think)).

`~[]Xq` goes to `not same_moment only (succ some q)`. That is, there's some index for a given moment which has a successor which is not q.

The big conceptual advantage is we don't overload the successor relationship and moments. Technically, it makes it easier to add modal depth (I think). 

## (Temporal) modal depth >1 

We do proliferate individuals and I'm not sure reducing properties compensates. Let's consider a model with only 2 histories which branch after the first successor.

```
m/h1 same_moment m/h2.
m1/h1 same_modment m1/h2.
m2/h1. # No other indicies for m2
m3/h2. # No other indicies for m3

m/h1 succ m1/h1.
m/h2 succ m1/h2.
m1/h1 succ m2/h1.
m1/h2 succ m3/h2.
```

Now we can talk about formulae with higher modal depth, e.g.,

`XXq` goes to `succ some (succ some q)` (true at `m/h1` if `m2/h1` is in `q`).

