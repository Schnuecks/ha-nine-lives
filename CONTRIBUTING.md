# Contributing to Nine Lives

Thanks for your interest! Bug reports, ideas and pull requests are welcome.

## Reporting problems

Use the issue forms: **Bug report** or **Feature request**. For bugs, please add the log
with debug logging for Nine Lives (see the bug report form). German is fine too.

Security problems go to **Security → Report a vulnerability** instead, see
[SECURITY.md](SECURITY.md).

## Pull requests

1. Open an issue first for larger changes, so we can agree on the approach.
2. Set up the development environment and make sure all checks pass:

   ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -r requirements-dev.txt
   ruff check . && ruff format --check . && pytest
   ```

3. Keep swaps safe: everything Nine Lives changes must be shown in the preview first and
   be undoable. Places it cannot change safely are reported, not changed.
4. Update README.md and README.de.md if needed and add a line under "Unreleased" in
   `CHANGELOG.md` if users will notice the change.

The pull request template has a short checklist for this.

## Code layout

| Path | Contents |
|---|---|
| `custom_components/nine_lives/matching.py` | Pairing old and new entities |
| `custom_components/nine_lives/references.py` | Rewriting device references in configs |
| `custom_components/nine_lives/scan.py` | Dashboards, YAML files, where an entity ID is used |
| `custom_components/nine_lives/swap.py` | Planning, applying and undoing a swap, backups |
| `custom_components/nine_lives/energy.py` | Meter sum corrections |
| `custom_components/nine_lives/notice.py` | The notification after a swap |
| `custom_components/nine_lives/websocket.py` | WebSocket commands for the panel |
| `custom_components/nine_lives/frontend/` | The sidebar panel (plain JavaScript, no build step) |
| `tests/` | Tests, including the recorder behaviour the swap relies on |

## License

By contributing you agree that your contribution is released under the
[MIT License](LICENSE).
