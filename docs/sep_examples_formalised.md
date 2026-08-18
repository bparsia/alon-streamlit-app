# Examples from the Standford Encyclopedia of Philosophy (SEP)

The article [Causation in the Law](https://plato.stanford.edu/entries/causation-law/) contains a narrative, highly selective collection of "usage facts about how “causation” is used in resolving the problems that arise in particular cases". In particular, it claims:

> With considerable selectivity, some simplification, and little claim to completeness, sixteen facts are below selected as salient in the legal usage of the concept of causation.

We use this collection as a (limited) test of the representational adequacy of our variant of ALOn. 

1. Causation is ubiquitous in the law’s prohibitions of actions because the causative verbs of action (such as, “killing”) imply causation of some harm such as death by an act; and conversely (if controversially—Byrne, 2021,2022), causation of such harms imply that such an action as killing has taken place.

N/A because we don't define "killing" or any such connection to death. We could potentially to the controversial converse, but in an annoying way given the propositional nature. I.e., we cannot classify actions with additional decorators or have implications between actions (each agent group can only do *one* action.) We could have something like `akd` ("Alice's shooting of dan was a killing") and e.g., `but(sd1, akd) v ness(sd1, akd) -> q`. It'd be nicer if we had some variables and could populate things a bit better.

2. In cases of actions rather than omissions, usually (but not always—see the discussion below of the action-overdetermination cases) if the harm did not counterfactually depend on the defendant’s action, then the defendant is not liable for that harm because he is not said to have caused it (American Law Institute 1962).

Example 3.1? But maybe not because but/ness of beth's action? Or maybe looking at the other histories would illustrate  this?

3. If the defendant’s act does not increase the probability of some harm occurring, and particularly if that act decreases such probability, then the defendant is not liable for that harm because he is not said to have caused it, even if that harm’s occurrence counterfactually depended on the defendant’s action (Oxendine v. State; Johnson, 2021).

Cannot handle it usefully. You really want probabilitstic notions of causation here. The counterfactuals are rather different.

4. With regard to liability for omissions, usually there is no liability for omitting to prevent some harm even in cases where there is counterfactual dependence of the occurrence of that harm on that omission; yet sometimes (the status, undertaking, and causing of peril exceptions) there is such liability (so long as the occurrence of the harm counterfactually depends on such omission; Dressler 1995: 466–467).

Example 3.1 I think. We need to discuss how res/sres are liability operators. Not sure about "the status, undertaking, and causing of peril exceptions" 

5. With regard to liability for “double preventions” (where, for example, a defendant prevents a lifeguard from preventing another from drowning), often there is a supposedly cause-based liability for the unprevented harm in such cases because a defendant preventing a preventer from preventing some harm is regarded as the cause of that harm (Skow, 2022, calls these “interrupting” double prevention cases). Yet sometimes (for double preventions amounting to the “allowings” as conceived by the centuries-old doing/allowing distinction) double preventions are treated just like omissions so that there is no legal causation and no liability except for those exceptional circumstances (the status, undertaking, and causing of peril exceptions) that exist for omission liability (Moore 2009a: 61–65, 459–460).

Complex. Need to break out the example and consider opposings vs. multiple moments.

6. In cases of probability-raising actions, omissions, and doubly-preventative actions, there is occasionally and inconsistently still no liability for harms that counterfactually depend on such actions, omissions, and double preventions if such harm does not also counterfactually depend on that aspect of those actions, etc., that made the defendant culpable.

Same as 3.

7. There is a complex pattern of liability for multiple cause cases involving actions: 
    a. First, in ordinary, garden-variety concurrent cause cases (two or more factors individually necessary and only jointly sufficient for some harm), there is commonly liability even though the defendant’s act is but one of many causal factors producing a harm and such liability is full (“joint and several”) individual liability of such co-causing joint tort-feasors in torts and co-causing principals in criminal law. 
    b. Second, in the symmetrical overdetermination variety of concurrent cause cases (where two or more factors are individually sufficient and only jointly necessary for some harm), there is universally liability where the acts of each of two or more culpable defendants is independently sufficient (and thus not individually necessary) for the harm, and there is almost always liability where the sufficient condition alternative to the defendant’s action is not the act of another human agent but is a natural event or condition such as an avalanche. 
    c. Third, there is also liability in mixed cases (“mixed” between overdetermination and garden variety concurrent cause cases in that there are three or more factors, any two of which are sufficient for the harm, meaning no factor is individually necessary for that harm; Johnson 2016). 
    d. Fourth, there is also liability in asymmetrical overdetermination concurrent cause cases, these being cases where one factor is sufficient and other factors are neither individually necessary nor individually sufficient, such liability uniformly being imposed for the big cause (the sufficient factor) and non-uniformly and inconsistently being imposed for the little causes (the insufficient and unnecessary factors; Wright 1985b). 
    e. Fifth, in the pre-emptive variety of multiple cause cases (where one sufficient factor pre-empts another equally sufficient factor from operating on this occasion), there is liability for the pre-empting sufficient factor but there is no liability for the pre-empted sufficient factor.

8. There is also a complex pattern of liability for a harm in multiple cause cases involving omissions that is different than it is for actions, even when we restrict our gaze to omission cases where there is a legal duty on each omitter not to omit to prevent that harm: 
    a. First, there is liability on each omitter in ordinary, garden-variety, concurrent omission cases just as there is in multiple cause cases involving actions and not omissions. 
    b. Second, predominantly (but not universally) there is no liability for the overdetermination variety of concurrent omissions—this is universally true where one of the absences sufficient for the occurrence of the harm is natural, not human, and it is predominantly true where all of the absences individually sufficient for the occurrence of the harm are the omissions of culpable human actors (Fisher 1992; Abrams, 2022). 
    c. Third, there are no pre-emptive omission cases because such cases are conceptually impossible, and thus any liability questions here are moot (Moore 2011b: 479–482; 2013: 342–348; Abrams, 2022).

9. There is also a complex pattern of liability for a harm in multiple cause cases involving double preventions rather than actions or omissions, and this pattern of liability is different yet again than it is in cases of actions or omissions: First there is liability in ordinary, garden-variety, concurrent double-prevention cases just as there is for actions and omissions. Second, there is predominantly (but not universally) no liability for the overdetermination variety of concurrent double-preventions—this is universally true where one of the doubly-preventative acts sufficient for the occurrence of the harm is a natural event, not a culpable human action, and it is predominantly true where all doubly-preventative acts sufficient for the occurrence of the harm are the actions of culpable human actors (Moore 2009a: 466–467). Third, unlike in omission cases, there is such a thing as a pre-emptive double prevention case; in such cases, there is liability for the pre-empting double prevention but not for the pre-empted action that would otherwise have been a double prevention (Moore 2011b).

10. Liability exists for harms caused by a defendant even though such harms would not have occurred but for the victim’s freakishly abnormal condition so long as that condition pre-existed the defendant’s action (this is the common law’s “thin-skulled man” or “you take your victim as you find him” maxim).

11. Yet no liability exists for harms in part caused by a defendant if that harm was also in part caused by a freakishly large natural event that intervened between the defendant’s act and the harm that he in part caused (the “vis major” part of the common law’s “superseding cause” doctrine; Larremore 1909).

12. There is no liability for harms due to a “coincidence” (defined as a freakishly unusual conjunction of events) even though such harms would not have occurred but for the defendant’s culpable action, so long as that coincidence is not used by the defendant as a means to bringing about the harm (another part of the common law’s “superseding cause” doctrine; Hart & Honoré 1959, 1985).

13. Intention has supposed aphrodisiac powers to extend legally relevant causal influence to what otherwise would be legally remote events (the “no harm is too remote if intended” maxim of the common law; Terry 1914: 17; Knobe and Shapiro 2021: 205–206).

14. Under the intervening human actor branch of the common law’s superseding cause doctrine, there is no liability if a subsequent human actor (rather than a natural event) intervenes to “break the causal chain” otherwise existing (because of counterfactual dependence) between the harm and the defendant’s earlier act, where that intervening actor:

   - Acts subsequently to defendant’s act, and is thus not a co-causer of the harm.
   - Does an act that is causally significant with respect to the harm.
   - Acts independently of any motive to so act supplied by the defendant.
   - Acts with great culpability in bringing about the harm (usually intentionally or sometimes recklessly, but not merely negligently, with respect to the harm).
   - Acts voluntarily in the narrow, technical sense of the law, namely, the relevant bodily movements are not reflexive, done while asleep, unconscious, in shock, under hypnosis, or otherwise not the product of the defendant’s will.
   - Acts voluntarily in the sense that he is not coerced by threats, by natural necessity, or by the compunctions of legal duty.
   - Is a responsible agent (not very young, insane, or very drunk).

15. The set of doctrines presupposing scalarity of the causal relation as that relation is used in law (Moore 2009a: 65–76, 118–123):

   - The use of “strength of causal connection” as one factor (along with degrees of fault) in apportioning liability in multiple cause cases in torts, of particular importance in strict liability cases where liability does not depend on fault (American Law Institute 2010: sec. 6).
   - The seeming dependence on degree of causal contribution to license use of the balance of evils defense in cases of aiding nature or other persons to cause harm, and in the redirection of force cases.
   - The puzzling use of something like degree of causal contribution to license the balance of evils defense in the acceleration cases (cases where the defendant merely accelerates a harm that was about to happen anyway).
   - The “petering out” of degrees of causal contribution in cases of simple spatio-temporal remoteness.
16. The absence of liability in the freakish route cases even when a harm counterfactually depends on the defendants act, including both cases where the route is freakish vis-à-vis the defendant’s plans or expectation, and cases where the route is freakish to an outside observer.


Moore, Michael, "Causation in the Law", The Stanford Encyclopedia of Philosophy (Spring 2024 Edition), Edward N. Zalta & Uri Nodelman (eds.), URL = <https://plato.stanford.edu/archives/spr2024/entries/causation-law/>.