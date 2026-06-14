"""LangGraph-compatible state machine with SQLite checkpointing."""

from __future__ import annotations

import operator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Annotated, Any, Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph


class GraphState(TypedDict, total=False):
    """Canonical graph state shared across tutorial workflows."""

    messages: Annotated[list[Any], operator.add]
    current_step: str
    data: dict[str, Any]
    errors: Annotated[list[str], operator.add]
    metadata: dict[str, Any]


GraphNode = Callable[[GraphState], dict[str, Any] | GraphState]
Condition = Callable[[GraphState], str]


class StateMachine:
    """Thin wrapper over ``StateGraph`` with SQLite-backed checkpointing."""

    def __init__(self, checkpoint_path: str | Path) -> None:
        self._checkpoint_path = Path(checkpoint_path)
        self._builder = StateGraph(GraphState)
        self._compiled: Any | None = None
        self._checkpointer: SqliteSaver | None = None
        self._checkpointer_cm: AbstractContextManager[Any] | None = None

    def add_node(self, name: str, func: GraphNode) -> None:
        """Register a processing node.

        Args:
            name: Unique node identifier.
            func: Callable accepting graph state and returning updates.
        """

        self._builder.add_node(name, func)

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add a deterministic edge between nodes.

        Args:
            from_node: Source node or ``\"START\"`` sentinel.
            to_node: Destination node or ``\"END\"`` sentinel.
        """

        resolved_from = START if from_node == "START" else from_node
        resolved_to = END if to_node == "END" else to_node
        self._builder.add_edge(resolved_from, resolved_to)

    def add_conditional_edge(
        self,
        from_node: str,
        condition: Condition,
        mapping: dict[str, str],
    ) -> None:
        """Add a router that selects the next node based on ``condition``."""

        self._builder.add_conditional_edges(from_node, condition, mapping)

    def compile(self) -> Any:
        """Compile the graph with a SQLite checkpointer for durable state."""

        if self._compiled is not None:
            return self._compiled
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._checkpointer_cm = SqliteSaver.from_conn_string(str(self._checkpoint_path))
        self._checkpointer = self._checkpointer_cm.__enter__()
        self._compiled = self._builder.compile(checkpointer=self._checkpointer)
        return self._compiled

    def close(self) -> None:
        """Release SQLite resources held by the checkpointer context."""

        if self._checkpointer_cm is not None:
            self._checkpointer_cm.__exit__(None, None, None)
            self._checkpointer_cm = None
        self._checkpointer = None
        self._compiled = None

    def run(self, initial_state: dict[str, Any], thread_id: str = "default") -> dict[str, Any]:
        """Execute the graph while persisting checkpoints after each step.

        Args:
            initial_state: Starting graph payload.
            thread_id: Identifier used for checkpoint isolation.

        Returns:
            Dictionary with ``final_state`` and ``trace`` keys.
        """

        try:
            graph = self.compile()
            config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
            trace: list[dict[str, Any]] = []
            for chunk in graph.stream(initial_state, config=config):
                trace.append(
                    {
                        key: dict(value) if hasattr(value, "items") else value
                        for key, value in chunk.items()
                    },
                )
            snapshot = graph.get_state(config)
            final_state = dict(snapshot.values) if snapshot.values is not None else initial_state
            return {"final_state": final_state, "trace": trace}
        finally:
            self.close()
