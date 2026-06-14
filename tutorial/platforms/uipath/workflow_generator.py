"""Dynamic BPMN-style workflow definitions derived from TUTORIAL incidents."""

from __future__ import annotations

import re
import uuid
from xml.sax.saxutils import escape

import structlog
from pydantic import BaseModel, Field

from shared.models import Incident

logger = structlog.get_logger(__name__)


class WorkflowDefinition(BaseModel):
    """BPMN 2.0 XML plus structured metadata for Maestro / Studio import."""

    model_config = {"extra": "forbid"}

    workflow_id: str = Field(min_length=4)
    workflow_type: str = Field(min_length=1)
    bpmn_xml: str = Field(min_length=32)
    parallel_stages: list[str] = Field(default_factory=list)
    human_gates: list[str] = Field(default_factory=list)
    rollback_points: list[str] = Field(default_factory=list)


def _classify(incident: Incident) -> str:
    blob = f"{incident.title} {incident.description}".lower()
    if any(k in blob for k in ("exfil", "data theft", "egress", "c2")):
        return "data_exfiltration"
    if any(k in blob for k in ("malware", "ransom", "trojan", "virus")):
        return "malware"
    return "generic_security"


def _bpmn_process_id(wf_type: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", wf_type)[:40]


class WorkflowGenerator:
    """Builds BPMN 2.0 XML with parallel lanes, gateways, and escalation paths."""

    def __init__(self, *, escalation_minutes: int = 120) -> None:
        self._escalation_minutes = max(15, escalation_minutes)

    async def generate_workflow(self, incident: Incident) -> WorkflowDefinition:
        """Analyze incident context and emit importable BPMN 2.0."""

        wf_type = _classify(incident)
        wf_id = f"wf_{uuid.uuid4().hex[:12]}"
        title = escape(incident.title[:200])
        sev = incident.severity.value

        if wf_type == "malware":
            parallel = ["MemoryAnalysis", "LogAnalysis"]
            gates = ["THREAT_CONFIRMED", "ContainmentApproval"]
            xml = self._malware_bpmn(wf_id, title, sev)
            rollback = ["BeforeContainment", "RestoreNetwork"]
        elif wf_type == "data_exfiltration":
            parallel = ["NetFlowAnalysis", "DNSAnalysis"]
            gates = ["CONFIRM_C2", "BlockExfilApproval"]
            xml = self._exfil_bpmn(wf_id, title, sev)
            rollback = ["UnblockStaging", "RestoreFirewall"]
        else:
            parallel = ["Triage", "EvidenceTriage"]
            gates = ["ManagerApproval"]
            xml = self._generic_bpmn(wf_id, title, sev)
            rollback = ["CancelChanges"]

        logger.info("workflow_generated", workflow_id=wf_id, type=wf_type, severity=sev)
        return WorkflowDefinition(
            workflow_id=wf_id,
            workflow_type=wf_type,
            bpmn_xml=xml,
            parallel_stages=parallel,
            human_gates=gates,
            rollback_points=rollback,
        )

    def _malware_bpmn(self, wf_id: str, title: str, severity: str) -> str:
        esc = self._escalation_minutes
        pid = escape(_bpmn_process_id(wf_id))
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             id="{escape(wf_id)}"
             targetNamespace="https://tutorial.local/uipath/maestro">
  <process id="{pid}" name="MalwareIncident" isExecutable="true">
    <documentation>{title} ({escape(severity)})</documentation>
    <startEvent id="start"/>
    <parallelGateway id="fork"/>
    <serviceTask id="mem" name="Investigation Agent: Memory Analysis" data-agent="defense_investigation"/>
    <serviceTask id="logs" name="Investigation Agent: Log Analysis" data-agent="defense_investigation"/>
    <parallelGateway id="join"/>
    <serviceTask id="evidence" name="Evidence Agent: Collect Samples" data-agent="defense_evidence"/>
    <exclusiveGateway id="threatGate" name="THREAT CONFIRMED?"/>
    <userTask id="approveContain" name="Human approval: containment" data-gate="critical"/>
    <serviceTask id="contain" name="Containment Agent: Isolate Host" data-agent="defense_containment"/>
    <serviceTask id="remediate" name="Remediation Agent: Clean and Patch" data-agent="defense_remediation"/>
    <serviceTask id="lesson" name="Lesson Agent: Generate Lesson" data-agent="teaching_narrative"/>
    <serviceTask id="notify" name="Notify Stakeholders" data-agent="system"/>
    <boundaryEvent id="escalate" attachedToRef="threatGate" cancelActivity="true">
      <timerEventDefinition><timeDuration>PT{esc}M</timeDuration></timerEventDefinition>
    </boundaryEvent>
    <serviceTask id="rollback" name="Rollback path" data-rollback="BeforeContainment"/>
    <endEvent id="end"/>
    <sequenceFlow id="f1" sourceRef="start" targetRef="fork"/>
    <sequenceFlow id="f2" sourceRef="fork" targetRef="mem"/>
    <sequenceFlow id="f3" sourceRef="fork" targetRef="logs"/>
    <sequenceFlow id="f4" sourceRef="mem" targetRef="join"/>
    <sequenceFlow id="f5" sourceRef="logs" targetRef="join"/>
    <sequenceFlow id="f6" sourceRef="join" targetRef="evidence"/>
    <sequenceFlow id="f7" sourceRef="evidence" targetRef="threatGate"/>
    <sequenceFlow id="f8" name="yes" sourceRef="threatGate" targetRef="approveContain"/>
    <sequenceFlow id="f9" sourceRef="approveContain" targetRef="contain"/>
    <sequenceFlow id="f10" sourceRef="contain" targetRef="remediate"/>
    <sequenceFlow id="f11" sourceRef="remediate" targetRef="lesson"/>
    <sequenceFlow id="f12" sourceRef="lesson" targetRef="notify"/>
    <sequenceFlow id="f13" sourceRef="notify" targetRef="end"/>
    <sequenceFlow id="f14" sourceRef="escalate" targetRef="rollback"/>
    <sequenceFlow id="f15" sourceRef="rollback" targetRef="notify"/>
  </process>
  <bpmndi:BPMNDiagram id="Diagram1">
    <bpmndi:BPMNPlane bpmnElement="{pid}"/>
  </bpmndi:BPMNDiagram>
</definitions>"""

    def _exfil_bpmn(self, wf_id: str, title: str, severity: str) -> str:
        esc = self._escalation_minutes
        pid = escape(_bpmn_process_id(wf_id))
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             id="{escape(wf_id)}"
             targetNamespace="https://tutorial.local/uipath/maestro">
  <process id="{pid}" name="DataExfiltration" isExecutable="true">
    <documentation>{title} ({escape(severity)})</documentation>
    <startEvent id="start"/>
    <parallelGateway id="fork"/>
    <serviceTask id="net" name="Investigation Agent: Network Analysis" data-agent="defense_investigation"/>
    <serviceTask id="cap" name="Evidence Agent: Capture Traffic" data-agent="defense_evidence"/>
    <parallelGateway id="join"/>
    <exclusiveGateway id="c2gate" name="CONFIRMED?"/>
    <userTask id="approveBlock" name="Human approval: block exfiltration" data-gate="critical"/>
    <serviceTask id="block" name="Containment Agent: Block Exfiltration" data-agent="defense_containment"/>
    <serviceTask id="preserve" name="Evidence Agent: Preserve Logs" data-agent="defense_evidence"/>
    <serviceTask id="secure" name="Remediation Agent: Secure Data" data-agent="defense_remediation"/>
    <serviceTask id="lesson" name="Lesson Agent: Generate Lesson" data-agent="teaching_curriculum"/>
    <serviceTask id="compliance" name="Compliance Notification" data-agent="system"/>
    <endEvent id="end"/>
    <boundaryEvent id="escalate" attachedToRef="c2gate" cancelActivity="true">
      <timerEventDefinition><timeDuration>PT{esc}M</timeDuration></timerEventDefinition>
    </boundaryEvent>
    <serviceTask id="rollback" name="Rollback firewall" data-rollback="UnblockStaging"/>
    <sequenceFlow id="e1" sourceRef="start" targetRef="fork"/>
    <sequenceFlow id="e2" sourceRef="fork" targetRef="net"/>
    <sequenceFlow id="e3" sourceRef="fork" targetRef="cap"/>
    <sequenceFlow id="e4" sourceRef="net" targetRef="join"/>
    <sequenceFlow id="e5" sourceRef="cap" targetRef="join"/>
    <sequenceFlow id="e6" sourceRef="join" targetRef="c2gate"/>
    <sequenceFlow id="e7" sourceRef="c2gate" targetRef="approveBlock"/>
    <sequenceFlow id="e8" sourceRef="approveBlock" targetRef="block"/>
    <sequenceFlow id="e9" sourceRef="block" targetRef="preserve"/>
    <sequenceFlow id="e10" sourceRef="preserve" targetRef="secure"/>
    <sequenceFlow id="e11" sourceRef="secure" targetRef="lesson"/>
    <sequenceFlow id="e12" sourceRef="lesson" targetRef="compliance"/>
    <sequenceFlow id="e13" sourceRef="compliance" targetRef="end"/>
    <sequenceFlow id="e14" sourceRef="escalate" targetRef="rollback"/>
    <sequenceFlow id="e15" sourceRef="rollback" targetRef="compliance"/>
  </process>
  <bpmndi:BPMNDiagram id="Diagram1">
    <bpmndi:BPMNPlane bpmnElement="{pid}"/>
  </bpmndi:BPMNDiagram>
</definitions>"""

    def _generic_bpmn(self, wf_id: str, title: str, severity: str) -> str:
        pid = escape(_bpmn_process_id(wf_id))
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             id="{escape(wf_id)}"
             targetNamespace="https://tutorial.local/uipath/maestro">
  <process id="{pid}" name="SecurityIncident" isExecutable="true">
    <documentation>{title} ({escape(severity)})</documentation>
    <startEvent id="start"/>
    <serviceTask id="triage" name="Investigation Agent: Triage" data-agent="defense_investigation"/>
    <userTask id="mgr" name="Manager approval" data-gate="standard"/>
    <serviceTask id="contain" name="Containment Agent" data-agent="defense_containment"/>
    <serviceTask id="lesson" name="Lesson Agent" data-agent="teaching_narrative"/>
    <endEvent id="end"/>
    <sequenceFlow id="g1" sourceRef="start" targetRef="triage"/>
    <sequenceFlow id="g2" sourceRef="triage" targetRef="mgr"/>
    <sequenceFlow id="g3" sourceRef="mgr" targetRef="contain"/>
    <sequenceFlow id="g4" sourceRef="contain" targetRef="lesson"/>
    <sequenceFlow id="g5" sourceRef="lesson" targetRef="end"/>
  </process>
  <bpmndi:BPMNDiagram id="Diagram1">
    <bpmndi:BPMNPlane bpmnElement="{pid}"/>
  </bpmndi:BPMNDiagram>
</definitions>"""
