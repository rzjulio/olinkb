# Changelog

All notable changes to this project will be documented in this file.

## 0.1.0 - 2026-04-11

Initial public release of the OlinKB foundation slice.

- Added the OlinKB MCP server with `boot_session`, `remember`, `save_memory`, `end_session`, and `forget`
- Added PostgreSQL-backed storage, migration runner, local session state, and read cache
- Added the interactive `--init` flow with repository/global installation scope selection
- Added GitHub Release automation for downloadable wheel and source assets
- Added test coverage for CLI behavior, cache behavior, session tracking, and template generation