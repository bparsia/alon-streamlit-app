# Manipulation Cases in ALOn with varying temporal modal depths

ALOn allows, within a moment, for agents to interfere with each other. Following the general approach of STIT logics where *within* a moment agents cannot *preclude* other agent's choices, this interference cannot *preclude* another agent from essaying an action
. Thus, if Alice has a choice at a moment to shoot Dan or stand still, it must be possible for her to do either no matter what any other agent might do at a moment. Thus, if Beth has the choice whether to stand still or hit Alice's arm (to mess up her shot) then all four combinations of Alice's and Beth's actions must be possible at that moment. Unlike in standard STIT logics, since the agents are choosing between actions and not (sets of) histories, there is conceptual leeway for actions to interfere with *how they play out*. Thus, if Alice shoots (at) Dan but Beth jostles her arm throwing off her aim, Dan will live. Dan will also live if Alice decides to stand still.

This is a significant departure from standard STIT. In STIT logics, choices (or "choice cells") are sets of histories. Compatibility of choices cashes out as every intersection of choice cells must be non-empty. Since a STIT claim such as `[alice stit]danisdead` (Alice sees to it that Dan is dead) individuate history sets by *their common ensured proposition*. Thus, `[alice stit]danisdead` and `[beth stit]~danisdead` are inconsistent choices, because no matter how we allocate histories to the corresponding choice cells, their intersection must be empty.
^["Accordingly, a formula like do(ai ) means that agent i is carrying out an action of type a, without this implying anything about his success or failure in doing so. The important point is that it makes perfect sense to say that an agent is doing something even if, in the end, she fails because of some external opposition." quote from Ilaria]

[discuss the semantic difference between direct stit and the alon defined stit]



```alon-context
aliases:
  1: Alice
  2: Beth
  3: Isabella
  sd: shoots Dan
  ss: stands still
  ha: hits Alice
  masd: manipulates Alice into shooting Dan
  q: Dan dies
```

# Aliases
These aliases are used throughout.

{{alias_table}}

{{page_break}}

# Example 3.1 from Where Responsibility Takes You

We can formalise our initial example in ALOn (following the presentation in Where Responsibility Takes You.) (See the Alias table above to map the logical symbols into their intended readings.)

```mermaid
---
title: Example 3.1 from Where Responsibility Takes You
description: This is a minimal specification of the corresponding model with all histories except h1 left implicit. Thus, the naming of the other histories might be different than in the book, but the results are the same. Of note is that since we do full responsibility analysis we get results for group {1,2} which has quite a bit of responsibility.
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
opposings:
  sd1:
    - ha2
---
classDiagram
direction BT
  class m {
  }
  m --> m1 : h1({sd1, ss2})
  m --> m2 : h2({sd1, ha2})
  m --> m3 : h3({ss1, hs2})
  m --> m4 : h4({ss1, ha2})
  m1: q
  m2: ~q
  m3: ~q
  m4: ~q  
```


{{action_table}}

{{opposing_table}}

{{page_break}}

# Isabella Manipulation Example (TD=2)

Here's an attempt to model a multistep manipulation case. Critically, the manipualation is fully determinative, i.e., it's a compulsion. After the manipulation, Alice has no choice but to shoot Dan.  However, *without** manipulation Alice is still free to choose whether to shoot Dan. In the Isabella not manipulating case, possible histories play out as in Example 3.1.

```mermaid
---
title: Isabella Manipulation Example (TD=2)
description: Isabella manipulates Alice into shooting Dan. Chained responsibility across two temporal stages.
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
  3:
    - ss
    - masd
opposings:
  sd1:
    - ha2
evaluate:
  - - m/h1
    - do(sd1)
  - - mA/h1
    - q
---
classDiagram
direction BT

  m --> mA : h1/h2({masd3})
  m --> mB : h3/h4/h5/h6({ss3})

  mA --> m1 : h1({sd1, ss2})
  mB --> m2 : h2({sd1, ha2})

  mB --> m3 : h3({sd1, ss2})
  mB --> m4 : h4({sd1, ha2})
  mB --> m5 : h5({ss1, ss2})
  mB --> m6 : h6({ss1, ha2})

  mA: do(sd1)
  m1: q
  m2: ~q
  m3: q
  m4: ~q
  m5: ~q
  m6: ~q
```

{{model_overview}}

## Actions and opposings

{{action_table}}

{{opposing_table}}

## Analysis

There are several points of potential interest. First, we can check the situation where Isabella doesn't manipulate. We might expect that learning that Isabella did nothing to affect Alice or Beth should leave our earlier judgements of their causal responsibility untouched. Which it does:

{{results eval="m/h1" target="do(sd1)"}} 


we can ask if Isabella is responsible for Alice's shooting of Dan:

{{results eval="m/h1" target="do(sd1)"}} 

{{page_break}}

# Isabella Manipulation Example 2 (TD=2)

T

```mermaid
---
title: Isabella Manipulation Example 2(TD=2)
description: In this case, Alice doesn't shoot Dan *unless* Isabella manipulates her into it.
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
  3:
    - ss
    - masd
opposings:
  sd1:
    - ha2
aliases:
  1: Alice
  2: Beth
  3: Isabella
  sd: shoots Dan
  ss: stands still
  ha: hits Alice
  masd: manipulates Alice into shooting Dan
  q: Dan dies

evaluate:
  - - m/h1
    - do(sd1)
  - - mm/h1
    - q
---
classDiagram
direction BT

  m --> mm : h1/h2({masd3})
  m --> mmm : h3/h4/h5/h6({ss3})

  mm --> m1 : h1({sd1, ss2})
  mm --> m2 : h2({sd1, ha2})

  mmm --> m5 : h5({ss1, ss2})
  mmm --> m6 : h6({ss1, ha2})

  mm: do(sd1)
  m1: q
  m2: ~q
  m5: ~q
  m6: ~q

```
{{model_overview}}

## Actions and opposings

{{action_table}}

{{opposing_table}}

## Analysis

{{results}}

# Weird, TD=1 Isabella case
```mermaid
---
title: Example 3.1 from Where Responsibility Takes You
description: This is a minimal specification of the corresponding model with all histories except h1 left implicit. Thus, the naming of the other histories might be different than in the book, but the results are the same. Of note is that since we do full responsibility analysis we get results for group {1,2} which has quite a bit of responsibility.
type: DBT
actions:
  1:
    - sd
    - ss
  2:
    - ss
    - ha
  3:
    - ss
    - masd
opposings:
  sd1:
    - ha2
  ss1:
    - masd3
aliases:
  1: Alice
  2: Beth
  3: Isabella
  sd: shoots Dan
  ss: stands still
  ha: hits Alice
  masd: manipulates Alice to shoot dan
  q: Dan dies
---
classDiagram
direction BT
  class m {
  }
  m --> m1 : h1({sd1, ss2, ss3})
  m --> m1b : h1b({sd1, ss2, masd3})
  m --> m2 : h2({sd1, ha2, ss3})
  m --> m2b : h2b({sd1, ha2, masd3})
  m --> m3 : h3({ss1, ss2, ss3})
  m --> m3b : h3b({ss1, ss2, masd3})
  m --> m4 : h4({ss1, ha2, ss3})
  m --> m4b : h4b({ss1, ha2, masd3})

  m1: q
  m1b: q
  m2: ~q
  m2b: ~q
  m3: ~q
  m3b: q
  m4: ~q 
  m4b: q 
```