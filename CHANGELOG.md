# Changelog

## [0.2.0](https://github.com/StackOneHQ/stackone-adk-plugin/compare/stackone-adk-v0.1.0...stackone-adk-v0.2.0) (2026-05-05)


### Features

* **plugin:** add `mode="search_and_execute"` for LLM-driven tool discovery — registers two meta tools (`tool_search`, `tool_execute`) instead of the full catalog
* **plugin:** add `search` and `execute` config params, forwarded to `StackOneToolSet`
* **exports:** re-export `SearchConfig`, `SearchMode`, `ExecuteToolsConfig` from `stackone_ai`
* **examples:** new `search_and_execute_agent.py` demonstrating meta-tool discovery


### Dependencies

* bump `stackone-ai[mcp]` floor to `>=2.8.0` (required for `mode="search_and_execute"`)


## 0.1.0 (2026-01-29)


### Features

* initial release of the StackOne ADK plugin
* dynamic tool discovery from connected SaaS providers via StackOne's MCP endpoint
* automatic account-id discovery with optional `providers` / `actions` / `account_ids` filters
* `StackOneAdkTool` adapter — JSON Schema → `FunctionDeclaration`, sync `execute()` → async `run_async()`
