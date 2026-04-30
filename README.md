# stackone-adk

Google ADK plugin for connecting agents to 200+ SaaS providers via [StackOne](https://stackone.com).

StackOne provides a unified API gateway for HRIS, ATS, CRM, scheduling, and more. This plugin dynamically discovers available tools from StackOne's API and exposes them as native Google ADK tools, no hardcoded tool definitions needed.

## Installation

```bash
pip install stackone-adk
```

Or with uv:

```bash
uv add stackone-adk
```

## Configuration

### StackOne API Key

Get your API key from the [StackOne Dashboard](https://app.stackone.com).

```bash
# Environment variable (recommended)
export STACKONE_API_KEY="your-stackone-api-key"
```

Or pass directly:

```python
plugin = StackOnePlugin(api_key="your-stackone-api-key")
```

### Google API Key

Get your API key from [Google AI Studio](https://aistudio.google.com/apikey). This key is required to access Google's Gemini models.

```bash
export GOOGLE_API_KEY="your-google-api-key"
```

## Quick Start

In standard ADK, you define tools as Python functions:

```python
# Standard ADK — manual tool functions
def get_current_time(city: str) -> dict:
    """Returns the current time in a specified city."""
    return {"status": "success", "city": city, "time": "10:30 AM"}

root_agent = Agent(
    model="gemini-3.1-pro-preview",
    name="root_agent",
    tools=[get_current_time],
)
```

With StackOne, tools are discovered dynamically from your connected providers — no manual tool definitions needed:

```python
import asyncio
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from stackone_adk import StackOnePlugin

async def main():
    # StackOne replaces manual tool functions
    # Reads STACKONE_API_KEY from env and uses the specified account_id
    plugin = StackOnePlugin(account_id="YOUR_WORKDAY_ACCOUNT_ID")

    agent = Agent(
        model="gemini-3.1-pro-preview",
        name="workday_agent",
        instruction="You are an HR assistant with access to Workday.",
        tools=plugin.get_tools(),  # instead of: tools=[get_current_time]
    )

    app = App(name="workday_app", root_agent=agent, plugins=[plugin])

    async with InMemoryRunner(app=app) as runner:
        response = await runner.run_debug("List the first 3 workers.")
        print(response)

asyncio.run(main())
```

## Usage Patterns

### With App (Recommended)

```python
from google.adk.apps import App
from google.adk.runners import InMemoryRunner

plugin = StackOnePlugin(account_id="YOUR_WORKDAY_ACCOUNT_ID")

agent = Agent(
    model="gemini-3.1-pro-preview",
    name="workday_agent",
    tools=plugin.get_tools(),
)

app = App(name="workday_app", root_agent=agent, plugins=[plugin])

async with InMemoryRunner(app=app) as runner:
    response = await runner.run_debug("List the first 3 workers")
```

### With Runner Directly

```python
from google.adk.runners import InMemoryRunner

plugin = StackOnePlugin(account_id="YOUR_WORKDAY_ACCOUNT_ID")

agent = Agent(
    model="gemini-3.1-pro-preview",
    name="workday_agent",
    tools=plugin.get_tools(),
)

async with InMemoryRunner(app_name="workday_app", agent=agent) as runner:
    response = await runner.run_debug("List the first 3 workers")
```

## Plugin Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str \| None` | `None` | StackOne API key. Falls back to `STACKONE_API_KEY` env var. |
| `account_id` | `str \| None` | `None` | Default account ID for all tools. |
| `base_url` | `str \| None` | `None` | API URL override (default: `https://api.stackone.com`). |
| `plugin_name` | `str` | `"stackone_plugin"` | Plugin identifier for ADK. |
| `providers` | `list[str] \| None` | `None` | Filter by provider names. |
| `actions` | `list[str] \| None` | `None` | Filter by action patterns (supports globs). |
| `account_ids` | `list[str] \| None` | `None` | Scope tools to specific account IDs. |
| `mode` | `Literal["search_and_execute"] \| None` | `None` | Tool registration strategy. See [Search and Execute mode](#search-and-execute-mode). |
| `search` | `SearchConfig \| None` | `None` | Search backend config. Only used when `mode="search_and_execute"`. |
| `execute` | `ExecuteToolsConfig \| None` | `None` | Execution config (account scoping, timeout). Only used when `mode="search_and_execute"`. |
| `timeout` | `float \| None` | `None` | Per-request timeout in seconds for tool execution. |

## Search and Execute Mode

By default, `StackOnePlugin` registers every discovered tool with the agent — fine for one or two providers, but the LLM context balloons quickly when many SaaS accounts are connected. With `mode="search_and_execute"`, the plugin registers exactly **two meta tools** (`tool_search` and `tool_execute`) and lets the model discover and invoke real tools on demand:

```python
from stackone_adk import StackOnePlugin

plugin = StackOnePlugin(
    mode="search_and_execute",
    search={"method": "auto", "top_k": 5},
)

agent = Agent(
    model="gemini-3.1-pro-preview",
    name="multi_saas_agent",
    tools=plugin.get_tools(),
)
```

**When to use:** more than ~5 connected providers, or whenever the full tool list would dominate the model's context window.

**How it works:** the LLM calls `tool_search("...")` to get a short list of candidate tools (name, description, parameter schema), then calls `tool_execute(tool_name, parameters)` with the chosen one. Both calls round-trip to StackOne's AI Integration Gateway via the SDK.

**Notes:**
- `providers` and `actions` filters are ignored in this mode (scoping happens via `account_ids` and the LLM's search query). A warning is logged if you pass them.
- Search defaults to `{"method": "auto"}` (semantic search with local BM25+TF-IDF fallback). Pass `search={"method": "semantic"}` or `search={"method": "local"}` to force one backend.
- The connector list embedded in the meta tools' descriptions is captured at plugin construction time. If you link new accounts after the plugin starts, restart the agent to pick them up.

See [`examples/search_and_execute_agent.py`](examples/search_and_execute_agent.py) for a complete runnable example.

## Tool Filtering

### By Account ID (Recommended)

Scope tools to specific connected accounts. This is the recommended approach to ensure your agent only accesses the intended accounts:

```python
# Single account
plugin = StackOnePlugin(account_id="YOUR_ACCOUNT_ID")

# Multiple accounts
plugin = StackOnePlugin(account_ids=["acct-hibob-1", "acct-bamboohr-1"])
```

### By Provider

Filter tools to specific SaaS providers:

```python
# Single provider
plugin = StackOnePlugin(providers=["workday"])

# Multiple providers
plugin = StackOnePlugin(providers=["hibob", "bamboohr"])
```

### By Action Pattern

Use glob patterns to filter specific actions:

```python
# Read-only operations
plugin = StackOnePlugin(actions=["*_list_*", "*_get_*"])

# Specific actions
plugin = StackOnePlugin(actions=["workday_list_workers", "workday_get_worker*"])
```

### Combining Filters

```python
plugin = StackOnePlugin(
    providers=["hibob", "bamboohr"],
    actions=["*_list_*", "*_get_*"],
    account_ids=["acct-hibob-1", "acct-bamboohr-1"],
)
```

## Available Tools

Unlike plugins with a fixed set of tools, StackOne tools are **dynamically discovered** from your connected providers via the StackOne API. The available tools depend on which SaaS providers you have connected in your [StackOne Dashboard](https://app.stackone.com).
Print discovered tools:

```python
plugin = StackOnePlugin(account_id="YOUR_ACCOUNT_ID", providers=["workday"])
for tool in plugin.get_tools():
    print(f"{tool.name}: {tool.description}")
```

## Examples

See the [`examples/`](examples/) directory:

| Example | Description |
|---------|-------------|
| [`workday_agent.py`](examples/workday_agent.py) | Workday HR agent — default mode, all Workday tools |
| [`search_and_execute_agent.py`](examples/search_and_execute_agent.py) | Workday agent using `mode="search_and_execute"` (2 meta tools) |

## Development

```bash
git clone https://github.com/StackOneHQ/stackone-adk-plugin.git
cd stackone-adk-plugin
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Lint and type check:

```bash
ruff check stackone_adk/ tests/
mypy stackone_adk/
```

Try an example (requires a Workday account connected in your [StackOne Dashboard](https://app.stackone.com)):

```bash
export STACKONE_API_KEY="your-stackone-api-key"
export STACKONE_ACCOUNT_ID="your-workday-account-id"
export GOOGLE_API_KEY="your-google-api-key"
uv run examples/workday_agent.py
```

## License

Apache 2.0 — see [LICENSE](LICENSE).

## References

- [StackOne Documentation](https://docs.stackone.com/)
- [StackOne Python SDK](https://github.com/StackOneHQ/stackone-ai-python)
- [Google ADK Documentation](https://google.github.io/adk-docs/)
