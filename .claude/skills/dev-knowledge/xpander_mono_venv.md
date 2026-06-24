# xpander-mono — Single Root Virtualenv

**Scope**: Any Python work in `/agent/data/dev/xpander-mono` (running services, installing deps, running tests, lint, pre-commit, scripts).

---

## 1. The Rule — One venv at the Repo Root

`xpander-mono` uses a **single shared virtualenv** at the repo root: `/agent/data/dev/xpander-mono/.venv`.

- **Never** create per-service or per-package venvs inside `services/*` or `packages/*`.
- **Always** activate the root venv before any `pip`, `pytest`, `python`, lint, or service command:
  ```bash
  cd /agent/data/dev/xpander-mono
  source .venv/bin/activate
  ```
- This matches the guidance in the repo's `AGENTS.md`, `CLAUDE.md`, and `README.md`.

---

## 2. Bootstrap — Use `createEnvironment.sh` Non-Interactively

The repo ships `createEnvironment.sh` at the root. It is **interactive** — it asks two questions:

1. `Do you want to proceed? (y/n):`
2. `Which services do you want to install dependencies for?` (space-separated names, or `all`)

It also **deletes** any existing `.venv/` before recreating it. So treat it as a full reset.

### Recommended invocation (agent-friendly)

Feed both answers via stdin using a here-string. Always run from the repo root.

```bash
cd /agent/data/dev/xpander-mono

# Full install — all services
printf 'y\nall\n' | bash createEnvironment.sh

# Selective install — only the services you need (space-separated)
printf 'y\nagent-worker api\n' | bash createEnvironment.sh

# Minimal install — just base packages, no service deps
printf 'y\n\n' | bash createEnvironment.sh
```

Notes:
- Use `printf` (not `echo -e`) for portable `\n` handling.
- Do **not** use `yes y` — the second prompt expects service names, not `y`.
- Do **not** pipe with `< /dev/null` — both reads will fail and the script exits/errors.
- The script `source`s `.venv/bin/activate` inside its own subshell only; that activation does **not** persist to your shell. You must re-activate after it finishes (see §3).
- Expect a long run (several minutes for `all`). Bump the bash tool timeout: `timeout=1500` or higher.

### What the script does (for reference)

1. `rm -rf .venv/`
2. `python3 -m venv .venv`
3. Activates `.venv` (in its own subshell)
4. Installs `requirements.txt` for chosen services under `services/`
5. Installs `packages/xpander_dev_utils` requirements + editable install
6. Installs `pylint`

---

## 2a. ⚠️ Post-Bootstrap Fix — Editable `xpander_dev_utils` Import

This sandbox sets `PIP_TARGET=/agent/data/.persist/python/lib` (and includes it in `PYTHONPATH`), so every `pip install` is redirected to that shared persist dir instead of the venv's site-packages. Most packages still work (they're on `PYTHONPATH`), **but editable installs (`pip install -e`) write a `.pth` file that Python only auto-loads from real site-packages directories**. The persist dir is not one, so `import xpander_dev_utils` fails out of the box after running `createEnvironment.sh`.

**Verified symptom:**
```text
ModuleNotFoundError: No module named 'xpander_dev_utils'
```
while `pip show xpander_dev_utils` still reports it as installed (Location: `/agent/data/.persist/python/lib`, Editable project location: `.../packages/xpander_dev_utils`).

**Fix — reinstall the editable into the real venv site-packages by clearing `PIP_TARGET` for that single command:**
```bash
cd /agent/data/dev/xpander-mono
source .venv/bin/activate
PIP_TARGET= pip install -e packages/xpander_dev_utils --no-deps
python -c "import xpander_dev_utils; print(xpander_dev_utils.__file__)"
# → /agent/data/dev/xpander-mono/packages/xpander_dev_utils/src/xpander_dev_utils/__init__.py
```

Notes:
- `PIP_TARGET=` (empty) on the same line overrides the env var only for that command.
- `--no-deps` skips re-resolving runtime deps that are already on `PYTHONPATH` via the persist dir.
- Always run this **right after** `createEnvironment.sh` finishes, before any service code that imports `xpander_dev_utils`.
- Same pattern applies if you ever need to add another editable install in this monorepo.

---

## 3. Activate Before Any Python Work

After bootstrap (or in any new shell), always activate before running anything Python-related:

```bash
cd /agent/data/dev/xpander-mono
source .venv/bin/activate
which python  # sanity check — must point inside .venv
```

For one-off commands without persisting activation:

```bash
cd /agent/data/dev/xpander-mono && source .venv/bin/activate && pytest services/api/tests
```

---

## 4. Adding / Updating Dependencies

- Add deps to the relevant `services/<svc>/requirements.txt` or `packages/<pkg>/requirements.txt`.
- Then either:
  - Re-run `createEnvironment.sh` (full reset), **or**
  - Targeted install into the existing root venv:
    ```bash
    source .venv/bin/activate
    pip install -r services/<svc>/requirements.txt
    ```
- Never create a sibling venv to "isolate" a service — breaks the monorepo convention.

---

## 5. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `command not found: pytest` / wrong `python` | venv not activated. `source .venv/bin/activate` from repo root. |
| Script hangs forever | You forgot to feed stdin. Use the `printf 'y\n...\n' \| bash createEnvironment.sh` form. |
| `.venv` missing after script | Script was canceled at the `y/n` prompt, or stdin closed early. Re-run with the `printf` pattern. |
| Import errors for `xpander_dev_utils` | `PIP_TARGET` redirected the editable install away from the venv. Apply the fix in §2a: `PIP_TARGET= pip install -e packages/xpander_dev_utils --no-deps`. |
| Tool timeout during `all` install | Increase `xpworkspace-bash` `timeout` (e.g. 1500–1800). |

---

## 6. Quick Reference

```bash
# First-time / full reset (all services) — then fix editable install
cd /agent/data/dev/xpander-mono && printf 'y\nall\n' | bash createEnvironment.sh
source .venv/bin/activate && PIP_TARGET= pip install -e packages/xpander_dev_utils --no-deps

# Selective
cd /agent/data/dev/xpander-mono && printf 'y\nagent-worker api\n' | bash createEnvironment.sh
source .venv/bin/activate && PIP_TARGET= pip install -e packages/xpander_dev_utils --no-deps

# Daily use
cd /agent/data/dev/xpander-mono && source .venv/bin/activate
```

> One repo, one venv at the root. Never per-service. Always feed stdin to the bootstrap script.
