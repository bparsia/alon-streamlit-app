"""
Query generation for automated responsibility analysis.

This module provides functionality to automatically generate responsibility
queries from a declarative configuration, eliminating the need to manually
enumerate all agent/coalition combinations.
"""

import re
from dataclasses import dataclass
from typing import Literal
from itertools import combinations


def _sanitize_id(s: str) -> str:
    """Sanitize a formula string for use in a query ID.

    Replaces characters that are invalid in Datalog predicate names or
    awkward in display (parentheses, spaces, braces, colons, commas) with
    underscores, then collapses runs of underscores.
    """
    result = re.sub(r'[(){}\[\],: ]', '_', s)
    result = re.sub(r'_+', '_', result)
    return result.strip('_')

from .model.core import ALOModel, Query


@dataclass
class ResponsibilityConfig:
    """Configuration for automated responsibility analysis."""

    target_proposition: str
    """The proposition to analyze responsibility for (e.g., 'q')"""

    agents: list[str] | Literal["all"]
    """Agents to analyze: 'all' or specific list like ['1', '3']"""

    groups: Literal["all", "singletons"] | list[list[str]] | str
    """
    Coalition specification:
    - 'singletons': only individual agents
    - 'all': all possible coalitions (power set - empty)
    - 'size<=k': coalitions up to size k (e.g., 'size<=2')
    - [[1,3], [2,4]]: explicit list of coalitions
    """

    responsibility_types: list[str]
    """
    Types of responsibility to check: ['pres', 'sres', 'res', 'dsxtit', 'but', 'ness']
    - pres: Potential responsibility ([A pres]φ)
    - sres: Strong responsibility ([A sres]φ)
    - res: Responsibility ([A res]φ)
    - dsxtit: DxStit ([A dsxtit]φ)
    - but: But-for causation (but(action, φ)) - automatically uses agent's action from history
    - ness: NESS causation (ness(action, φ)) - automatically uses agent's action from history

    Note: but/ness queries are only generated for individual agents (singletons), not coalitions,
    and require the agent to have an action specified in the named history.
    """

    history: str = "h1"
    """History to evaluate at (default: h1)"""


