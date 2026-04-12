# Changelog

All notable changes to this project will be documented in this file.

## 0.1.0 - 2026-04-11

Initial public release of the OlinKB foundation slice.

- Added the FastMCP-based OlinKB server with `boot_session`, `remember`, `save_memory`, `end_session`, and `forget`
- Added PostgreSQL-backed storage, migration runner, local session state, and read cache
- Added the `setup-workspace` one-shot bootstrap command for MCP and repository instructions
- Added GitHub Release automation for downloadable wheel and source assets
- Added test coverage for CLI behavior, cache behavior, session tracking, and template generation