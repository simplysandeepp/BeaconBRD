"""
adk_orchestrator.py
Bridges Google ADK's async runner to FastAPI SSE endpoints.

Responsibilities:
1. Fetch signals from DB and inject into ADK session state
2. Run each ADK agent individually with per-agent error isolation
3. Iterative refinement: re-run conflicting sections, then re-validate
4. After completion, persist agent outputs to DB (brd_sections + brd_validation_flags)

Key design decision: Each agent runs as a separate Runner.call() so that
if one agent fails (rate limit, context length, etc.), the other agents
still complete. This mirrors the legacy ThreadPoolExecutor approach.
"""
import json
import asyncio
import sys
import os
from pathlib import Path
from typing import Optional, Callable, Dict, Any

# Ensure project root is on path for imports
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_NOISE_FILTER = os.path.join(_PROJECT_ROOT, "Noise filter module")
if os.path.isdir(_NOISE_FILTER) and _NOISE_FILTER not in sys.path:
    sys.path.insert(0, _NOISE_FILTER)

from brd_module.storage import (
    get_signals_for_snapshot,
    store_brd_section,
    create_snapshot,
)
from brd_module.validator import store_validation_flag
from brd_module.adk_workflow import build_workflow
from brd_module.adk_agents import create_agents
from brd_module.adk_config import get_adk_model, get_session_service
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner

# Maximum refinement iterations before giving up
MAX_REFINEMENT_ROUNDS = 2


def _map_adk_event(event: Any) -> Optional[Dict[str, str]]:
    """Map an ADK Event to our existing SSE event format."""
    action = getattr(event, "action", None) or getattr(event, "type", "message")
    agent_name = getattr(event, "agent_name", None) or getattr(event, "source", "unknown")

    if action in ("internal", "tool_call", "tool_response"):
        return None

    event_type = "message"
    if "complete" in str(action).lower():
        event_type = "agent_completed"
    elif "start" in str(action).lower() or "begin" in str(action).lower():
        event_type = "agent_started"
    elif "error" in str(action).lower() or "fail" in str(action).lower():
        event_type = "agent_failed"
    elif "validation" in str(action).lower():
        event_type = action

    result = {
        "type": event_type,
        "agent": agent_name,
    }

    content = getattr(event, "content", None)
    if content:
        result["content"] = str(content)[:500]

    return result


