# Changelog

## [0.2.0](https://github.com/StackOneHQ/stackone-adk-plugin/compare/stackone-adk-v0.1.0...stackone-adk-v0.2.0) (2026-04-30)


### Features

* **plugin:** add `mode="search_and_execute"` for LLM-driven tool discovery — registers two meta tools (`tool_search`, `tool_execute`) instead of the full catalog
* **plugin:** add `search`, `execute`, `timeout` constructor params (full pass-through to `StackOneToolSet`)
* **exports:** re-export `SearchConfig`, `SearchMode`, `ExecuteToolsConfig` from `stackone_ai` for a single import surface
* **tools:** preserve `StackOneAPIError.status_code`, `response_body`, and `tool_name` in `StackOneAdkTool.run_async` (matches SDK error contract)
* **plugin:** send `User-Agent: stackone-adk-plugin/{version}` on account-discovery HTTP calls
* **examples:** new `search_and_execute_agent.py` demonstrating meta-tool discovery against Workday
* **examples:** rename `calendly_agent.py` → `workday_agent.py`, model bumped to `gemini-3.1-pro-preview`


### Dependencies

* bump `stackone-ai[mcp]` floor to `>=2.8.0` (required for `mode="search_and_execute"`)
* bump `google-adk` floor to `>=1.31.1`


### Documentation

* document `mode="search_and_execute"` usage, `SearchConfig`/`ExecuteToolsConfig` parameters, and when to prefer each mode in `README.md`


## 0.1.0 (2026-01-29)


### Features

* initial release of the StackOne ADK plugin
* dynamic tool discovery from connected SaaS providers via StackOne's MCP endpoint
* automatic account-id discovery with optional `providers` / `actions` / `account_ids` filters
* `StackOneAdkTool` adapter — JSON Schema → `FunctionDeclaration`, sync `execute()` → async `run_async()`
