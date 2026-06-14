"""CRUD facades grouped by aggregate root."""

from database.crud import agents, evidence, incidents, investigations, knowledge, lessons, students

__all__ = [
    "agents",
    "evidence",
    "incidents",
    "investigations",
    "knowledge",
    "lessons",
    "students",
]
