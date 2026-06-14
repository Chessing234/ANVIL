"""Vivid scene descriptions for future UI rendering."""

from __future__ import annotations

from agents.teaching.narrative_types import Character, Setting


def describe_setting(setting: Setting) -> str:
    """Return a vivid prose description of the setting."""

    prop_blob = ", ".join(setting.props) if setting.props else "standard SOC furniture"
    return (
        f"{setting.location} — {setting.time_description}. The room feels {setting.mood}: "
        f"{prop_blob} anchor the space while monitors wash everything in cool cyan light."
    )


def describe_action(action: str, characters: list[Character]) -> str:
    """Describe a dynamic beat involving the listed characters."""

    names = ", ".join(c.name for c in characters) if characters else "the team"
    styles = ", ".join({c.dialogue_style for c in characters}) if characters else "focused"
    return (
        f"{names} move in coordinated urgency as they {action}. "
        f"The interplay of dialogue styles ({styles}) keeps the moment human, not Hollywood."
    )


def describe_discovery(finding: str) -> str:
    """Heighten a discovery beat without inventing technical falsehoods."""

    return (
        "The room hushes—notification chimes stack into silence. "
        f"On screen, the decisive clue resolves: {finding.strip()} "
        "You let the implication land: defenders must act on evidence, not adrenaline."
    )
