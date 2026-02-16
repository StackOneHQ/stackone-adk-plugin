"""Dynamic tool discovery using keyword search with StackOne and Google ADK.

StackOne's utility tools let you search for relevant tools using natural
language queries (hybrid BM25 + TF-IDF), then execute the best match —
instead of loading all provider tools into the agent upfront.

This example shows:
  1. Keyword search across all connected providers
  2. An ADK agent using the discovered tools

Setup:
    1. Get your StackOne API key from https://app.stackone.com
    2. Connect your providers (e.g. Calendly, HiBob) in the StackOne dashboard
    3. Set environment variables:
        export STACKONE_API_KEY="your-stackone-api-key"
        export GOOGLE_API_KEY="your-google-api-key"
    4. Run: python examples/tool_search_agent.py
"""

import asyncio
import json
import logging
import os
import warnings

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from stackone_ai import StackOneToolSet

from stackone_adk import StackOnePlugin
from stackone_adk.plugin import DEFAULT_BASE_URL, _discover_account_ids

# Suppress warnings from the Gemini SDK about non-text parts
warnings.filterwarnings("ignore", message=".*non-text parts.*")
_genai_logger = logging.getLogger("google.genai")
_genai_logger.addFilter(lambda r: "non-text parts" not in r.getMessage())


def demo_keyword_search() -> None:
    """Demonstrate keyword search for tool discovery."""
    print("=" * 60)
    print("Keyword Search — discover tools by query")
    print("=" * 60)

    api_key = os.getenv("STACKONE_API_KEY", "")
    account_ids = _discover_account_ids(api_key, DEFAULT_BASE_URL)

    toolset = StackOneToolSet(api_key=api_key)
    all_tools = toolset.fetch_tools(account_ids=account_ids)
    print(f"\n{len(all_tools)} tools across {len(account_ids)} connected account(s)\n")

    utility = all_tools.utility_tools()
    search_tool = utility.get_tool("tool_search")
    if not search_tool:
        print("tool_search not available")
        return

    queries = [
        "list events",
        "get current user",
        "list employees",
    ]

    for query in queries:
        result = search_tool.execute({"query": query, "limit": 3})
        tools_found = result.get("tools", [])
        print(f'  "{query}"')
        for t in tools_found:
            print(f"    -> {t['name']} (score: {t['score']:.2f})")
        print()


def print_events(events: list) -> None:
    """Print agent events in a readable format showing the tool call flow."""
    step = 0
    for event in events:
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if part.function_call:
                step += 1
                name = part.function_call.name
                args = part.function_call.args or {}

                if name == "tool_search":
                    query = args.get("query", "")
                    print(f"  [{step}] tool_search(\"{query}\")")
                elif name == "tool_execute":
                    tool_name = args.get("toolName", "?")
                    params = args.get("params")
                    if params:
                        print(f"  [{step}] tool_execute({tool_name}, {json.dumps(params)})")
                    else:
                        print(f"  [{step}] tool_execute({tool_name})")

            elif part.function_response:
                resp = part.function_response.response or {}
                name = part.function_response.name

                if name == "tool_search":
                    tools_found = resp.get("tools", [])
                    for t in tools_found[:3]:
                        print(f"      found: {t['name']} ({t['score']:.2f})")
                elif name == "tool_execute":
                    if "error" in resp:
                        print(f"      error: {resp['error'][:100]}")
                    else:
                        resp_str = json.dumps(resp)
                        if len(resp_str) > 200:
                            resp_str = resp_str[:200] + "..."
                        print(f"      result: {resp_str}")

            elif part.text:
                print(f"\n{'─' * 60}")
                print(f"Assistant: {part.text}")


async def demo_agent_with_utility_tools() -> None:
    """Demonstrate an ADK agent using utility tools."""
    print("=" * 60)
    print("ADK Agent — using tool_search + tool_execute")
    print("=" * 60)

    plugin = StackOnePlugin(use_utility_tools=True)
    tools = plugin.get_tools()
    print(f"\nAgent has {len(tools)} tools: {[t.name for t in tools]}\n")

    if not tools:
        print("No tools available. Connect a provider in your StackOne dashboard.")
        return

    agent = Agent(
        model="gemini-2.5-flash",
        name="assistant",
        description="Assistant that discovers and executes tools via StackOne.",
        instruction=(
            "You are an assistant with access to tools from multiple SaaS providers "
            "via StackOne.\n\n"
            "Workflow:\n"
            "1. Use tool_search with action words like 'list scheduled events', "
            "'get current user' — not provider names like 'Calendly'.\n"
            "2. Use tool_execute with the exact parameter schema from the search results.\n"
            "3. If a tool needs a parameter you don't have (like a user URI), "
            "first search for and execute a tool that provides it.\n\n"
            "Never ask the user for IDs, URIs, or technical parameters."
        ),
        tools=tools,
    )

    app = App(name="tool_search_app", root_agent=agent, plugins=[plugin])

    async with InMemoryRunner(app=app) as runner:
        prompt = "List my upcoming Calendly events"
        print(f"User: {prompt}\n")
        events = await runner.run_debug(prompt, quiet=True)
        print_events(events)


async def main() -> None:
    demo_keyword_search()
    print()
    await demo_agent_with_utility_tools()


if __name__ == "__main__":
    asyncio.run(main())
