"""Workday agent using the StackOne plugin for Google ADK.

Default mode — registers a small, scoped set of Workday tools with the agent.
Workday's full catalog (hundreds of actions) exceeds Gemini's `tools` payload
cap; for unscoped catalogs use ``search_and_execute_agent.py`` instead.

Setup:
    export STACKONE_API_KEY="..."
    export STACKONE_ACCOUNT_ID="..."     # Workday account id
    export GOOGLE_API_KEY="..."          # for Gemini

Run:
    uv run examples/workday_agent.py
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import warnings

# Force-load authlib's deprecate filter so our ignore takes precedence.
with contextlib.suppress(ImportError):
    import authlib.deprecate  # noqa: F401
warnings.simplefilter("ignore")
for _name in ("google_genai", "google_genai.types", "google.genai", "google.adk"):
    logging.getLogger(_name).setLevel(logging.ERROR)

from google.adk.agents import Agent  # noqa: E402
from google.adk.apps import App  # noqa: E402
from google.adk.runners import InMemoryRunner  # noqa: E402

from stackone_adk import StackOnePlugin  # noqa: E402


async def main() -> None:
    if not os.getenv("STACKONE_API_KEY"):
        sys.exit("Set STACKONE_API_KEY to run this example.")
    account_id = os.getenv("STACKONE_ACCOUNT_ID")
    if not account_id:
        sys.exit("Set STACKONE_ACCOUNT_ID (Workday) to run this example.")
    if not os.getenv("GOOGLE_API_KEY"):
        sys.exit("Set GOOGLE_API_KEY to run this example.")

    # Default mode sends every tool's schema to the LLM. Workday has hundreds
    # of actions, so we scope to a handful to stay under Gemini's payload cap.
    # For larger catalogs use search_and_execute_agent.py instead.
    plugin = StackOnePlugin(
        account_id=account_id,
        providers=["workday"],
        actions=[
            "workday_list_workers",
            "workday_get_worker",
            "workday_list_jobs",
        ],
    )

    tools = plugin.get_tools()
    print(f"Registered {len(tools)} Workday tool(s): {[t.name for t in tools]}\n")

    agent = Agent(
        model="gemini-3.1-pro-preview",
        name="stackone_agent",
        description="Provides access to connected SaaS data via StackOne.",
        instruction=(
            "You are an HR assistant with access to tools via StackOne "
            "(e.g. Workday). Use the available tools to answer questions "
            "about workers and HR records. Keep answers concise and reference "
            "real data."
        ),
        tools=tools,
    )

    app = App(name="stackone_app", root_agent=agent, plugins=[plugin])

    prompt = "List the first 3 Workday workers and summarise who they are."
    print(f"User: {prompt}")
    print("=" * 60)

    async with InMemoryRunner(app=app) as runner:
        events = await runner.run_debug(prompt, quiet=True)
        for event in reversed(events):
            if event.content and event.content.parts:
                text_parts = [p.text for p in event.content.parts if p.text]
                if text_parts:
                    print(f"Agent: {''.join(text_parts)}\n")
                    break


if __name__ == "__main__":
    asyncio.run(main())