async def run_brd_generation_adk(
    session_id: str,
    client=None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    snapshot_id: Optional[str] = None,
) -> str:
    """
    Run the BRD workflow via Google ADK with per-agent error isolation
    and iterative refinement.

    Pipeline:
      Round 0: All 7 section agents run individually (per-agent error isolation)
              → Executive Summary → Validation
      Round 1+: If conflicts found, re-run only conflicting sections with context → Re-validate
      Max refinement rounds: MAX_REFINEMENT_ROUNDS (default 2)
    """
    print(f"[ADK:{session_id}] Starting BRD Generation via Google ADK...")

    def emit(event: Dict[str, Any]) -> None:
        if not on_progress:
            return
        try:
            on_progress(event)
        except Exception:
            pass

    # Stage 0: Create snapshot if not provided
    if snapshot_id is None:
        snapshot_id = create_snapshot(session_id)
        print(f"[ADK:{session_id}] Snapshot {snapshot_id} created.")
        emit({"type": "snapshot_created", "session_id": session_id, "snapshot_id": snapshot_id})

    # Fetch signals for the snapshot
    signals = get_signals_for_snapshot(snapshot_id)

    if not signals:
        emit({"type": "error", "session_id": session_id, "message": "No signals found for this session."})
        snapshot_id = create_snapshot(session_id)
        return snapshot_id

    print(f"[ADK:{session_id}] Loaded {len(signals)} signals.")

    # Build model and agents
    model = get_adk_model()
    agents = create_agents(model)
    session_service = get_session_service()

    # Inject signal data into ADK session state
    signals_json = json.dumps([s.model_dump(mode="json") for s in signals])
    initial_state = {
        "signals_json": signals_json,
        "snapshot_id": snapshot_id,
        "session_id": session_id,
        "total_signals": str(len(signals)),
        "unique_sources": str(len(set(s.source_ref for s in signals if s.source_ref))),
    }

    # ── Round 0: Run all 7 section agents individually ──
    print(f"[ADK:{session_id}] Round 0: Launching all 7 agents...")
    emit({"type": "agents_launched", "count": 7, "session_id": session_id, "round": 0})

    agent_results = await _run_all_agents_with_resilience(
        session_service, agents, session_id, snapshot_id,
        signals_json, initial_state, emit, round_num=0
    )

    # ── Run Executive Summary + Validation ──
    print(f"[ADK:{session_id}] Round 0: Executive Summary + Validation...")
    await _run_sequential_agents(
        session_service, agents, session_id, snapshot_id,
        ["executive_summary", "validation"], initial_state, emit, round_num=0
    )

    # ── Iterative refinement rounds ──
    for round_num in range(1, MAX_REFINEMENT_ROUNDS + 1):
        # Read validation flags from session state
        session = await _get_session(session_service, session_id, snapshot_id)
        if session is None:
            break
        state = session.state
        validation_flags_raw = state.get("validation_flags", "")

        if not validation_flags_raw or validation_flags_raw.strip() in ("", "[]", '{"issues": []}'):
            print(f"[ADK:{session_id}] Round {round_num}: No conflicts found. Done.")
            break

        # Parse conflicting sections from validation output
        try:
            if isinstance(validation_flags_raw, str):
                flags_data = json.loads(validation_flags_raw)
                issues = flags_data.get("issues", [])
            else:
                issues = validation_flags_raw.get("issues", [])
        except (json.JSONDecodeError, AttributeError):
            print(f"[ADK:{session_id}] Round {round_num}: Could not parse validation flags. Done.")
            break

        if not issues:
            print(f"[ADK:{session_id}] Round {round_num}: No issues. Done.")
            break

        # Identify which sections need refinement
        conflict_sections = set()
        for issue in issues:
            sec = issue.get("section", "")
            if sec and sec != "cross_section":
                conflict_sections.add(sec)

        if not conflict_sections:
            print(f"[ADK:{session_id}] Round {round_num}: Only cross-section issues, no specific section to fix. Done.")
            break

        print(f"[ADK:{session_id}] Round {round_num}: Refining sections: {conflict_sections}")
        emit({
            "type": "refinement_started",
            "session_id": session_id,
            "round": round_num,
            "sections": list(conflict_sections),
            "issues": issues,
        })

        # Build conflict context for the refinement agents
        conflict_context = _build_conflict_context(state, issues)

        # Run only the conflicting agents with conflict context
        await _run_refinement_agents(
            session_service, agents, session_id, snapshot_id,
            conflict_sections, conflict_context, emit, round_num
        )

        # Re-run validation
        await _run_single_agent(
            session_service, agents["validation"], "validation",
            session_id, snapshot_id, initial_state, emit, round_num
        )

        print(f"[ADK:{session_id}] Round {round_num}: Refinement complete.")

    # ── Persist all outputs to DB ──
    await _persist_outputs(session_service, session_id, snapshot_id, signals)

    print(f"[ADK:{session_id}] BRD Generation complete.")
    emit({"type": "generation_completed", "session_id": session_id, "snapshot_id": snapshot_id})

    return snapshot_id


