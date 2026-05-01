"""Workday agent using StackOne search-and-execute mode with Google ADK.

The plugin exposes only ``tool_search`` and ``tool_execute``; the agent
discovers and invokes Workday actions on demand. Use this when many SaaS
accounts are linked and the full tool catalog would dominate the model's
context window.

Setup:
    export STACKONE_API_KEY="..."
    export STACKONE_ACCOUNT_ID="..."     # Workday account id
    export GOOGLE_API_KEY="..."          # for Gemini

Run:
    uv run examples/search_and_execute_agent.py
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


def _print_tool_call(name: str, args: dict) -> None:
    pretty = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"  → {name}({pretty})")


def _print_tool_response(name: str, response: dict) -> None:
    if name == "tool_search":
        tools = response.get("tools", [])
        total = response.get("total", len(tools))
        print(f"  ← tool_search: total={total}")
        for t in tools:
            print(f"      • {t.get('name')}")
        return
    summary = str(response)
    if len(summary) > 400:
        summary = summary[:400] + "…"
    print(f"  ← {name}: {summary}")


async def main() -> None:
    if not os.getenv("STACKONE_API_KEY"):
        sys.exit("Set STACKONE_API_KEY to run this example.")
    account_id = os.getenv("STACKONE_ACCOUNT_ID")
    if not account_id:
        sys.exit("Set STACKONE_ACCOUNT_ID (Workday) to run this example.")
    if not os.getenv("GOOGLE_API_KEY"):
        sys.exit("Set GOOGLE_API_KEY to run this example.")

    plugin = StackOnePlugin(
        mode="search_and_execute",
        account_ids=[account_id],
        search={"method": "auto", "top_k": 10},
        execute={"account_ids": [account_id]},
    )

    tools = plugin.get_tools()
    print(f"Registered {len(tools)} meta tool(s): {[t.name for t in tools]}\n")

    agent = Agent(
        model="gemini-3.1-pro-preview",
        name="workday_agent",
        description="Workday assistant powered by StackOne search-and-execute.",
        instruction=(
            "You are a Workday assistant. To answer the user's request, first "
            "call tool_search with a short natural-language query to find the "
            "right Workday action, then call tool_execute with the chosen "
            "tool_name and parameters that match the schema returned by "
            "tool_search. Keep answers concise and reference real data."
        ),
        tools=tools,
    )

    app = App(name="workday_app", root_agent=agent, plugins=[plugin])

    prompt = "List the first 3 Workday workers and summarise who they are."
    print(f"User: {prompt}")
    print("=" * 60)

    async with InMemoryRunner(app=app) as runner:
        events = await runner.run_debug(prompt, quiet=True)

        for event in events:
            for call in event.get_function_calls() or []:
                _print_tool_call(call.name, dict(call.args or {}))
            for resp in event.get_function_responses() or []:
                _print_tool_response(resp.name, dict(resp.response or {}))

        for event in reversed(events):
            if event.content and event.content.parts:
                text_parts = [p.text for p in event.content.parts if p.text]
                if text_parts:
                    print("=" * 60)
                    print(f"Agent: {''.join(text_parts)}\n")
                    break


if __name__ == "__main__":
    asyncio.run(main())
