# stackone-adk

Google ADK plugin that gives your agents [StackOne](https://stackone.com)'s 540+ connectors and 33,000+ actions as native ADK tools.

StackOne is integration infrastructure for AI agents. Use this plugin when you're building an ADK agent that acts in your customers' applications as part of your product, or an agent for your own company's systems. When you create the plugin, it loads the actions available to your StackOne account and gives them to your agent as ADK tools: one tool per action by default, or StackOne's search and execute tools, which find and run actions on demand, in `search_and_execute` mode. You don't write or maintain any tool definitions.

## Installation

Requires Python 3.11 or later.

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
    plugin = StackOnePlugin(account_id="STACKONE_ACCOUNT_ID")

    agent = Agent(
        model="gemini-3.1-pro-preview",
        name="stackone_agent",
        instruction="You are an HR assistant with access to tools via StackOne.",
        tools=plugin.get_tools(),  # instead of: tools=[get_current_time]
    )

    app = App(name="stackone_app", root_agent=agent, plugins=[plugin])

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

plugin = StackOnePlugin(account_id="STACKONE_ACCOUNT_ID")

agent = Agent(
    model="gemini-3.1-pro-preview",
    name="stackone_agent",
    tools=plugin.get_tools(),
)

app = App(name="stackone_app", root_agent=agent, plugins=[plugin])

async with InMemoryRunner(app=app) as runner:
    response = await runner.run_debug("List the first 3 workers")
```

### With Runner Directly

```python
from google.adk.runners import InMemoryRunner

plugin = StackOnePlugin(account_id="STACKONE_ACCOUNT_ID")

agent = Agent(
    model="gemini-3.1-pro-preview",
    name="stackone_agent",
    tools=plugin.get_tools(),
)

async with InMemoryRunner(app_name="stackone_app", agent=agent) as runner:
    response = await runner.run_debug("List the first 3 workers")
```

## Plugin Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str \| None` | `None` | StackOne API key. Falls back to `STACKONE_API_KEY` env var. |
| `account_id` | `str \| None` | `None` | Default account ID for all tools. |
| `base_url` | `str \| None` | `None` | API URL override. Falls back to `STACKONE_BASE_URL`, then `https://api.stackone.com`. |
| `plugin_name` | `str` | `"stackone_plugin"` | Plugin identifier for ADK. |
| `providers` | `list[str] \| None` | `None` | Filter by provider names. |
| `actions` | `list[str] \| None` | `None` | Filter by action patterns (supports globs). Ignored in search and execute mode. |
| `account_ids` | `list[str] \| None` | `None` | Scope tools to specific account IDs. |
| `mode` | `Literal["search_and_execute"] \| None` | `None` | Tool registration strategy. See [Search and Execute mode](#search-and-execute-mode). |
| `execute` | `ExecuteToolsConfig \| None` | `None` | Execution config (account scoping, timeout), forwarded to `StackOneToolSet`. |
| `timeout` | `float` | `180.0` | Per-request timeout in seconds for listing and executing tools. |

## Search and Execute Mode

By default, `StackOnePlugin` registers every discovered tool with the agent — fine for one or two providers, but the LLM context balloons quickly when many SaaS accounts are connected. With `mode="search_and_execute"`, the plugin registers StackOne's **search and execute tools** and lets the model find and run actions on demand:

```python
from stackone_adk import StackOnePlugin

plugin = StackOnePlugin(mode="search_and_execute")

agent = Agent(
    model="gemini-3.1-pro-preview",
    name="multi_saas_agent",
    tools=plugin.get_tools(),
)
```

**When to use:** more than ~5 connected providers, or whenever the full tool list would dominate the model's context window.

**How it works:** StackOne serves three tools spanning every account in scope, however many there are:

- `stackone_search_actions` takes a natural-language `query` and returns ranked actions, each with its `action_id`, `input_schema`, an `example_request` and the `available_accounts` it can run on.
- `stackone_execute_action` runs one by `action_id`, with arguments nested under `path`, `query` and `body` as the `example_request` shows. When the action's connector is linked on more than one account, the model passes the chosen one as `stackone_account_id`.
- `stackone_list_accounts` lists the accounts in scope, so the model can resolve an account name to its id.

**Notes:**
- `actions` is ignored in this mode (the LLM's search query selects actions); a warning is logged if you pass it. `providers` and `account_ids` scope the accounts the tools span.
- The connectors named in the tools' descriptions are captured at plugin construction time. If you link new accounts after the plugin starts, restart the agent to pick them up.

See [`examples/search_and_execute_agent.py`](examples/search_and_execute_agent.py) for a complete runnable example.

## Tool Filtering

### By Account ID (Recommended)

Scope tools to specific connected accounts. This is the recommended approach to ensure your agent only accesses the intended accounts:

```python
# Single account
plugin = StackOnePlugin(account_id="STACKONE_ACCOUNT_ID")

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
plugin = StackOnePlugin(account_id="STACKONE_ACCOUNT_ID", providers=["workday"])
for tool in plugin.get_tools():
    print(f"{tool.name}: {tool.description}")
```

## Examples

See the [`examples/`](examples/) directory:

| Example | Description |
|---------|-------------|
| [`workday_agent.py`](examples/workday_agent.py) | Default mode (registers all matching tools); demo uses `actions=[...]` to scope to 3 Workday actions |
| [`search_and_execute_agent.py`](examples/search_and_execute_agent.py) | LLM-driven discovery via `mode="search_and_execute"`, registers StackOne's search and execute tools |

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

### Integration smoke test

The test suite replaces `StackOneToolSet` with a `MagicMock`, so it passes regardless of how
the SDK behaves — it cannot catch an SDK regression. The
[sdk-conformance](https://github.com/StackOneHQ/sdk-conformance) repo carries a smoke script
that drives the real SDK through the real plugin against a mock StackOne API, asserting the
plugin exposes exactly the tool catalog the server listed:

```bash
git clone git@github.com:StackOneHQ/sdk-conformance.git
cd sdk-conformance && pnpm install
./scripts/run_smoke.sh adk
```

It expects `stackone-adk-plugin` and `stackone-ai-python` checked out alongside it; override
with `ADK=` and `SDK_PY=`.

This is not wired into CI because `sdk-conformance` is a private repository and this repo has
no credential configured to clone it. Wiring it up needs a deploy key or PAT secret added
here first.

Try an example (requires at least one provider connected in your [StackOne Dashboard](https://app.stackone.com), e.g. Workday):

```bash
export STACKONE_API_KEY="your-stackone-api-key"
export STACKONE_ACCOUNT_ID="account-id"
export GOOGLE_API_KEY="your-google-api-key"
uv run examples/workday_agent.py
```

## Releasing

Bump version in `pyproject.toml` and `stackone_adk/__init__.py`, update `CHANGELOG.md`, then:

```bash
rm -rf dist/ && uv build && UV_PUBLISH_TOKEN=<pypi-token> uv publish
git tag stackone-adk-vX.Y.Z && git push origin stackone-adk-vX.Y.Z
```

## License

Apache 2.0 — see [LICENSE](LICENSE).

## References

- [StackOne Documentation](https://docs.stackone.com/)
- [StackOne Python SDK](https://github.com/StackOneHQ/stackone-ai-python)
- [Google ADK Documentation](https://google.github.io/adk-docs/)
