# OlinKB __VERSION__

Release summary for __VERSION__.

## Included

- Describe the user-visible improvements in this release
- Describe any operational or packaging changes
- Mention any migration or setup changes if relevant

## Developer Installation

1. Download `olinkb-__VERSION__-py3-none-any.whl` from this release.
2. Install it with `pipx`:

```bash
pipx install ./olinkb-__VERSION__-py3-none-any.whl
```

3. Configure the current repository against the team PostgreSQL server:

```bash
olinkb setup-workspace --pg-url postgresql://usuario:password@host:5432/olinkb --team mi-equipo --project mi-proyecto
```

4. Verify the CLI is available:

```bash
olinkb --help
```

## Notes

- Add any runtime limitations, compatibility notes, or rollout guidance here.