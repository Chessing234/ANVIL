"""YAML playbook parsing, dependency resolution, and parallel execution on SIFT."""

from __future__ import annotations

import asyncio
import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import BaseModel, Field

from platforms.sift.connector import SIFTConnector

logger = structlog.get_logger(__name__)

OnErrorPolicy = Literal["retry_once", "skip", "abort"]


class PlaybookStep(BaseModel):
    """One executable unit inside a forensic playbook."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    plugin: str | None = None
    output_format: str = Field(default="text", pattern="^(text|json)$")
    timeout: float = Field(default=120.0, ge=1.0, le=86_400.0)
    on_error: OnErrorPolicy = "abort"
    depends_on: list[str] = Field(default_factory=list)
    condition: str | None = None
    playbook_ref: str | None = None
    command: str | None = None


class Playbook(BaseModel):
    """Structured investigation playbook."""

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    description: str = ""
    steps: list[PlaybookStep] = Field(default_factory=list)


@dataclass
class StepExecutionRecord:
    """Single step outcome for aggregation and reporting."""

    name: str
    tool: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    skipped: bool = False
    error_message: str | None = None


@dataclass
class PlaybookResult:
    """Aggregate result after running a playbook."""

    playbook_name: str
    steps: list[StepExecutionRecord] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    progress_percent: float = 0.0
    aborted: bool = False
    abort_reason: str | None = None


def _playbook_base_dir() -> Path:
    return Path(__file__).resolve().parent / "playbooks"


def _interpolate(template: str, context: dict[str, Any]) -> str:
    """Replace ``{{path.to.value}}`` placeholders from a nested context dict."""

    def resolve(path: str) -> Any:
        cur: Any = context
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return ""
        return cur

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        val = resolve(key)
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val)
        return str(val)

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", replacer, template)


def _eval_condition(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a limited playbook condition against ``context``."""

    expr = expr.strip()
    if not expr:
        return True
    m = re.match(
        r"^previous\.([a-zA-Z0-9_]+)\s*(==|!=|>=|<=|>|<)\s*(.+)$",
        expr,
    )
    if not m:
        logger.warning("playbook_condition_unparsed", expr=expr)
        return True
    key, op, rhs_raw = m.group(1), m.group(2), m.group(3).strip()
    prev = context.get("previous", {})
    if key not in prev:
        return False
    cell = prev[key]
    lhs = cell.get("parsed") if isinstance(cell, dict) else None
    lhs_val: Any
    if isinstance(lhs, dict) and key in lhs:
        lhs_val = lhs[key]
    elif isinstance(lhs, dict):
        lhs_val = lhs.get("suspicious_processes", lhs.get("value", 0))
    else:
        lhs_val = cell.get("stdout", "") if isinstance(cell, dict) else ""

    rhs: Any
    if rhs_raw.startswith('"') and rhs_raw.endswith('"'):
        rhs = rhs_raw[1:-1]
    elif rhs_raw.lower() in ("true", "false"):
        rhs = rhs_raw.lower() == "true"
    else:
        try:
            rhs = float(rhs_raw) if "." in rhs_raw else int(rhs_raw)
        except ValueError:
            rhs = rhs_raw

    if op == "==":
        return lhs_val == rhs
    if op == "!=":
        return lhs_val != rhs
    if op == ">":
        return float(lhs_val) > float(rhs)  # type: ignore[arg-type]
    if op == "<":
        return float(lhs_val) < float(rhs)  # type: ignore[arg-type]
    if op == ">=":
        return float(lhs_val) >= float(rhs)  # type: ignore[arg-type]
    if op == "<=":
        return float(lhs_val) <= float(rhs)  # type: ignore[arg-type]
    return True


