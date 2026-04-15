# Releasing OlinKB

This repository is prepared so the maintainer only needs to update versioned notes, push `main`, and tag a release. The release workflow derives the package version from the pushed tag and applies it to both the base package and the MCP addon during the build.

## Exact Commit Message

For the current initial release:

```bash
git commit -m "Prepare v0.1.0 release"
```

For future releases, reuse the same pattern:

```bash
git commit -m "Prepare vX.Y.Z release"
```

## Pre-Push Checklist

1. Update `docs/CHANGELOG.md` with the new version entry.
2. Add or update `docs/releases/vX.Y.Z.md`.
3. Run the local test suite:

```bash
python -m pytest
```

4. Check the repository status and confirm only intended files changed:

```bash
git status --short
```

5. Commit the release prep changes.
6. Push `main`.
7. Create and push the tag.

## Exact Initial Release Commands

```bash
git add .
git commit -m "Prepare v0.1.0 release"
git push origin main
git tag v0.1.0
git push origin v0.1.0
```

## How Release Notes Work

- If `docs/releases/vX.Y.Z.md` exists for the pushed tag, the release workflow uses it.
- If that file does not exist, the workflow falls back to `docs/releases/TEMPLATE.md` and injects the tag version automatically.

## Outcome

After the tag is pushed, GitHub Actions will:

1. Run tests.
2. Normalize the tag, for example `v0.1.3` -> `0.1.3`, and sync that version into the base package metadata and the MCP addon metadata for the workflow build.
3. Build the base `olinkb` wheel and source tarball.
4. Build the optional `olinkb-mcp` addon wheel and source tarball with the same version and matching `olinkb==...` dependency.
5. Create the GitHub Release.
6. Upload the artifacts as downloadable assets.