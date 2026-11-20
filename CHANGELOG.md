# Changelog

## 0.3.0 (unreleased)

Built on StackOne AI SDK 3.0, which lists and runs every tool over StackOne's MCP endpoint.

### Breaking changes

* **python:** requires Python 3.11 or later, as `stackone-ai` 3.0 does.
* **dependencies:** depends on `stackone-ai>=3.0.0,<4.0.0`. The `[mcp]` extra is gone: MCP is a core dependency of the SDK.
* **plugin:** `search=` is removed, and with it the `SearchConfig` and `SearchMode` exports. Search runs on StackOne's server, so there is no backend to configure.
* **plugin:** in `mode="search_and_execute"` the tools are StackOne's `stackone_search_actions` and `stackone_execute_action` (with `stackone_list_accounts` when more than one account is in scope), spanning every account in scope, at most 50, in place of `tool_search` and `tool_execute`. Update prompts that name the old tools. `stackone_execute_action` takes `action_id` and arguments nested under `path`, `query` and `body`, plus `stackone_account_id` when the connector is linked on more than one account.
* **tools:** a tool returns the server's result as it wrote it, `{"isError": false, "result": ...}`, not the unwrapped payload.
* **tools:** a tool's declared `required` list is the one StackOne served, not one derived from each property's `nullable` marker.

### Changes

* **plugin:** account discovery is the SDK's. With no account given, the plugin uses every active shared account on the API key. If the tools cannot be loaded, it still logs a warning and registers no tools.
* **plugin:** `base_url` falls back to `STACKONE_BASE_URL` before the default.
* **ci:** the matrix runs Python 3.11 to 3.13.

## [0.2.1](https://github.com/StackOneHQ/stackone-adk-plugin/compare/v0.2.0...v0.2.1) (2026-10-20)


### Dependencies

* cap `stackone-ai[mcp]` below 3.0.0, so new installs don't resolve the SDK v3 release, which removes `SearchConfig` and `SearchMode` ([#27](https://github.com/StackOneHQ/stackone-adk-plugin/pull/27))


### Documentation

* update the plugin description to current StackOne positioning ([#28](https://github.com/StackOneHQ/stackone-adk-plugin/pull/28))

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
