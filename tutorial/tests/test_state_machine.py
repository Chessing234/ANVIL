"""Smoke tests for LangGraph state machine wrapper."""

from __future__ import annotations

from pathlib import Path

from core.state_machine import GraphState, StateMachine


def test_state_machine_checkpointed_run(tmp_path: Path) -> None:
    """Graph executes with SQLite checkpoints and returns trace metadata."""

    checkpoint = tmp_path / "graph.sqlite"

    def init_node(state: GraphState) -> dict[str, object]:
        """Initialize workflow metadata."""

        return {"current_step": "initialized", "metadata": {"depth": 1}}

    def finish_node(state: GraphState) -> dict[str, object]:
        """Finalize workflow metadata."""

        return {"current_step": "finished", "metadata": {**state.get("metadata", {}), "depth": 2}}

    machine = StateMachine(checkpoint)
    machine.add_node("init", init_node)
    machine.add_node("finish", finish_node)
    machine.add_edge("START", "init")
    machine.add_edge("init", "finish")
    machine.add_edge("finish", "END")

    initial: GraphState = {
        "messages": [],
        "data": {},
        "errors": [],
        "metadata": {},
    }
    result = machine.run(initial, thread_id="unit-test")
    assert result["trace"]
    assert result["final_state"]["current_step"] == "finished"