class PlaybookRunner:
    """Executes YAML playbooks on SIFT via SSH-backed :class:`SIFTConnector`."""

    def __init__(self, connector: SIFTConnector) -> None:
        self._connector = connector

    @staticmethod
    async def load_playbook(path: str) -> Playbook:
        """Load and validate a playbook YAML file."""

        p = Path(path)
        if not p.is_file():
            alt = _playbook_base_dir() / path
            if alt.is_file():
                p = alt
        raw = p.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise ValueError("playbook root must be a mapping")
        return Playbook.model_validate(data)

    def topological_layers(self, playbook: Playbook) -> list[list[PlaybookStep]]:
        """Group steps into layers so each layer can run in parallel."""

        steps = {s.name: s for s in playbook.steps}
        remaining = set(steps)
        layers: list[list[PlaybookStep]] = []
        while remaining:
            ready = [steps[n] for n in list(remaining) if all(d not in remaining for d in steps[n].depends_on)]
            if not ready:
                raise ValueError("playbook dependency cycle or missing step names in depends_on")
            for s in ready:
                remaining.remove(s.name)
            layers.append(ready)
        return layers

    async def _run_remote(self, command: str, timeout: float) -> dict[str, Any]:
        """Execute one shell command on SIFT and return a normalized result dict."""

        res = await self._connector.execute_command(command, timeout=timeout)
        parsed: Any = None
        if res.stdout.strip():
            try:
                parsed = json.loads(res.stdout)
            except json.JSONDecodeError:
                parsed = None
        return {
            "stdout": res.stdout,
            "stderr": res.stderr,
            "exit_code": res.exit_code,
            "parsed": parsed,
            "duration_seconds": res.duration_seconds,
        }

    def _build_tool_command(self, step: PlaybookStep, context: dict[str, Any]) -> str:
        """Compose the remote shell command for a playbook step."""

        if step.command:
            return _interpolate(step.command, context)
        evidence = str(context.get("evidence_path", ""))
        work = str(context.get("working_dir", "/cases/tutorial"))
        if step.tool == "playbook":
            raise ValueError("nested playbooks are executed in run_playbook, not as shell")
        if step.tool == "volatility":
            plugin = step.plugin or "windows.pslist"
            fmt = "-r json" if step.output_format == "json" else ""
            vol = "vol.py"
            return f"{vol} {fmt} -f {shlex.quote(evidence)} {plugin}".strip()
        if step.tool == "sleuthkit":
            if step.plugin == "mmls":
                return f"mmls {shlex.quote(evidence)}"
            if step.plugin == "fls":
                return f"fls -r {shlex.quote(evidence)}"
            if step.plugin == "fsstat":
                return f"fsstat {shlex.quote(evidence)}"
            return f"fls {shlex.quote(evidence)}"
        if step.tool == "plaso":
            out = f"{work}/plaso.dump"
            if step.plugin == "log2timeline":
                return f"log2timeline.py --storage_file {shlex.quote(out)} {shlex.quote(evidence)}"
            if step.plugin == "psort":
                return f"psort.py -w {shlex.quote(work + '/timeline.csv')} {shlex.quote(out)}"
            return f"log2timeline.py {shlex.quote(evidence)}"
        if step.tool == "tshark":
            filt = step.plugin or ""
            base = f"tshark -r {shlex.quote(evidence)} -T json -c 100"
            if filt:
                return f"{base} -Y {shlex.quote(filt)}"
            return base
        if step.tool == "log_analysis":
            log_dir = evidence or work
            return (
                f"find {shlex.quote(log_dir)} -maxdepth 3 -type f "
                r"\( -name '*.evtx' -o -name '*.log' -o -name 'syslog' \) "
                "-print | head -n 50 | xargs grep -h . 2>/dev/null | tail -n 200"
            )
        if step.tool == "shell":
            return step.plugin or "true"
        raise ValueError(f"unsupported tool {step.tool}")

    async def execute_playbook_step(self, step: PlaybookStep, context: dict[str, Any]) -> StepExecutionRecord:
        """Run a single step (used by self-correction and full playbook runs)."""

        if step.condition and not _eval_condition(step.condition, context):
            return StepExecutionRecord(
                name=step.name,
                tool=step.tool,
                success=True,
                stdout="",
                stderr="",
                exit_code=0,
                duration_seconds=0.0,
                skipped=True,
            )
        attempt = 0
        last_err: str | None = None
        while attempt < 2:
            attempt += 1
            try:
                cmd = self._build_tool_command(step, context)
            except ValueError as exc:
                return StepExecutionRecord(
                    name=step.name,
                    tool=step.tool,
                    success=False,
                    stdout="",
                    stderr=str(exc),
                    exit_code=1,
                    duration_seconds=0.0,
                    error_message=str(exc),
                )
            try:
                raw = await self._run_remote(cmd, step.timeout)
            except TimeoutError:
                last_err = "timeout"
                if step.on_error == "retry_once" and attempt < 2:
                    continue
                if step.on_error == "skip":
                    return StepExecutionRecord(
                        name=step.name,
                        tool=step.tool,
                        success=False,
                        stdout="",
                        stderr="timeout",
                        exit_code=124,
                        duration_seconds=step.timeout,
                        error_message="timeout",
                    )
                raise
            ok = raw["exit_code"] == 0
            if ok or step.on_error != "retry_once" or attempt >= 2:
                return StepExecutionRecord(
                    name=step.name,
                    tool=step.tool,
                    success=ok,
                    stdout=raw["stdout"],
                    stderr=raw["stderr"],
                    exit_code=raw["exit_code"],
                    duration_seconds=raw["duration_seconds"],
                    error_message=None if ok else raw["stderr"] or "non_zero_exit",
                )
            last_err = str(raw.get("stderr", "error"))
            await asyncio.sleep(0.2)
        return StepExecutionRecord(
            name=step.name,
            tool=step.tool,
            success=False,
            stdout="",
            stderr=last_err or "failed",
            exit_code=1,
            duration_seconds=0.0,
            error_message=last_err,
        )

    async def run_playbook(self, playbook: Playbook, context: dict[str, Any]) -> PlaybookResult:
        """Execute all steps respecting dependencies, conditions, and parallelism."""

        result = PlaybookResult(playbook_name=playbook.name, context=dict(context))
        ctx = result.context
        if "previous" not in ctx:
            ctx["previous"] = {}
        total = max(1, len(playbook.steps))
        done = 0

        for layer in self.topological_layers(playbook):

            async def run_one(step: PlaybookStep) -> StepExecutionRecord:
                if step.tool == "playbook" and step.playbook_ref:
                    sub = await PlaybookRunner.load_playbook(step.playbook_ref)
                    sub_ctx = dict(ctx)
                    sub_res = await PlaybookRunner(self._connector).run_playbook(sub, sub_ctx)
                    ctx["subplaybooks"] = ctx.get("subplaybooks", {})
                    ctx["subplaybooks"][step.name] = {
                        "playbook": sub.playbook_name,
                        "steps": [s.__dict__ for s in sub_res.steps],
                    }
                    if "previous" in sub_ctx:
                        ctx.setdefault("previous", {}).update(sub_ctx["previous"])
                    return StepExecutionRecord(
                        name=step.name,
                        tool="playbook",
                        success=not sub_res.aborted,
                        stdout=json.dumps(ctx["subplaybooks"][step.name]),
                        stderr=sub_res.abort_reason or "",
                        exit_code=0 if not sub_res.aborted else 1,
                        duration_seconds=sum(s.duration_seconds for s in sub_res.steps),
                        error_message=sub_res.abort_reason,
                    )
                if step.condition and not _eval_condition(step.condition, ctx):
                    rec = StepExecutionRecord(
                        name=step.name,
                        tool=step.tool,
                        success=True,
                        stdout="",
                        stderr="",
                        exit_code=0,
                        duration_seconds=0.0,
                        skipped=True,
                    )
                    ctx["previous"][step.name] = {
                        "stdout": "",
                        "parsed": {},
                        "exit_code": 0,
                        "skipped": True,
                    }
                    return rec
                rec = await self.execute_playbook_step(step, ctx)
                parsed: dict[str, Any] | None = None
                if rec.stdout.strip().startswith("{"):
                    try:
                        parsed = json.loads(rec.stdout)
                    except json.JSONDecodeError:
                        parsed = None
                ctx["previous"][step.name] = {
                    "stdout": rec.stdout,
                    "stderr": rec.stderr,
                    "exit_code": rec.exit_code,
                    "parsed": parsed,
                }
                if isinstance(parsed, dict):
                    for k, v in parsed.items():
                        if isinstance(v, (int, float)):
                            ctx["previous"][k] = {"parsed": {k: v}, "stdout": rec.stdout}
                if not rec.success:
                    if step.on_error == "skip":
                        rec = StepExecutionRecord(
                            name=rec.name,
                            tool=rec.tool,
                            success=True,
                            stdout=rec.stdout,
                            stderr=rec.stderr,
                            exit_code=rec.exit_code,
                            duration_seconds=rec.duration_seconds,
                            skipped=True,
                            error_message=rec.error_message,
                        )
                    elif step.on_error == "abort":
                        result.aborted = True
                        result.abort_reason = rec.error_message or "step_failed"
                return rec

            layer_results = await asyncio.gather(*[run_one(s) for s in layer])
            for rec in layer_results:
                result.steps.append(rec)
                done += 1
                if result.aborted:
                    result.progress_percent = 100.0 * done / total
                    return result
            result.progress_percent = min(100.0, 100.0 * done / total)

        result.progress_percent = 100.0
        return result