class QueryGenerator:
    """Generates responsibility queries from configuration."""

    def generate_queries(self, model: ALOModel, config: ResponsibilityConfig) -> list[Query]:
        """
        Generate all responsibility queries based on config.

        Args:
            model: The ALon model
            config: Responsibility analysis configuration

        Returns:
            List of Query objects ready for serialization
        """
        # Generate agent/coalition sets
        agent_sets = self._generate_agent_sets(model, config)

        # Generate responsibility queries for each set
        queries = self._generate_responsibility_queries(
            agent_sets,
            config.responsibility_types,
            config.target_proposition,
            model,
            config.history
        )

        return queries

    def _generate_agent_sets(self, model: ALOModel, config: ResponsibilityConfig) -> list[list[str]]:
        """
        Generate list of agent coalitions based on config.

        Examples:
            'singletons' → [['1'], ['2'], ['3']]
            'all' → [['1'], ['2'], ['3'], ['1','2'], ['1','3'], ['2','3'], ['1','2','3']]
            'size<=2' → [['1'], ['2'], ['3'], ['1','2'], ['1','3'], ['2','3']]
            [['1','3'], ['2']] → [['1','3'], ['2']]  (explicit list)

        Args:
            model: The ALon model
            config: Responsibility configuration

        Returns:
            List of agent sets (each set is a list of agent IDs)
        """
        # Determine which agents to consider
        if config.agents == "all":
            agents = sorted(model.agents_actions.keys())
        else:
            agents = sorted(config.agents)

        # Generate coalitions based on groups specification
        if config.groups == "singletons":
            return [[a] for a in agents]

        elif config.groups == "all":
            # Power set excluding empty set
            all_sets = []
            for r in range(1, len(agents) + 1):
                all_sets.extend(combinations(agents, r))
            return [list(s) for s in all_sets]

        elif isinstance(config.groups, str) and config.groups.startswith("size<="):
            # Limited size coalitions
            max_size = int(config.groups.split("<=")[1])
            all_sets = []
            for r in range(1, min(max_size + 1, len(agents) + 1)):
                all_sets.extend(combinations(agents, r))
            return [list(s) for s in all_sets]

        else:
            # Explicit list of coalitions
            return config.groups

    def _generate_responsibility_queries(
        self,
        agent_sets: list[list[str]],
        resp_types: list[str],
        prop: str,
        model: ALOModel,
        history: str
    ) -> list[Query]:
        """
        Generate responsibility queries for each agent set × responsibility type.

        Supported responsibility types:
        - pres: Potential responsibility ([A pres]φ)
        - sres: Strong responsibility ([A sres]φ)
        - res: Responsibility ([A res]φ)
        - dsxtit: DxStit ([A dsxtit]φ)
        - but: But-for causation (but(action, φ)) - uses agent's action from history
        - ness: NESS causation (ness(action, φ)) - uses agent's action from history

        For but/ness: Looks up which action each agent performed in the designated
        history and generates causal queries for those actions. Only works for
        individual agents (singletons), not coalitions.

        Args:
            agent_sets: List of agent coalitions
            resp_types: Responsibility types to generate
            prop: Target proposition
            model: The ALon model (needed for but/ness to look up actions)
            history: History name to look up actions from (e.g., "h1")

        Returns:
            List of Query objects
        """
        queries = []

        # Get the designated history's group action (for but/ness lookups)
        history_action = model.named_histories.get(history) if history in model.named_histories else None

        for agent_set in agent_sets:
            # Format agent set for expression
            if len(agent_set) == 1:
                agent_expr = agent_set[0]
            else:
                agent_expr = "{" + ", ".join(agent_set) + "}"

            # Generate ID suffix
            agent_id_suffix = "_".join(agent_set)

            for resp_type in resp_types:
                # Modal responsibility types: [A resp_type]φ
                if resp_type in ["pres", "sres", "res", "dsxtit", "dxstit"]:
                    # Parser requires uppercase DXSTIT (with X not S)
                    if resp_type in ["dsxtit", "dxstit"]:
                        modal_op = "DXSTIT"
                    else:
                        modal_op = resp_type
                    expr = f"[{agent_expr} {modal_op}]{prop}"
                    prop_id = _sanitize_id(prop)
                    query_id = f"q_{resp_type}_{agent_id_suffix}_{prop_id}"
                    queries.append(Query(formula_string=expr, query_id=query_id))

                # Causal responsibility types: but(action, φ) / ness(action, φ)
                elif resp_type in ["but", "ness"]:
                    if len(agent_set) == 1:
                        # Individual agent
                        agent_id = agent_set[0]

                        # Look up which action this agent performed in the history
                        if history_action and agent_id in history_action.actions:
                            action_type = history_action.actions[agent_id]
                            action_id = f"{action_type}{agent_id}"  # e.g., "sd1"

                            expr = f"{resp_type}({action_id}, {prop})"
                            query_id = f"q_{resp_type}_{action_id}_{_sanitize_id(prop)}"
                            queries.append(Query(formula_string=expr, query_id=query_id))
                        else:
                            # Warn if can't find action, but don't error
                            print(f"Warning: Cannot generate {resp_type} query for agent {agent_id} - "
                                  f"action not found in history {history}")
                    else:
                        # Coalition/group - generate joint action query
                        # Check if all agents in the coalition performed actions in this history
                        if history_action and all(agent_id in history_action.actions for agent_id in agent_set):
                            # Build joint action expression: {1:sd, 2:ss} (grammar: NUMBER:IDENTIFIER)
                            mappings = [f"{agent_id}:{history_action.actions[agent_id]}"
                                        for agent_id in agent_set]
                            joint_action = "{" + ", ".join(mappings) + "}"

                            expr = f"{resp_type}({joint_action}, {prop})"
                            query_id = f"q_{resp_type}_{'_'.join(agent_set)}_{_sanitize_id(prop)}"
                            queries.append(Query(formula_string=expr, query_id=query_id))

                else:
                    raise ValueError(f"Unknown responsibility type: {resp_type}")

        return queries


def generate_queries(model: ALOModel) -> list[Query]:
    """
    Convenience function to generate queries from a model with responsibility_config.

    Args:
        model: ALOModel with a responsibility_config attribute

    Returns:
        List of generated Query objects

    Raises:
        ValueError: If model doesn't have responsibility_config
    """
    if not hasattr(model, 'responsibility_config') or not model.responsibility_config:
        raise ValueError("Model must have a responsibility_config attribute to generate queries")

    generator = QueryGenerator()
    return generator.generate_queries(model, model.responsibility_config)
