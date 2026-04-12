# Releasing OlinKB

This repository is prepared so the maintainer only needs to update versioned notes, push `main`, and tag a release.

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

1. Confirm the package version is correct in `pyproject.toml` and `src/olinkb/__init__.py`.
2. Update `CHANGELOG.md` with the new version entry.
3. Add or update `docs/releases/vX.Y.Z.md`.
4. Run the local test suite:

```bash
python -m pytest
```

5. Check the repository status and confirm only intended files changed:

```bash
git status --short
```

6. Commit the release prep changes.
7. Push `main`.
8. Create and push the tag.

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
2. Build the wheel and source tarball.
3. Create the GitHub Release.
4. Upload the artifacts as downloadable assets.