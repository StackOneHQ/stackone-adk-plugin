"""Multi-provider HRIS agent using StackOne plugin for Google ADK.

StackOne lets you combine tools from multiple SaaS providers and filter
by action type — all discovered dynamically from your connected accounts:

    plugin = StackOnePlugin(
        providers=["hibob", "bamboohr"],
        actions=["*_list_*", "*_get_*"],  # read-only operations only
    )
    agent = Agent(
        model="gemini-2.5-flash",
        name="hris_agent",
        tools=plugin.get_tools(),  # tools from both providers
    )

Setup:
    1. Get your StackOne API key from https://app.stackone.com
    2. Connect your HRIS providers in the StackOne dashboard
    3. Set environment variables:
        export STACKONE_API_KEY="your-stackone-api-key"
        export GOOGLE_API_KEY="your-google-api-key"
    4. Run: python examples/hris_agent.py
"""

import asyncio
import logging

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner

from stackone_adk import StackOnePlugin

# Suppress "non-text parts" warning from the Gemini SDK
_genai_logger = logging.getLogger("google.genai")
_genai_logger.addFilter(lambda r: "non-text parts" not in r.getMessage())


async def main() -> None:
    # Combine multiple providers with optional action filtering
    plugin = StackOnePlugin(
        providers=["hibob", "bamboohr"],
        actions=["*_list_*", "*_get_*"],  # read-only operations only
    )

    tools = plugin.get_tools()
    print(f"Discovered {len(tools)} HRIS tools\n")

    if not tools:
        print("No HRIS tools found. Connect HiBob or BambooHR in your StackOne dashboard.")
        return

    # Create agent with tools from multiple providers
    agent = Agent(
        model="gemini-2.5-flash",
        name="hris_agent",  # replace with your agent name
        description="Agent to answer questions using HiBob and BambooHR data.",
        instruction=(
            "You are a read-only HRIS assistant with access to multiple providers "
            "via StackOne. You can list and retrieve data from HiBob and BambooHR, "
            "but you cannot create, update, or delete anything.\n\n"
            "When asked to list employees or retrieve data, use the tools directly "
            "— do not ask the user for additional parameters.\n\n"
            "Always clarify which provider the data comes from in your responses."
        ),
        tools=tools,
    )

    app = App(name="hris_app", root_agent=agent, plugins=[plugin])

    async with InMemoryRunner(app=app) as runner:
        prompt = "List employees from HiBob"
        print(f"User: {prompt}")
        print("=" * 60)
        events = await runner.run_debug(prompt, quiet=True)
        # Extract the agent's final text response
        for event in reversed(events):
            if event.content and event.content.parts:
                text_parts = [p.text for p in event.content.parts if p.text]
                if text_parts:
                    print(f"Agent: {''.join(text_parts)}\n")
                    break


if __name__ == "__main__":
    asyncio.run(main())