async def _run_all_agents_with_resilience(
    session_service: InMemorySessionService,
    agents: dict,
    session_id: str,
    snapshot_id: str,
    signals_json: str,
    initial_state: dict,
    emit: Callable,
    round_num: int,
) -> dict:
    """
    Run each section agent individually so one failure doesn't kill the pipeline.
    This is the key resilience pattern — each agent is isolated.
    """
    results = {}
    section_agents = {k: v for k, v in agents.items()
                     if k not in ("executive_summary", "validation")}

    for agent_key, agent in section_agents.items():
        emit({"type": "agent_started", "agent": agent_key, "session_id": session_id, "round": round_num})
        try:
            await _run_single_agent(
                session_service, agent, agent_key,
                session_id, snapshot_id, initial_state, emit, round_num
            )
            results[agent_key] = "completed"
            emit({"type": "agent_completed", "agent": agent_key, "session_id": session_id, "round": round_num})
            print(f"  [ADK:{session_id}] Agent '{agent_key}' completed successfully.")

        except Exception as e:
            # Agent failed — store error placeholder, continue with other agents
            error_msg = f"Error generating section: {str(e)}"
            results[agent_key] = error_msg
            emit({
                "type": "agent_failed",
                "agent": agent_key,
                "session_id": session_id,
                "round": round_num,
                "error": str(e),
            })
            print(f"  [ADK:{session_id}] Agent '{agent_key}' FAILED: {e}")
            continue  # <-- KEY: don't crash, move to next agent

    return results


async def _run_sequential_agents(
    session_service: InMemorySessionService,
    agents: dict,
    session_id: str,
    snapshot_id: str,
    agent_keys: list,
    initial_state: dict,
    emit: Callable,
    round_num: int,
):
    """Run a list of agents sequentially (e.g., executive_summary → validation)."""
    for agent_key in agent_keys:
        emit({"type": "agent_started", "agent": agent_key, "session_id": session_id, "round": round_num})
        try:
            await _run_single_agent(
                session_service, agents[agent_key], agent_key,
                session_id, snapshot_id, initial_state, emit, round_num
            )
            emit({"type": "agent_completed", "agent": agent_key, "session_id": session_id, "round": round_num})
        except Exception as e:
            emit({
                "type": "agent_failed",
                "agent": agent_key,
                "session_id": session_id,
                "round": round_num,
                "error": str(e),
            })
            print(f"  [ADK:{session_id}] Agent '{agent_key}' FAILED: {e}")


async def _run_single_agent(
    session_service: InMemorySessionService,
    agent,
    agent_key: str,
    session_id: str,
    snapshot_id: str,
    initial_state: dict,
    emit: Callable,
    round_num: int,
    additional_context: str = "",
):
    """
    Run a single ADK agent in its own Runner call.
    This isolates failures — if this agent fails, it doesn't affect others.
    """
    single_runner = Runner(
        agent=agent,
        session_service=session_service,
        app_name="beacon_brd",
    )

    # Ensure session exists with proper state
    sess = await session_service.get_session(user_id=session_id, session_id=snapshot_id)
    if sess is None:
        sess = await session_service.create_session(
            user_id=session_id, session_id=snapshot_id, state=initial_state,
        )
    else:
        # Update state but preserve signals
        for key, val in initial_state.items():
            sess.state[key] = val

    # Build the user message
    if additional_context:
        new_message = (
            f"Refine your section. Address these issues:\n{additional_context}\n\n"
            f"Store your improved output in session.state['{agent_key}_output']."
        )
    else:
        new_message = (
            "Generate your BRD section using the signals stored in session.state['signals_json']. "
            "Follow your agent's instructions for reading inputs and storing outputs in session state."
        )

    async for event in single_runner.run_async(
        user_id=session_id,
        session_id=snapshot_id,
        new_message=new_message,
    ):
        progress_event = _map_adk_event(event)
        if progress_event:
            progress_event["session_id"] = session_id
            progress_event["round"] = round_num
            progress_event["agent"] = agent_key
            emit(progress_event)


async def _run_refinement_agents(
    session_service: InMemorySessionService,
    agents: dict,
    session_id: str,
    snapshot_id: str,
    conflict_sections: set,
    conflict_context: str,
    emit: Callable,
    round_num: int,
):
    """Run only the conflicting agents with conflict context in parallel."""
    # Map DB section names to agent keys
    section_to_agent = {
        "functional_requirements": "frd",
        "nfrd": "nfrd",
        "stakeholder_analysis": "stakeholder",
        "timeline": "timeline",
        "decisions": "business_rules",
        "assumptions_risks": "assumptions_risks",
        "success_metrics": "success_metrics",
    }

    tasks = []
    for section_name in conflict_sections:
        agent_key = section_to_agent.get(section_name)
        if agent_key and agent_key in agents:
            emit({
                "type": "agent_started",
                "agent": agent_key,
                "session_id": session_id,
                "round": round_num,
                "refinement": True,
            })
            tasks.append(
                _run_single_agent(
                    session_service, agents[agent_key], agent_key,
                    session_id, snapshot_id, {}, emit, round_num,
                    additional_context=conflict_context,
                )
            )
        else:
            print(f"  -> Skipping unknown section: {section_name}")

    if tasks:
        # Run all conflicting agents in parallel, collect results
        await asyncio.gather(*tasks, return_exceptions=True)


