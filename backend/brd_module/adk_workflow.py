"""
adk_workflow.py
Builds the BRD workflow graph using ADK's ParallelAgent and SequentialAgent.

All ADK imports are lazy so the app doesn't crash if google.adk is not installed.

Structure:
  BRDWorkflow (SequentialAgent)
  ├── AllSectionsParallel (ParallelAgent): ALL 7 section agents run at once
  └── SynthesisSequential (SequentialAgent): Executive Summary → Validation
"""
from brd_module.adk_agents import create_agents
from brd_module.adk_config import get_adk_model, get_session_service, get_runner


def _import_adk_workflow():
    """Lazy import ADK workflow classes."""
    from google.adk.agents import SequentialAgent, ParallelAgent
    return SequentialAgent, ParallelAgent


def build_workflow() -> tuple:
    """
    Build the complete BRD workflow graph and return (runner, session_service).

    Returns:
        tuple: (Runner, InMemorySessionService) — ready to execute the pipeline.
    """
    SequentialAgent, ParallelAgent = _import_adk_workflow()

    # 1. Shared model (OpenRouter via LiteLLM)
    model = get_adk_model()

    # 2. Create all 9 agents
    agents = create_agents(model)

    # 3. All 7 section agents run in parallel — no dependencies between them
    all_sections_parallel = ParallelAgent(
        name="all_sections_parallel",
        sub_agents=[
            agents["frd"],
            agents["nfrd"],
            agents["stakeholder"],
            agents["timeline"],
            agents["business_rules"],
            agents["assumptions_risks"],
            agents["success_metrics"],
        ],
    )

    # 4. Synthesis: Executive Summary → Validation (sequential, runs after all sections)
    synthesis_sequential = SequentialAgent(
        name="synthesis",
        sub_agents=[
            agents["executive_summary"],
            agents["validation"],
        ],
    )

    # 5. Root workflow: All sections parallel → Synthesis sequential
    brd_workflow = SequentialAgent(
        name="brd_workflow",
        sub_agents=[all_sections_parallel, synthesis_sequential],
    )

    # 6. Session service and runner
    session_service = get_session_service()
    runner = get_runner(session_service, brd_workflow)

    return runner, session_service
