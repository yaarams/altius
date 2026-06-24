# 📦 Agent Export — Replicate This Agent to Another Instance

This skill packages everything required to clone the current agent's persistent brain (skills, memory, context, plans) **plus the GitHub + git identity** into a portable zip bundle that can be imported into another xpander.ai agent instance with zero onboarding.

> **v2.1 default — auth-bundled mode.** The export now carries the agent's
> `~/.config/gh/hosts.yml`, `.gitconfig`, `.git-credentials`, and `.netrc`
> inside the bundle's `auth/` subdir. The recipient agent comes online as
> `xpander-fullstack-generalist` automatically. Treat the resulting `.zip`
> as a credential. For external sharing use `EXPORT_STRICT=1` (which forces
> `EXPORT_NO_AUTH=1`).

---

## When to Use

- The user asks to "export", "backup", "clone", "replicate", or "share" the agent's skills/memory/knowledge
- Before a major refactor of `workspace/` so we have a snapshot
- When standing up a sister agent that should inherit the same conventions

---

## What Gets Exported

| Source | Included? | Reason |
|---|---|---|
| `workspace/dev-knowledge/skills/` | ✅ | Reusable capabilities — required for replication |
| `workspace/dev-knowledge/memory/` | ✅ | Persistent decisions, lessons learned, architecture |
| `workspace/local/` | ✅ | Specs, docs, plans (`context/plans/*.md`) |
| `workspace/tmp/` | ❌ | Disposable, ephemeral artifacts |
| Local SQLite DB (`task_queue` etc.) | ✅ | Dumped to `memory/db/<table>.sql` (idempotent) so the recipient agent recreates the queue automatically |
| `~/.config/gh/hosts.yml`, `.gitconfig`, `.git-credentials`, `.netrc` | ✅ (default) | Bundled under `auth/` so the recipient comes online as `xpander-fullstack-generalist` without onboarding. Set `EXPORT_NO_AUTH=1` to opt out. |
| Cloned repos under `/agent/data/dev` | ❌ | Tracked separately via git; `known_repos.md` lists them |
| Agent identity / instructions / goals | ✅ (snapshot) | Captured in `manifest.json` for reference |

---

## How It Works

The export is produced by `workspace/dev-knowledge/skills/agent_export.sh`:

1. Creates a timestamped staging dir under `workspace/tmp/export_<ts>/`
2. Copies `skills/`, `memory/`, `context/` into the staging dir
3. Writes `manifest.json` with: timestamp, file inventory + sha256, file counts, total size
4. Writes `REPLICATION_GUIDE.md` explaining how to bootstrap a new agent from the bundle
5. Zips the staging dir to `workspace/tmp/agent_bundle_<ts>.zip`
6. **Also writes a base64 sidecar `agent_bundle_<ts>.zip.b64`** — share this one, NOT the raw zip
7. Prints both paths and the zip's sha256

> ⚠️ **Critical pitfall:** `xpworkspace-file-share` corrupts binary files — the
> CDN re-encodes high bytes as UTF-8, growing the file ~44% and breaking the
> zip's central directory. **Always share the `.b64` sidecar** and instruct the
> recipient to `base64 -d` it locally.

---

## Run It

```bash
# Default: bundle includes auth/ → recipient skips onboarding
bash workspace/dev-knowledge/skills/agent_export.sh

# External sharing: strip auth + fail-fast on any token in skills/memory/context
EXPORT_STRICT=1 bash workspace/dev-knowledge/skills/agent_export.sh
```

Optional env vars:
- `EXPORT_LABEL` — short label appended to the zip name (e.g. `pre-refactor`)
- `EXPORT_OUT_DIR` — output dir (default `workspace/tmp`)
- `EXPORT_NO_AUTH=1` — skip the `auth/` subdir (recipient must run Phase 3)
- `EXPORT_STRICT=1` — abort on any detected token; **also implies `EXPORT_NO_AUTH=1`**
- `AGENT_HOME` — override the source HOME for credential capture (default `/agent/data/.home`)

---

## After Running

1. `xpworkspace-file-share` the **`.b64`** sidecar (NOT the raw zip) to get a public URL
2. Email the URL with these decode instructions:
   ```bash
   curl -L -o bundle.zip.b64 <url>
   base64 -d bundle.zip.b64 > bundle.zip
   unzip bundle.zip
   ```
3. Include the zip's sha256 so the recipient can verify integrity
4. Mention the bundle's `REPLICATION_GUIDE.md` so the recipient knows how to import

---

## Importing Into Another Agent

**Preferred:** use the companion skill `workspace/dev-knowledge/skills/agent_import.md` — it
automates download, base64 decode, sha256 verification, and conflict-aware
merging:

```bash
# Phase 1 — dry-run to see new files / conflicts
bash workspace/dev-knowledge/skills/agent_import.sh --dry-run <bundle-url>

# Phase 2 — apply with the chosen mode
bash workspace/dev-knowledge/skills/agent_import.sh --mode=merge <bundle-url>
```

Manual fallback (per the bundle's `REPLICATION_GUIDE.md`):

1. Download and unzip into the target agent's workspace root
2. Verify checksums via `manifest.json`
3. Read `skills/MUST_READ.md` first, then `skills/known_repos.md`
4. Carry over the agent identity / instructions / goals from `manifest.json` into the target agent's profile (manual step in the xpander.ai UI)

---

## Maintenance

- If new top-level workspace dirs are added (beyond `skills/`, `memory/`, `context/`, `tmp/`), update both this skill and `agent_export.sh` to include them
- Keep `REPLICATION_GUIDE.md` (generated by the script) in sync with current bootstrap rules