async def _get_session(session_service, session_id, snapshot_id):
    """Helper to get session state."""
    try:
        loop = asyncio.new_event_loop()
        session = loop.run_until_complete(
            session_service.get_session(user_id=session_id, session_id=snapshot_id)
        )
        loop.close()
        return session
    except Exception:
        return None


def _build_conflict_context(state: dict, issues: list) -> str:
    """Build a conflict context string from validation issues."""
    context_parts = ["## Issues found in your section that need fixing:\n"]

    for i, issue in enumerate(issues, 1):
        sec = issue.get("section", "unknown")
        desc = issue.get("description", "")
        severity = issue.get("severity", "medium")
        context_parts.append(f"{i}. [{severity.upper()}] Section '{sec}': {desc}")

    context_parts.append(
        "\n## Instructions:\n"
        "- Re-read your current output from session state\n"
        "- Address each issue listed above\n"
        "- Ensure consistency with other sections\n"
        "- Store your improved output in the same session state key\n"
        "- Make sure your output is comprehensive and detailed"
    )

    return "\n".join(context_parts)


async def _persist_outputs(session_service, session_id: str, snapshot_id: str, signals: list):
    """After ADK workflow completes, read all agent outputs from session state and persist to DB."""
    print(f"[ADK:{session_id}] Persisting outputs to DB...")

    session = await _get_session(session_service, session_id, snapshot_id)
    if session is None:
        print(f"[ADK:{session_id}] Session not found.")
        return

    state = session.state

    section_mapping = {
        "frd_output": "functional_requirements",
        "nfrd_output": "nfrd",
        "stakeholder_output": "stakeholder_analysis",
        "timeline_output": "timeline",
        "business_rules_output": "decisions",
        "assumptions_risks_output": "assumptions_risks",
        "success_metrics_output": "success_metrics",
        "executive_summary_output": "executive_summary",
    }

    for state_key, db_name in section_mapping.items():
        content = state.get(state_key, "")
        if content and len(content.strip()) > 10:
            source_ids = [c.chunk_id for c in signals[:30]]
            store_brd_section(
                session_id=session_id,
                snapshot_id=snapshot_id,
                section_name=db_name,
                content=content,
                source_chunk_ids=source_ids,
                human_edited=False,
            )
            print(f"  -> Persisted '{db_name}': {len(content)} chars")

    # Persist validation flags
    validation_flags_raw = state.get("validation_flags", "")
    if validation_flags_raw and validation_flags_raw.strip() not in ("", "[]"):
        try:
            if isinstance(validation_flags_raw, str):
                if validation_flags_raw.strip().startswith("{"):
                    flags_data = json.loads(validation_flags_raw)
                elif validation_flags_raw.strip().startswith("["):
                    flags_data = {"issues": json.loads(validation_flags_raw)}
                else:
                    flags_data = {"issues": []}
            else:
                flags_data = validation_flags_raw

            for issue in flags_data.get("issues", []):
                store_validation_flag(
                    session_id=session_id,
                    section_name=issue.get("section", "cross_section"),
                    flag_type=issue.get("type", "general"),
                    description=issue.get("description", "Validation issue detected."),
                    severity=issue.get("severity", "medium"),
                )
            print(f"  -> Persisted {len(flags_data.get('issues', []))} validation flags")
        except Exception as e:
            print(f"  -> Validation flags parse error: {e}")

    print(f"[ADK:{session_id}] Persistence complete.")
