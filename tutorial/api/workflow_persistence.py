"""Persist LangGraph defense/teaching outputs into the primary SQL database."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import evidence as evidence_crud
from database.crud import incidents as incidents_crud
from database.crud import investigations as investigations_crud
from database.crud import lessons as lessons_crud
from database.models import Evidence, EvidenceType, InvestigationStep, LessonDifficulty
from orchestration.coordinator import TutorialCoordinator
from shared.models import LessonStatus

logger = structlog.get_logger(__name__)

_EVIDENCE_TYPE_MAP: dict[str, EvidenceType] = {
    "memory_dump": EvidenceType.MEMORY,
    "network_capture": EvidenceType.NETWORK,
    "disk_image": EvidenceType.DISK,
    "log_file": EvidenceType.LOG,
}


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return None


def _enrich_accuracy_report(raw: dict[str, Any] | None) -> dict[str, Any]:
    report = dict(raw or {})
    fe = report.get("FIND_EVIL") or {}
    corrections = int(fe.get("self_correction_count", 0))
    report["self_corrections_performed"] = corrections
    avg = float(fe.get("avg_confidence", 0.0))
    report["overall_accuracy_rating"] = "HIGH" if avg >= 0.7 else "MEDIUM"
    return report


def _as_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _best_lesson_status_for_incident(coordinator: TutorialCoordinator, incident_id: str) -> LessonStatus | None:
    """Pick the newest lesson orchestration row that already materialized a ``lesson`` dict."""

    best: LessonStatus | None = None
    for st in coordinator._lessons.values():
        if str(st.ticket.incident_id) != incident_id:
            continue
        if not isinstance((st.latest_state or {}).get("lesson"), dict):
            continue
        if best is None or str(st.ticket.lesson_id) > str(best.ticket.lesson_id):
            best = st
    return best


async def sync_defense_and_teach_post_submit(
    session: AsyncSession,
    incident_id: uuid.UUID,
    coordinator: TutorialCoordinator,
) -> None:
    """Replace prior defense-derived rows and upsert accuracy + auto-generated lesson."""

    inc_str = str(incident_id)
    try:
        status = await coordinator.get_incident_status(inc_str)
    except KeyError:
        logger.warning("sync_skipped_no_orchestration_row", incident_id=inc_str)
        return

    latest = status.latest_state or {}
    if not latest.get("completed"):
        logger.warning("sync_skipped_incomplete_defense", incident_id=inc_str)
        return

    await session.execute(delete(InvestigationStep).where(InvestigationStep.incident_id == incident_id))
    await session.execute(
        delete(Evidence).where(
            Evidence.incident_id == incident_id,
            Evidence.collected_by == "defense_evidence",
        ),
    )

    steps_raw = list(latest.get("investigation_steps") or [])
    corrections: list[dict[str, Any]] = list(latest.get("self_corrections") or [])
    if len(steps_raw) > 3:
        steps_raw = steps_raw[-3:]
        if corrections:
            corrections = corrections[-1:]

    corr_idx = 0
    for raw in steps_raw:
        step = dict(raw)
        step.pop("incident_id", None)
        step.pop("created_at", None)
        step.pop("updated_at", None)
        if "id" in step:
            step["id"] = _as_uuid(step["id"])
        ts = _parse_ts(step.pop("timestamp", None))
        if ts is not None:
            step["timestamp"] = ts
        step.setdefault("tool_used", step.get("tool_used") or "")
        step.setdefault("raw_output", step.get("raw_output") or "")
        step.setdefault("interpretation", step.get("interpretation") or "")
        if step.get("is_self_correction"):
            if corr_idx < len(corrections):
                step["correction_reason"] = str(corrections[corr_idx].get("reason", "Self-correction"))
                corr_idx += 1
            elif not step.get("correction_reason"):
                step["correction_reason"] = "Self-correction"
        step.setdefault("execution_time_ms", 12)
        await investigations_crud.create_step(session, incident_id, step)

    now = datetime.now(timezone.utc)
    seen_hashes: set[str] = set()
    for ev in latest.get("collected_evidence") or []:
        if not isinstance(ev, dict):
            continue
        h = str(ev.get("hash_sha256", ""))
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        et_key = str(ev.get("type") or "memory_dump")
        et = _EVIDENCE_TYPE_MAP.get(et_key, EvidenceType.OTHER)
        meta = dict(ev.get("metadata") or {})
        custody = meta.get("chain_of_custody")
        chain: list[Any]
        if isinstance(custody, list):
            chain = custody
        elif custody is not None:
            chain = [{"entry": custody}]
        else:
            chain = [{"actor": str(ev.get("collected_by", "defense_evidence")), "action": "synthesis"}]
        await evidence_crud.create(
            session,
            incident_id,
            {
                "evidence_type": et,
                "file_path": str(ev.get("file_path", "")),
                "hash_sha256": str(ev.get("hash_sha256", "")),
                "file_size_bytes": int(ev.get("file_size_bytes", 0)),
                "metadata_": meta,
                "collected_by": str(ev.get("collected_by", "defense_evidence")),
                "custody_chain": chain,
                "storage_location": str(ev.get("storage_location", "workflow")),
                "verified_at": now,
            },
        )

    report = _enrich_accuracy_report(latest.get("accuracy_report"))
    await incidents_crud.update_accuracy_report(session, incident_id, report)

    lesson_blob: dict[str, Any] | None = None
    st = _best_lesson_status_for_incident(coordinator, inc_str)
    if st is not None:
        cand = (st.latest_state or {}).get("lesson")
        if isinstance(cand, dict):
            lesson_blob = cand
    if lesson_blob is None:
        rows = await asyncio.to_thread(coordinator._store.fetch_lessons_for_incident, inc_str)
        for row in rows:
            ls = row.get("latest_state") or {}
            if isinstance(ls, dict):
                cand = ls.get("lesson")
                if isinstance(cand, dict):
                    lesson_blob = cand
                    break
    if isinstance(lesson_blob, dict):
        await upsert_lesson_from_workflow(session, lesson_blob)


async def upsert_lesson_from_workflow(session: AsyncSession, lesson: dict[str, Any]) -> uuid.UUID:
    """Insert or replace a lesson row using workflow JSON (interactive_steps → interactive_elements)."""

    lid = uuid.UUID(str(lesson["id"]))
    diff_raw = str(lesson.get("difficulty", "beginner")).lower()
    try:
        difficulty = LessonDifficulty(diff_raw)
    except ValueError:
        difficulty = LessonDifficulty.BEGINNER
    interactive = lesson.get("interactive_steps")
    if not isinstance(interactive, list):
        interactive = list(lesson.get("interactive_elements") or [])
    csta = lesson.get("csta_standards")
    if not isinstance(csta, list):
        csta = []
    created = _parse_ts(lesson.get("created_at"))

    payload: dict[str, Any] = {
        "id": lid,
        "incident_id": uuid.UUID(str(lesson["incident_id"])),
        "title": str(lesson.get("title", "Lesson")),
        "narrative": str(lesson.get("narrative", "")),
        "interactive_elements": interactive,
        "difficulty": difficulty,
        "csta_standards": [str(x) for x in csta],
        "estimated_duration_minutes": int(lesson.get("estimated_duration_minutes", 30)),
        "concept_coverage": dict(lesson.get("concept_coverage") or {}),
    }
    if created is not None:
        payload["created_at"] = created

    row = await lessons_crud.get_by_id(session, lid)
    if row is None:
        await lessons_crud.create(session, payload)
    else:
        row.title = payload["title"]
        row.narrative = payload["narrative"]
        row.interactive_elements = payload["interactive_elements"]
        row.difficulty = payload["difficulty"]
        row.csta_standards = payload["csta_standards"]
        row.estimated_duration_minutes = payload["estimated_duration_minutes"]
        row.concept_coverage = payload["concept_coverage"]
        if created is not None:
            row.created_at = created
        await session.flush()
    return lid


async def sync_latest_lesson_for_incident(
    session: AsyncSession,
    incident_id: uuid.UUID,
    coordinator: TutorialCoordinator,
) -> uuid.UUID | None:
    """Persist the newest completed lesson for an incident (manual /generate path)."""

    st = _best_lesson_status_for_incident(coordinator, str(incident_id))
    blob: dict[str, Any] | None = None
    if st is not None:
        c = (st.latest_state or {}).get("lesson")
        if isinstance(c, dict):
            blob = c
    if blob is None:
        rows = await asyncio.to_thread(coordinator._store.fetch_lessons_for_incident, str(incident_id))
        for row in rows:
            ls = row.get("latest_state") or {}
            if isinstance(ls, dict):
                c = ls.get("lesson")
                if isinstance(c, dict):
                    blob = c
                    break
    if not isinstance(blob, dict):
        return None
    return await upsert_lesson_from_workflow(session, blob)
