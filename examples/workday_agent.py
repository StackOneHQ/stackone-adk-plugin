"""Workday agent using the StackOne plugin for Google ADK.

Default mode — every Workday tool the connected account exposes is registered
with the agent.

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

    plugin = StackOnePlugin(
        account_id=account_id,
        providers=["workday"],
    )

    tools = plugin.get_tools()
    print(f"Discovered {len(tools)} Workday tool(s)\n")

    agent = Agent(
        model="gemini-3.1-pro-preview",
        name="workday_agent",
        description="Manages Workday workers, jobs, and HR data via StackOne.",
        instruction=(
            "You are a Workday assistant powered by StackOne. Use the available "
            "tools to answer questions about workers and HR records. Keep "
            "answers concise and reference real data."
        ),
        tools=tools,
    )

    app = App(name="workday_app", root_agent=agent, plugins=[plugin])

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
