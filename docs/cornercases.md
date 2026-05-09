
# Exploring corner cases
```alon-context
aliases:
  1: Alice
  2: Beth
  3: Isabella
  sd: shoots Dan
  ss: stands still
  sh: stay home
  ha: hits Alice
  masd: manipulates Alice into shooting Dan
  q: Dan dies
math_preamble: |
  % --- ALOn system names ---
  \newcommand{\alon}{\mathcal{ALO}_n}
  \newcommand{\alonm}{\mathcal{M}}
  % --- Model components ---
  \newcommand{\dbt}{\mathcal{T}}
  \newcommand{\hists}{\mathcal{H}^T}
  \newcommand{\mhists}[1]{\mathcal{H}^T_\mathrm{#1}}
  \newcommand{\moments}{M}
  \newcommand{\actions}{\mathcal{A}}
  \newcommand{\prop}{\mathcal{P}}
  % --- Indices and projections ---
  \newcommand{\idx}[2]{#1/#2}
  \newcommand{\mh}{m/h}
  \newcommand{\proj}[2]{#1|_{#2}}
  \newcommand{\wildcard}{{\star}}
  % --- Action and agent functions ---
  \newcommand{\act}[1]{\mathsf{act}(#1)}
  \newcommand{\agents}[1]{\mathsf{agents}(#1)}
  \newcommand{\sucs}[1]{\mathsf{succ}(#1)}
  \newcommand{\opp}[1]{\mathsf{opp}(#1)}
  \newcommand{\unopp}[2]{\mathsf{UnOpp}(#1,#2)}
  % --- Do operators ---
  \newcommand{\mydo}[2]{\mathsf{do}(#1,#2)}
  \newcommand{\mydos}[1]{\mathsf{do}(#1)}
  \newcommand{\myDo}[1]{\mathsf{Do}(#1)}
  % --- Temporal operator ---
  \newcommand{\X}{\mathbf{X}}
  % --- Results-in relation ---
  \newcommand{\resultsin}{\mathrel{\raisebox{-0.23ex}{\boxplus}\!\!\!\!\rightarrow}}
  % --- Causal notions ---
  \newcommand{\bfCause}[2]{\mathsf{bfC}(#1,#2)}
  \newcommand{\nessCause}[2]{\mathsf{nsC}(#1,#2)}
```
{{page_break}}
# Aliases
These aliases are used throughout.

{{alias_table}}

{{page_break}}

# Minimal cases
Let's consider a super minimal case: 1 agent and 1 action.


```mermaid
---
title: 1 agent, 1 action degerate model.
description: T
type: DBT
actions:
  1:
    - sd
aliases:
  1: Alice
  q: Dan dies
---
classDiagram
direction BT

  m --> m1 : h1({sd1})
  m1: q
```

In the "standard" model structure we use, the fact that there is only one complete group action (CGA) means we have only 1 history (ALOn supports models where the same CGA has multiple outcomes, but that doesn't preclude *this* model). Thus, there are no alternatives and `Xq` is settled true (i.e., `[]Xq` is true at `m/h1`). This precludes strong or plain responsibility as they require `~[]Xq`. Given that `sd1` is the only action that happens, it seems it must be part of an actual cause. Indeed, it seems natural to argue that `but(sd1, q)` is true at `m/h1` because if `sd1` doesn't happen *nothing* happens.

One might say that it is vacuously true. One could argue that since there are no alternatives that everything is determined and nothing is "caused by a choice", though then it's questionable why the non-necessitated test is in `res` and `sres` instead of `but` and `ness`. Indeed, this suggests that actual causation can and should happen in determined settings.

Either way, it seems that if `but(sd1, q)` is true here, then `ness(sd1, q)` should likewise be true. After all, `{sd1}` is sufficient and it couldn't be more minimal. Or could it? Let's look at what the reasoner has to say:

{{results ness_empty_sufficient="true"}} 

Surprisingly, `but(sd1, q)` is true but `ness(sd1, q)` is false. 

If we look at the definition of `but`:

$$  \bfCause{\vec a}{\phi} := \X\phi \wedge \bigvee_{\begin{array}{c}\scriptstyle{
        \vec b\in \vec A}\\[-0.8ex] \scriptstyle{\vec a\sqsubseteq\vec b}
    \end{array}}
  \left (\mydos{\vec b} \wedge \bigwedge_{\vec c\in\vec A } \proj{\vec c}{I}\neq \proj{\vec a}{I}\rightarrow [\proj{\vec b}{\bar I}\oplus \proj{\vec c}{I}]\neg\phi  \right ),$$  where $I:= \agents{\vec a}$.

{{results ness_empty_sufficient="false"}} 