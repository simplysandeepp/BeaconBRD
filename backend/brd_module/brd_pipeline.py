"""
brd_pipeline.py
Agents and orchestration for the BRD generation pipeline.

Three-phase architecture:
  Phase 1 (parallel): FRD, NFRD, Stakeholder
  Phase 2 (parallel, with Phase 1 context): Timeline, Business Rules, Assumptions & Risks, Success Metrics
  Phase 3 (sequential): Executive Summary → Validation Agent
"""
import os
import json
import time
import uuid
import re
from typing import List, Dict, Any, Callable, Optional
from datetime import datetime, timezone
import concurrent.futures

from dotenv import load_dotenv
from pathlib import Path

_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env")

from groq import Groq, APIConnectionError, RateLimitError, APIStatusError
from brd_module.storage import create_snapshot, get_signals_for_snapshot, store_brd_section
from brd_module.hitl.versioned_ledger import is_section_locked, get_section_content, create_new_version


_INLINE_SOURCE_ID_PATTERN = re.compile(
    r"\s*\[[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\]"
)


def _strip_source_id_annotations(text: str) -> str:
    if not text:
        return text
    cleaned = _INLINE_SOURCE_ID_PATTERN.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def call_llm_with_retry(client: Groq, messages: List[Dict[str, str]], json_mode: bool = False, max_tokens: int = 2048) -> str:
    """Resilient LLM caller with exponential backoff. Model is resolved from GROQ_MODEL env var
    or defaults to llama-3.3-70b-versatile for improved reasoning quality."""
    MODEL_NAME = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    response_format = {"type": "json_object"} if json_mode else None

    import re

    for attempt in range(3):
        try:
            chat_completion = client.chat.completions.create(
                messages=messages,
                model=MODEL_NAME,
                temperature=0.0,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            raw = chat_completion.choices[0].message.content
            if not raw:
                raise ValueError("Empty response from LLM")

            # Strip HTML tags that the model may hallucinate (preserve <https://...> autolinks)
            clean_md = re.sub(r'<(?!https?://)[^>]+>', '', raw)
            return _strip_source_id_annotations(clean_md)
        except APIConnectionError as e:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise Exception(f"LLM connection error after retries: {e}")
        except RateLimitError as e:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise Exception(f"LLM rate-limit exceeded: {e}")
        except APIStatusError as e:
            if e.status_code >= 500 and attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise Exception(f"LLM API error ({e.status_code}): {e.message}")
        except (ValueError, AttributeError) as e:
            if attempt == 0:
                time.sleep(1)
                continue
            raise Exception(f"LLM parse error: {e}")
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
                continue
            raise Exception(f"Unexpected LLM error: {e}")

    raise Exception("Max retries exceeded")


# ─── Phase 1 Agents ─────────────────────────────────────────────────────────

def frd_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Functional Requirements Document agent — generates the core functional requirements."""
    if is_section_locked(session_id, 'functional_requirements') and not additional_context:
        return get_section_content(session_id, 'functional_requirements')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    reqs = get_signals_for_snapshot(snapshot_id, label_filter='requirement')
    reqs = reqs[:30]

    if not reqs and not additional_context:
        placeholder = "Insufficient data to generate this section. No requirement signals were found in the provided sources."
        create_new_version(session_id, None, 'functional_requirements', placeholder, 'system', snapshot_id=snapshot_id, source_chunk_ids=[])
        return placeholder

    source_ids = [c.chunk_id for c in reqs]

    prompt_text = "You are a senior business analyst synthesizing functional requirements for a formal BRD.\n\n"
    prompt_text += "Here are the requirement signals extracted from communications:\n"
    for r in reqs:
        prompt_text += f"[{r.chunk_id}] Speaker: {r.speaker or 'Unknown'} (Source: {r.source_ref})\n"
        prompt_text += f"{r.cleaned_text}\n\n"

    prompt_text += """
Instructions:
1. Group related requirements by theme (e.g., User Management, Data Processing, Reporting, etc.).
2. Number them sequentially (FR-001, FR-002, ...).
3. Each requirement must include:
   - A clear description (2-3 sentences minimum)
   - Acceptance criteria (testable conditions)
   - Priority (High/Medium/Low)
   - Any dependencies on other requirements
4. Do NOT include source IDs, UUIDs, or inline attributions in the final output.
5. EXPLICITLY flag any requirements that appear contradictory or incomplete in a "Contradictions / Gaps" section at the end.
6. Aim for comprehensive coverage — if the source data supports 10+ requirements, generate all of them.
7. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags like <p>, <ul>, <li>, or <div>.
Output ONLY the final markdown content for this section. Do not wrap in markdown code blocks.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL USER INSTRUCTION: {additional_context}\n"
        prompt_text += "Please apply this instruction while generating the section.\n"
        current_content = get_section_content(session_id, 'functional_requirements')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT (for reference/transformation):\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags like <h3>, <ul>, or <li>. Use Markdown syntax strictly (e.g. ### for headers, - for lists)."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating functional requirements: {e}"

    create_new_version(session_id, None, 'functional_requirements', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


def nfrd_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Non-Functional Requirements Document agent — generates NFRD sections."""
    if is_section_locked(session_id, 'nfrd') and not additional_context:
        return get_section_content(session_id, 'nfrd')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    # Gather signals that hint at non-functional requirements
    all_signals = get_signals_for_snapshot(snapshot_id)
    # Prioritize signals that mention performance, security, scalability, usability, compliance
    nfrd_keywords = re.compile(
        r'\b(performance|latency|throughput|scalab|security|auth|encrypt|usability|accessib|compliance|regulat|'
        r'availability|reliab|uptime|backup|disaster|load|concurrent|response time|sla|gdpr|hipaa|soc2|iso)\b',
        re.IGNORECASE
    )
    nfrd_signals = [s for s in all_signals if nfrd_keywords.search(s.cleaned_text)]
    # Also include decision signals for constraints
    decision_signals = [s for s in all_signals if s.label.value == 'decision']
    # Merge and deduplicate
    seen_ids = set()
    combined = []
    for s in nfrd_signals + decision_signals:
        if s.chunk_id not in seen_ids:
            seen_ids.add(s.chunk_id)
            combined.append(s)
    nfrd_signals = combined[:30]

    if not nfrd_signals and not additional_context:
        placeholder = "Insufficient data to generate this section. No non-functional requirement signals were found in the provided sources."
        create_new_version(session_id, None, 'nfrd', placeholder, 'system', snapshot_id=snapshot_id, source_chunk_ids=[])
        return placeholder

    source_ids = [c.chunk_id for c in nfrd_signals]

    prompt_text = "You are a senior business analyst defining non-functional requirements (NFRD) for a formal BRD.\n\n"
    prompt_text += "Here are the relevant signals extracted from communications that relate to non-functional requirements:\n"
    for r in nfrd_signals:
        prompt_text += f"[{r.chunk_id}] Speaker: {r.speaker or 'Unknown'} (Source: {r.source_ref})\n"
        prompt_text += f"{r.cleaned_text}\n\n"

    prompt_text += """
Instructions:
1. Generate a comprehensive NFRD section with the following categories:
   - **Performance**: Response times, throughput, resource utilization expectations
   - **Security**: Authentication, authorization, data protection, encryption
   - **Scalability**: Load handling, concurrent users, data volume growth
   - **Usability**: Accessibility, user experience, browser/device support
   - **Compliance**: Regulatory requirements (GDPR, HIPAA, SOC2, etc.)
   - **Availability & Reliability**: Uptime SLAs, disaster recovery, backup
2. For each NFRD item:
   - Assign an ID (NFRD-001, NFRD-002, ...)
   - Write a clear description (2-3 sentences)
   - Specify measurable acceptance criteria where possible
   - Note priority (High/Medium/Low)
3. If a category has no source data, write: 'No specific requirements identified — to be defined with stakeholders.'
4. Do NOT include source IDs, UUIDs, or inline attributions in the final output.
5. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags.
Output ONLY the final markdown content for this section. Do not wrap in markdown code blocks.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL USER INSTRUCTION: {additional_context}\n"
        current_content = get_section_content(session_id, 'nfrd')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT:\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags. Use Markdown syntax strictly."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating NFRD: {e}"

    create_new_version(session_id, None, 'nfrd', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


def stakeholder_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Stakeholder Analysis agent — identifies and analyzes project stakeholders."""
    if is_section_locked(session_id, 'stakeholder_analysis') and not additional_context:
        return get_section_content(session_id, 'stakeholder_analysis')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    all_signals = get_signals_for_snapshot(snapshot_id)
    all_signals = all_signals[:30]

    speakers = {}
    feedback_chunks = []

    for c in all_signals:
        if c.speaker:
            speakers[c.speaker] = speakers.get(c.speaker, 0) + 1
        if c.label.value == 'stakeholder_feedback':
            feedback_chunks.append(c)

    feedback_chunks = feedback_chunks[:20]

    unique_speakers = [s for s in speakers.keys() if s and s.lower() != 'unknown' and s.strip() != '']

    if len(unique_speakers) < 1 and not additional_context:
        placeholder = "Insufficient data to generate this section. No identifiable stakeholders were found in the source communications."
        create_new_version(session_id, None, 'stakeholder_analysis', placeholder, 'system', snapshot_id=snapshot_id, source_chunk_ids=[])
        return placeholder

    source_ids = [c.chunk_id for c in feedback_chunks] if feedback_chunks else [c.chunk_id for c in all_signals[:10]]

    prompt_text = "You are a senior business analyst compiling a stakeholder analysis for a BRD.\n\n"
    prompt_text += "Here are the named stakeholders identified in the communications, and the number of signals they contributed (indicating influence):\n"
    for spk, count in speakers.items():
        if spk and spk.lower() != 'unknown' and spk.strip() != '':
            prompt_text += f"- {spk} ({count} communications)\n"

    prompt_text += "\nHere is all the specific stakeholder feedback extracted:\n"
    if feedback_chunks:
        for r in feedback_chunks:
            prompt_text += f"[{r.chunk_id}] Speaker: {r.speaker or 'Unknown'}\n{r.cleaned_text}\n\n"
    else:
        prompt_text += "No specific stakeholder feedback signals were classified. Use the general communications to infer stakeholder roles.\n\n"

    prompt_text += """
Instructions:
1. Generate a stakeholder table identifying each named speaker.
2. Columns should include: Stakeholder Name, Apparent Role, Key Concerns/Preferences, and Influence Level (based on communication volume).
3. CRITICAL CONSTRAINT: Do not invent stakeholder roles. Only infer roles if strongly implied by the context. If unknown, write 'Role unknown'.
4. Do not fabricate stakeholder names. If speaker attribution was unavailable for some feedback, explicitly state that in your summary.
5. Provide a brief summary paragraph before the table analyzing the overall stakeholder landscape.
6. Include at least 2-3 sentences of analysis per stakeholder where data permits.
7. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags.
Output ONLY the final markdown content for this section. Do not wrap in markdown code blocks.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL USER INSTRUCTION: {additional_context}\n"
        current_content = get_section_content(session_id, 'stakeholder_analysis')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT:\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags. Use Markdown tables and headers strictly."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating stakeholder analysis: {e}"

    create_new_version(session_id, None, 'stakeholder_analysis', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


# ─── Phase 2 Agents ─────────────────────────────────────────────────────────

def timeline_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Timeline agent — generates project timeline, milestones, and deadlines."""
    if is_section_locked(session_id, 'timeline') and not additional_context:
        return get_section_content(session_id, 'timeline')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    timeline_refs = get_signals_for_snapshot(snapshot_id, label_filter='timeline_reference')
    timeline_refs = timeline_refs[:25]

    if not timeline_refs and not additional_context:
        placeholder = "No project timeline information was found in the provided sources. Timeline must be established through stakeholder clarification."
        create_new_version(session_id, None, 'timeline', placeholder, 'system', snapshot_id=snapshot_id, source_chunk_ids=[])
        return placeholder

    source_ids = [c.chunk_id for c in timeline_refs]

    prompt_text = "You are a senior business analyst compiling a project timeline for a formal BRD.\n\n"
    prompt_text += "Here are the timeline references extracted from project communications:\n"
    for r in timeline_refs:
        prompt_text += f"[{r.chunk_id}] (Source: {r.source_ref})\n"
        prompt_text += f"{r.cleaned_text}\n\n"

    prompt_text += """
Instructions:
1. Generate a chronological list of project milestones and deadlines.
2. For each entry, include:
   - Milestone name
   - Date or timeframe (use 'Date not specified' if vague)
   - What it refers to / deliverable
   - Dependencies on other milestones (if any)
3. CRITICAL CONSTRAINT: ONLY include dates and timeframes explicitly mentioned. NEVER invent or estimate dates.
4. If a deadline is mentioned without a specific date (e.g. 'go-live'), list the deadline with 'Date not specified'.
5. Do not include random meetings unless they represent a project milestone (like a sign-off or launch).
6. Group milestones by phase if the source data implies phases (e.g., Discovery, Build, Launch).
7. Aim for comprehensive coverage — if the source data supports 8+ milestones, generate all of them.
8. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags.
Output ONLY the final markdown content for this section.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL CONTEXT FROM OTHER AGENTS:\n{additional_context}\n"
        prompt_text += "Ensure your timeline is consistent with the business rules and decisions above.\n"
        current_content = get_section_content(session_id, 'timeline')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT:\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags. Use Markdown headers and lists strictly."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating timeline: {e}"

    create_new_version(session_id, None, 'timeline', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


def business_rules_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Business Rules agent — generates business rules, constraints, and policies."""
    if is_section_locked(session_id, 'decisions') and not additional_context:
        return get_section_content(session_id, 'decisions')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    decision_refs = get_signals_for_snapshot(snapshot_id, label_filter='decision')
    decision_refs = decision_refs[:20]

    if not decision_refs and not additional_context:
        placeholder = "Insufficient data to generate this section. No confirmed decisions or business rules were found in the provided sources."
        create_new_version(session_id, None, 'decisions', placeholder, 'system', snapshot_id=snapshot_id, source_chunk_ids=[])
        return placeholder

    source_ids = [c.chunk_id for c in decision_refs]

    prompt_text = "You are a senior business analyst compiling business rules and constraints for a BRD.\n\n"
    prompt_text += "Here are the confirmed decisions and policy signals extracted from project communications:\n"
    for r in decision_refs:
        prompt_text += f"[{r.chunk_id}] (Source: {r.source_ref})\n{r.cleaned_text}\n\n"

    prompt_text += """
Instructions:
1. Generate a numbered list of business rules and constraints.
2. Each rule must include:
   - Rule ID (BR-001, BR-002, ...)
   - Rule statement (clear, unambiguous)
   - Category (Data Validation, Access Control, Business Process, Regulatory, Threshold/limit)
   - Enforcement mechanism (how the system enforces this rule)
   - Priority (High/Medium/Low)
3. Include constraints like: data retention policies, approval workflows, threshold limits, regulatory requirements.
4. Do NOT include source IDs, UUIDs, or inline attributions in the final output.
5. If decisions imply scheduling or timing constraints, include them as business rules.
6. Aim for comprehensive coverage — if the source data supports 8+ rules, generate all of them.
7. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags.
Output ONLY the final markdown content for this section.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL CONTEXT FROM OTHER AGENTS:\n{additional_context}\n"
        prompt_text += "Ensure your business rules are consistent with the above context.\n"
        current_content = get_section_content(session_id, 'decisions')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT:\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags. Use Markdown headers and lists strictly."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating business rules: {e}"

    create_new_version(session_id, None, 'decisions', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


def assumptions_risks_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Assumptions & Risks agent — generates project assumptions and risk register."""
    if is_section_locked(session_id, 'assumptions_risks') and not additional_context:
        return get_section_content(session_id, 'assumptions_risks')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    all_refs = get_signals_for_snapshot(snapshot_id)
    if not all_refs and not additional_context:
        placeholder = "Insufficient data to generate this section. No signals were found to infer assumptions and risks from."
        create_new_version(session_id, None, 'assumptions_risks', placeholder, 'system', snapshot_id=snapshot_id, source_chunk_ids=[])
        return placeholder

    source_ids = [c.chunk_id for c in all_refs]
    all_refs = all_refs[:25]
    prompt_text = "You are a senior business analyst identifying project assumptions and risks.\n\n"
    prompt_text += "Here are the project signals to analyze:\n"
    for r in all_refs:
        prompt_text += f"[{r.chunk_id}] {r.cleaned_text}\n"

    prompt_text += """
Instructions:
1. Generate TWO sections:

## Assumptions
- List all implicit and explicit project assumptions
- Each assumption should have: ID (A-001, A-002, ...), description, basis (why this is assumed), and validation method
- Clearly mark AI-inferred assumptions with '[AI-inferred — requires stakeholder validation]'
- Include assumptions about: user behavior, data availability, technology constraints, organizational support, timeline feasibility

## Risks
- Generate a risk register with: ID (R-001, R-002, ...), risk description, likelihood (High/Medium/Low), impact (High/Medium/Low), mitigation strategy, and owner (if identifiable)
- Focus on: technical risks, resource risks, timeline risks, scope risks, stakeholder risks
- Each risk must have a concrete mitigation strategy (not just "monitor")
- Aim for at least 5-8 identified risks if source data supports it

2. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags.
Output ONLY the final markdown content for this section.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL CONTEXT FROM OTHER AGENTS:\n{additional_context}\n"
        prompt_text += "Ensure your assumptions and risks are consistent with the above context. Identify risks that arise from conflicts or gaps in other sections.\n"
        current_content = get_section_content(session_id, 'assumptions_risks')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT:\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags. Use Markdown headers and lists strictly."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating assumptions & risks: {e}"

    create_new_version(session_id, None, 'assumptions_risks', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


def success_metrics_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Success Metrics agent — derives measurable success criteria."""
    if is_section_locked(session_id, 'success_metrics') and not additional_context:
        return get_section_content(session_id, 'success_metrics')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    signals = []
    signals.extend(get_signals_for_snapshot(snapshot_id, label_filter='requirement'))
    signals.extend(get_signals_for_snapshot(snapshot_id, label_filter='decision'))
    signals = signals[:25]

    if not signals and not additional_context:
        placeholder = "Insufficient data to generate this section. No requirements or decisions were found to derive metrics from."
        create_new_version(session_id, None, 'success_metrics', placeholder, 'system', snapshot_id=snapshot_id, source_chunk_ids=[])
        return placeholder

    source_ids = [c.chunk_id for c in signals]
    prompt_text = "You are a senior business analyst deriving success metrics.\n\n"
    for r in signals:
        prompt_text += f"[{r.chunk_id}] {r.cleaned_text}\n"

    prompt_text += """
Instructions:
1. Derive measurable success criteria from the requirements and decisions.
2. For each metric, include:
   - Metric ID (SM-001, SM-002, ...)
   - Metric name (clear, descriptive)
   - Definition (what exactly is being measured)
   - Measurement method (how to collect the data)
   - Target value or range (if source data supports it; otherwise write 'TBD — requires stakeholder validation')
   - Related requirement(s) it measures
3. Group metrics by category: User Satisfaction, Performance, Business Impact, Quality
4. If requirements are not directly measurable, suggest proxy metrics with a flag.
5. CRITICAL CONSTRAINT: NEVER invent specific numbers/targets not present in the source data.
6. Aim for 8-12 metrics if source data supports it.
7. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags.
Output ONLY the final markdown content for this section.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL CONTEXT FROM OTHER AGENTS:\n{additional_context}\n"
        prompt_text += "Ensure your success metrics map to the requirements and NFRD items above.\n"
        current_content = get_section_content(session_id, 'success_metrics')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT:\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags. Use Markdown headers and lists strictly."},
        {"role": "user", "content": prompt_text}
    ]

    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating success metrics: {e}"

    create_new_version(session_id, None, 'success_metrics', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


# ─── Phase 3 Agents ─────────────────────────────────────────────────────────

def executive_summary_agent(session_id: str, snapshot_id: str, client: Groq = None, additional_context: str = "") -> str:
    """Runs LAST after all other agents. Reads all Phase 1 + Phase 2 outputs."""
    if is_section_locked(session_id, 'executive_summary') and not additional_context:
        return get_section_content(session_id, 'executive_summary')
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    from brd_module.storage import get_latest_brd_sections

    sections = get_latest_brd_sections(session_id)
    all_signals = get_signals_for_snapshot(snapshot_id)

    insufficient_sections = [name for name, content in sections.items() if "Insufficient data" in content]

    total_signals = len(all_signals)
    unique_sources = len(set(s.source_ref for s in all_signals if s.source_ref))

    prompt_text = "You are a senior business analyst writing an Executive Summary for a BRD.\n\n"
    prompt_text += "Here are the generated sections from other agents:\n"
    for name, content in sections.items():
        if name != 'executive_summary':
            capped = content[:3000] + ("..." if len(content) > 3000 else "")
            prompt_text += f"\n--- {name.upper()} ---\n{capped}\n"

    prompt_text += f"\nMetaData: This session processed {total_signals} total signals from {unique_sources} documents.\n"

    prompt_text += """
Instructions:
1. Write a 3-5 paragraph executive summary covering:
   - What the project aims to achieve (based on requirements).
   - Who the key stakeholders are.
   - Major constraints or risks (based on decisions/feedback).
2. Honest Completeness Statement: You MUST end the summary with an honest assessment of data completeness.
   - Explicitly state which sections had insufficient data if any.
   - You MUST include a sentence matching this format exactly: "This BRD was generated from <total_signals> signals extracted from <unique_sources> source documents."
3. STRICTURE: Output ONLY clean Markdown content. NEVER output HTML tags.
Output ONLY the final markdown content for this section.
"""

    if additional_context:
        prompt_text += f"\nADDITIONAL USER INSTRUCTION: {additional_context}\n"
        current_content = get_section_content(session_id, 'executive_summary')
        if current_content:
            prompt_text += f"\nCURRENT SECTION CONTENT:\n{current_content}\n"

    messages = [
        {"role": "system", "content": "You are a senior business analyst. You output ONLY valid Markdown. You NEVER use HTML tags. Use Markdown headers and paragraphs strictly."},
        {"role": "user", "content": prompt_text}
    ]
    try:
        content = call_llm_with_retry(client, messages, json_mode=False)
    except Exception as e:
        content = f"Error generating executive summary: {e}"

    source_ids = [c.chunk_id for c in all_signals]
    create_new_version(session_id, None, 'executive_summary', content, 'system', snapshot_id=snapshot_id, source_chunk_ids=source_ids)
    return content


# ─── Orchestration ──────────────────────────────────────────────────────────

def _build_phase2_context(agent_name: str, phase1_results: dict) -> str:
    """Build a context string summarizing Phase 1 outputs for Phase 2 agents."""
    sections = []
    for name in ["functional_requirements", "nfrd", "stakeholder_analysis"]:
        content = phase1_results.get(name, "")
        if content and len(content) > 100:
            capped = content[:2000] + ("..." if len(content) > 2000 else "")
            sections.append(f"\n--- {name.upper()} ---\n{capped}")
    if not sections:
        return ""
    return "Context from Phase 1 agents (use these to ensure consistency and avoid conflicts):" + "".join(sections)


def _run_parallel(agents_dict: dict, session_id: str, snapshot_id: str, client: Groq,
                  emit: Callable, phase1_context: dict = None) -> dict:
    """Run agents in parallel, return dict of section_name -> content."""
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for name, func in agents_dict.items():
            additional_ctx = ""
            if phase1_context and name in ("decisions", "assumptions_risks", "success_metrics"):
                additional_ctx = _build_phase2_context(name, phase1_context)
            emit({"type": "agent_started", "agent": name, "session_id": session_id})
            future = executor.submit(func, session_id, snapshot_id, client,
                                   additional_context=additional_ctx)
            futures[future] = name

        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                emit({"type": "agent_completed", "agent": name, "session_id": session_id})
            except Exception as exc:
                results[name] = f"Error generating {name}: {exc}"
                emit({
                    "type": "agent_failed",
                    "agent": name,
                    "session_id": session_id,
                    "error": str(exc),
                })
    return results


def run_brd_generation(
    session_id: str,
    client: Groq = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> str:
    """
    Main orchestration function for the BRD generation pipeline.

    Three-phase architecture:
      Phase 1 (parallel): FRD, NFRD, Stakeholder
      Phase 2 (parallel, with Phase 1 context): Business Rules, Assumptions & Risks, Success Metrics
      Phase 3 (sequential): Executive Summary → Validation Agent
    """
    if client is None:
        client = Groq(api_key=os.environ.get("GROQ_CLOUD_API", ""))

    print(f"[{session_id}] Starting BRD Generation...")

    def emit(event: Dict[str, Any]) -> None:
        if not on_progress:
            return
        try:
            on_progress(event)
        except Exception:
            pass

    # Stage 0: Snapshot Creation
    snapshot_id = create_snapshot(session_id)
    print(f"[{session_id}] Snapshot {snapshot_id} created. Freezing DB state for this run.")
    emit({"type": "snapshot_created", "session_id": session_id, "snapshot_id": snapshot_id})

    # ── Phase 1: FRD + NFRD + Stakeholder (parallel) ──
    print(f"[{session_id}] Phase 1: Launching FRD, NFRD, Stakeholder agents in parallel...")
    emit({"type": "agents_launched", "count": 3, "session_id": session_id, "phase": 1})

    phase1_agents = {
        "functional_requirements": frd_agent,
        "nfrd": nfrd_agent,
        "stakeholder_analysis": stakeholder_agent,
    }
    phase1_results = _run_parallel(phase1_agents, session_id, snapshot_id, client, emit)

    # ── Phase 2: Timeline + Business Rules + Assumptions & Risks + Success Metrics (parallel, with Phase 1 context) ──
    print(f"[{session_id}] Phase 2: Launching Timeline, Business Rules, Assumptions & Risks, Success Metrics agents...")
    emit({"type": "agents_launched", "count": 4, "session_id": session_id, "phase": 2})

    phase2_agents = {
        "timeline": timeline_agent,
        "decisions": business_rules_agent,
        "assumptions_risks": assumptions_risks_agent,
        "success_metrics": success_metrics_agent,
    }
    phase2_results = _run_parallel(phase2_agents, session_id, snapshot_id, client, emit,
                                    phase1_context=phase1_results)

    # ── Phase 3a: Executive Summary (reads all Phase 1 + Phase 2 outputs) ──
    print(f"[{session_id}] Phase 3a: Generating Executive Summary...")
    emit({"type": "agent_started", "agent": "executive_summary", "session_id": session_id})
    executive_summary_agent(session_id, snapshot_id, client)
    emit({"type": "agent_completed", "agent": "executive_summary", "session_id": session_id})

    # ── Phase 3b: Validation Agent ──
    print(f"[{session_id}] Phase 3b: Running Validation Agent...")
    emit({"type": "validation_started", "session_id": session_id})
    all_context = {**phase1_results, **phase2_results}
    from brd_module.validator import validation_agent
    validation_agent(session_id, snapshot_id, client, all_context)
    emit({"type": "validation_completed", "session_id": session_id})

    print(f"[{session_id}] BRD Generation complete.")
    emit({"type": "generation_completed", "session_id": session_id, "snapshot_id": snapshot_id})

    return snapshot_id


def run_single_agent(
    session_id: str,
    snapshot_id: str,
    section_name: str,
    client: Groq,
    additional_context: str = ""
) -> str:
    """Dispatches to a specific agent for ad-hoc regeneration."""
    agent_map = {
        'functional_requirements': frd_agent,
        'frd': frd_agent,
        'nfrd': nfrd_agent,
        'stakeholder_analysis': stakeholder_agent,
        'stakeholder': stakeholder_agent,
        'timeline': timeline_agent,
        'decisions': business_rules_agent,
        'business_rules': business_rules_agent,
        'assumptions_risks': assumptions_risks_agent,
        'success_metrics': success_metrics_agent,
        'executive_summary': executive_summary_agent,
    }

    agent_func = agent_map.get(section_name)
    if not agent_func:
        raise ValueError(f"Unknown section: {section_name}. Available: {list(agent_map.keys())}")

    return agent_func(session_id, snapshot_id, client, additional_context=additional_context)
