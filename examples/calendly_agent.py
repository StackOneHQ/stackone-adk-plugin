"""Calendly scheduling agent using StackOne plugin for Google ADK.

StackOne dynamically discovers tools from your connected SaaS providers,
so you don't need to define tool functions manually. Just connect your
Calendly account and the tools are ready to use:

    plugin = StackOnePlugin()
    agent = Agent(
        model="gemini-2.5-flash",
        name="calendly_agent",
        tools=plugin.get_tools(),
    )

Setup:
    1. Get your StackOne API key from https://app.stackone.com
    2. Connect your Calendly account in the StackOne dashboard
    3. Set environment variables:
        export STACKONE_API_KEY="your-stackone-api-key"
        export GOOGLE_API_KEY="your-google-api-key"
    4. Run: python examples/calendly_agent.py
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
    # Discovers tools from your connected providers
    plugin = StackOnePlugin()

    # Optionally filter by provider or scope to a specific account:
    # plugin = StackOnePlugin(providers=["calendly"], account_id="your-account-id")

    tools = plugin.get_tools()
    print(f"Discovered {len(tools)} Calendly tools\n")

    # Create agent with StackOne tools
    agent = Agent(
        model="gemini-2.5-flash",
        name="calendly_agent",  # replace with your agent name
        description="Manages scheduling via Calendly through StackOne.",
        instruction=(
            "You are a scheduling assistant powered by StackOne and Calendly. "
            "You help users manage their scheduling by listing event types "
            "and checking scheduled events.\n\n"
            "Always be helpful and provide clear, organized responses."
        ),
        tools=tools,
    )

    # Recommended: use App to register the plugin
    app = App(name="calendly_app", root_agent=agent, plugins=[plugin])

    async with InMemoryRunner(app=app) as runner:
        prompt = "Get my most recent scheduled meeting from Calendly."
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
