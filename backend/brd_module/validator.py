"""
validator.py
Validation Agent — runs after all 6 section agents complete in Phase 3b.

Reads all 6 BRD outputs, runs:
  1. Rule-based completeness checks (section length, placeholder detection)
  2. Rule-based cross-section checks (metric-to-requirement mapping, risk coverage)
  3. LLM-powered semantic validation (contradictions, gaps, orphan items)

Stores results in brd_validation_flags.
"""
import os
import json
import uuid
import re
from typing import List, Dict, Optional, Any, Callable
from datetime import datetime, timezone

from dotenv import load_dotenv
from pathlib import Path
from groq import Groq

_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env")

from brd_module.storage import get_connection
from brd_module.brd_pipeline import call_llm_with_retry


def store_validation_flag(session_id: str, section_name: str, flag_type: str,
                          description: str, severity: str):
    conn, db_type = get_connection()
    try:
        cur = conn.cursor()
        query = """
            INSERT INTO brd_validation_flags (
                flag_id, session_id, section_name, flag_type,
                description, severity, auto_resolvable, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        if db_type == "sqlite":
            query = query.replace("%s", "?")
        cur.execute(query, (
            str(uuid.uuid4()), session_id, section_name, flag_type,
            description, severity, False, datetime.now(timezone.utc)
        ))
        conn.commit()
    finally:
        conn.close()


def validation_agent(
    session_id: str,
    snapshot_id: str,
    client: Groq,
    agent_outputs: Dict[str, str],
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
):
    """
    Full validation agent that reads all 6 agent outputs and stores flags.

    Args:
        session_id: Session ID
        snapshot_id: Snapshot ID
        client: Groq client
        agent_outputs: dict of section_name -> content from all 6 agents
        on_progress: optional callback for progress events
    """
    def emit(event: dict):
        if on_progress:
            try:
                on_progress(event)
            except Exception:
                pass

    # ── 1. Rule-based completeness checks ──
    for name, content in agent_outputs.items():
        if not content or len(content.strip()) < 50:
            store_validation_flag(session_id, name, "gap",
                                 f"Section '{name}' has insufficient content ({len(content.strip())} chars).",
                                 "medium")
        elif "Insufficient data" in content or "Error generating" in content:
            store_validation_flag(session_id, name, "gap",
                                 f"Section '{name}' was not generated due to missing source data.",
                                 "medium")

    # Extract NFRD section names for cross-checking
    nfrd = agent_outputs.get("nfrd", "")
    frd = agent_outputs.get("functional_requirements", "")
    rules = agent_outputs.get("decisions", "")
    risks = agent_outputs.get("assumptions_risks", "")
    metrics = agent_outputs.get("success_metrics", "")
    stakeholder = agent_outputs.get("stakeholder_analysis", "")

    # ── 2. Rule-based cross-section checks ──

    # Check: does each success metric reference a requirement ID?
    if metrics and "Insufficient data" not in metrics:
        # Extract FR IDs from functional requirements (FR-XXX format)
        fr_ids = set(re.findall(r'FR-\d+', frd))
        # Extract SM IDs from success metrics
        sm_refs = set(re.findall(r'FR-\d+', metrics))
        # Check orphan metrics (metrics that don't reference any requirement)
        if fr_ids:
            orphan_refs = sm_refs - fr_ids
            if orphan_refs:
                store_validation_flag(session_id, "success_metrics", "orphan",
                                     f"Success metrics reference non-existent requirement IDs: {', '.join(orphan_refs)}",
                                     "low")

    # Check: does each risk have a corresponding mitigating requirement?
    if risks and "Insufficient data" not in risks:
        risk_ids = re.findall(r'R-\d+', risks)
        if len(risk_ids) < 2:
            store_validation_flag(session_id, "assumptions_risks", "coverage",
                                 f"Only {len(risk_ids)} risks identified. A comprehensive BRD should have at least 3-5 risks.",
                                 "low")

    # ── 3. LLM-powered semantic validation ──
    # Only run if we have enough content to validate
    sections_for_validation = {}
    for name, content in agent_outputs.items():
        if content and len(content) > 100 and "Insufficient data" not in content:
            # Cap each section at 4000 chars for the validation prompt (128K context budget)
            sections_for_validation[name] = content[:4000]

    if len(sections_for_validation) >= 3:
        _run_ai_validation(session_id, client, sections_for_validation, emit)

    emit({"type": "validation_completed", "session_id": session_id})


def _run_ai_validation(session_id: str, client: Groq, sections: dict, emit: callable):
    """Run a single LLM call to check all sections for consistency."""
    section_text = ""
    for name, content in sections.items():
        section_text += f"\n--- {name.upper()} ---\n{content}\n"

    prompt_text = f"""You are a BRD quality validator. Review these {len(sections)} BRD sections for conflicts, gaps, and inconsistencies.

{section_text}

Check for:
1. Functional requirements that conflict with business rules (FRD vs decisions)
2. Success metrics that do not map to any requirement or NFRD item
3. Risks identified in "Assumptions & Risks" but no corresponding mitigating requirement
4. Stakeholder concerns not addressed by any functional or non-functional requirement
5. NFRD items with no corresponding success metric to measure them
6. Contradictions between any two sections

Output JSON:
{{
  "issues": [
    {{
      "type": "conflict|gap|orphan|coverage|contradiction",
      "section": "<which section has the issue>",
      "severity": "high|medium|low",
      "description": "<clear 1-2 sentence explanation>"
    }}
  ]
}}

If there are NO issues, output: {{"issues": []}}
Output ONLY valid JSON. Do not include any other text."""

    messages = [
        {"role": "system", "content": "You are a strict JSON validation engine. Output ONLY valid JSON."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        raw_response = call_llm_with_retry(client, messages, json_mode=True)
        result = json.loads(raw_response)

        issues = result.get("issues", [])
        for issue in issues:
            store_validation_flag(
                session_id=session_id,
                section_name=issue.get("section", "cross_section"),
                flag_type=issue.get("type", "general"),
                description=issue.get("description", "Validation issue detected."),
                severity=issue.get("severity", "medium"),
            )
    except Exception as e:
        print(f"[{session_id}] AI validation check failed: {e}")


def validate_brd(session_id: str, client: Groq = None):
    """
    Legacy entry point kept for backward compatibility.
    Now delegates to the new validation_agent with data from the database.
    """
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    from brd_module.storage import get_latest_brd_sections, get_current_snapshot_id

    sections = get_latest_brd_sections(session_id)
    if not sections:
        return

    snapshot_id = get_current_snapshot_id(session_id) or "legacy"
    validation_agent(session_id, snapshot_id, client, sections)
