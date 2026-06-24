#!/usr/bin/env bash
# agent_export.sh — Bundle skills, memory, and context into a portable zip.
#
# v2.1 changes (auth-bundled mode — DEFAULT for internal cloning):
#   - Bundles the agent's gh auth + git identity files into a dedicated
#     `auth/` subdir of the bundle (hosts.yml, .gitconfig, .git-credentials,
#     .netrc), so the recipient agent comes online as the same identity
#     (xpander-fullstack-generalist) without a separate Phase 3 onboarding.
#   - The auth files are EXEMPT from the secret-exclusion globs and from the
#     pattern-scrub (they live OUTSIDE skills/ memory/ context/ — the scrub
#     only walks those three dirs). The token therefore lands in the zip
#     verbatim. This is the explicit operator preference.
#   - Set EXPORT_NO_AUTH=1 to fall back to the v2.0 behaviour (no auth in
#     bundle, recipient must run Phase 3 onboarding).
#   - manifest.bundle_version is bumped to 2.1; auth_included reflects the
#     actual state; onboarding_required is now `false` whenever auth_included
#     is true.
#
# v2.0 baseline:
#   - Single .zip output (no .b64 sidecar). xpworkspace-file-share now serves
#     binaries correctly.
#   - Hard-excludes secret directories and files inside skills/memory/context
#     (workspace/dev-knowledge/memory/secrets/**, .env*, *.pem, *.key, id_rsa*, .netrc,
#     .git-credentials, .backups/, *.bak.*). The new `auth/` subdir is
#     populated AFTER this copy stage and is intentionally not subject to
#     these excludes.
#   - Pattern-scrubs every text file UNDER skills/memory/context for known
#     token shapes (gh PATs, OpenAI, AWS, Slack, generic Bearer, xpander) and
#     replaces matches with <REDACTED:<kind>>. Emits scrub_report.json into
#     the bundle. The auth/ dir is NOT walked by the scrubber.
#   - EXPORT_STRICT=1 aborts the export if any token is detected inside
#     skills/memory/context (use before sharing externally — note that
#     EXPORT_STRICT=1 also implies EXPORT_NO_AUTH=1, since strict mode is for
#     external sharing where bundling creds is unsafe).
#
# ⚠️  Bundles produced with auth_included=true contain a live GitHub PAT.
#     Treat the resulting .zip as a credential. Do not share externally.
#
# See workspace/dev-knowledge/skills/agent_export.md for the full skill spec.

set -euo pipefail

# ---- Config -----------------------------------------------------------------
WORKSPACE_ROOT="${WORKSPACE_ROOT:-workspace}"
OUT_DIR="${EXPORT_OUT_DIR:-${WORKSPACE_ROOT}/tmp}"
LABEL="${EXPORT_LABEL:-}"
STRICT="${EXPORT_STRICT:-0}"
NO_AUTH="${EXPORT_NO_AUTH:-0}"
AGENT_HOME_DIR="${AGENT_HOME:-/agent/data/.home}"
# strict mode is for external sharing — never carry creds in that case
if [[ "$STRICT" == "1" ]]; then NO_AUTH=1; fi
TS="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ -n "$LABEL" ]]; then
  STAGE_NAME="agent_bundle_${TS}_${LABEL}"
else
  STAGE_NAME="agent_bundle_${TS}"
fi

STAGE_DIR="${OUT_DIR}/${STAGE_NAME}"
ZIP_PATH="${OUT_DIR}/${STAGE_NAME}.zip"

mkdir -p "$STAGE_DIR"

# ---- Exclusion patterns -----------------------------------------------------
# Applied during the staging copy. Defence-in-depth: secrets dir + any .env,
# private keys, credential files, local backup caches.
EXCLUDES=(
  --exclude='secrets'
  --exclude='secrets/**'
  --exclude='.env'
  --exclude='.env.*'
  --exclude='*.env'
  --exclude='*.pem'
  --exclude='*.key'
  --exclude='id_rsa*'
  --exclude='id_ed25519*'
  --exclude='.netrc'
  --exclude='.git-credentials'
  --exclude='.backups'
  --exclude='.backups/**'
  --exclude='*.bak.*'
)

# ---- Copy persistent dirs (with excludes) -----------------------------------
# Prefer rsync; fall back to a python copy that honours the same excludes.
if command -v rsync >/dev/null 2>&1; then
  for sub in skills memory context; do
    src="${WORKSPACE_ROOT}/${sub}"
    if [[ -d "$src" ]]; then
      mkdir -p "${STAGE_DIR}/${sub}"
      rsync -a "${EXCLUDES[@]}" "${src}/" "${STAGE_DIR}/${sub}/"
    else
      echo "warn: ${src} not found, skipping" >&2
    fi
  done
else
  # Python fallback — same exclude semantics (fnmatch over basename + path segments)
  python3 - "$WORKSPACE_ROOT" "$STAGE_DIR" <<'PY'
import fnmatch, os, shutil, sys
ws_root, stage = sys.argv[1], sys.argv[2]
# Mirrors EXCLUDES in shell.
EX_ANY_SEGMENT = {'secrets', '.backups'}
EX_BASENAME_GLOBS = [
    '.env', '.env.*', '*.env', '*.pem', '*.key',
    'id_rsa*', 'id_ed25519*', '.netrc', '.git-credentials', '*.bak.*',
]
def excluded(rel):
    parts = rel.split(os.sep)
    for p in parts:
        if p in EX_ANY_SEGMENT:
            return True
    base = parts[-1]
    for g in EX_BASENAME_GLOBS:
        if fnmatch.fnmatch(base, g):
            return True
    return False
for sub in ('skills', 'memory', 'context'):
    src = os.path.join(ws_root, sub)
    if not os.path.isdir(src):
        print(f'warn: {src} not found, skipping', file=sys.stderr)
        continue
    for root, dirs, files in os.walk(src):
        rel_root = os.path.relpath(root, src)
        # prune excluded dirs in-place
        dirs[:] = [d for d in dirs if not excluded(os.path.join(rel_root, d) if rel_root != '.' else d)]
        for f in files:
            rel = os.path.join(rel_root, f) if rel_root != '.' else f
            if excluded(rel):
                continue
            src_p = os.path.join(root, f)
            dst_p = os.path.join(stage, sub, rel)
            os.makedirs(os.path.dirname(dst_p), exist_ok=True)
            shutil.copy2(src_p, dst_p)
PY
fi

# ---- Dump local SQLite DB tables (task_queue, etc.) ------------------------
# The local DB holds the persistent task queue. We export it as portable SQL
# under memory/db/<table>.sql so a recipient agent can rebuild its queue
# idempotently (CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE on PK).
# schedule_id values are nulled because they reference the source agent's own
# scheduler instance.
DB_DIR="${STAGE_DIR}/memory/db"
mkdir -p "$DB_DIR"
LOCAL_DB="${LOCAL_DB:-/agent/data/data/local_db.db}"
if [[ -f "$LOCAL_DB" ]]; then
  python3 - "$LOCAL_DB" "$DB_DIR" <<'__PYDB__'
import os, sqlite3, sys
db_path, out_dir = sys.argv[1], sys.argv[2]
conn = sqlite3.connect(db_path)
cur = conn.cursor()
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
).fetchall()]
for t in tables:
    schema_rows = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type IN ('table','index') AND tbl_name=? AND sql IS NOT NULL ORDER BY type DESC",
        (t,)
    ).fetchall()
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})").fetchall()]
    rows = cur.execute(f"SELECT * FROM {t}").fetchall()
    out = os.path.join(out_dir, f"{t}.sql")
    with open(out, "w") as fh:
        fh.write(f"-- Dump of table `{t}` ({len(rows)} row(s))\n")
        fh.write("-- Idempotent: CREATE ... IF NOT EXISTS + INSERT OR IGNORE on PK.\n\n")
        for (sql,) in schema_rows:
            sql = sql.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
            sql = sql.replace("CREATE INDEX ", "CREATE INDEX IF NOT EXISTS ", 1)
            sql = sql.replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX IF NOT EXISTS ", 1)
            fh.write(sql.rstrip(";") + ";\n")
        fh.write("\n")
        for row in rows:
            vals = []
            for col, v in zip(cols, row):
                if t == "task_queue" and col == "schedule_id":
                    vals.append("NULL"); continue
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append("'" + str(v).replace("'", "''") + "'")
            collist = ", ".join(cols)
            vlist = ", ".join(vals)
            fh.write(f"INSERT OR IGNORE INTO {t} ({collist}) VALUES ({vlist});\n")
    print(f"dumped {t}: {len(rows)} row(s) -> {out}", file=sys.stderr)
conn.close()
__PYDB__
else
  echo "info: local DB not found at $LOCAL_DB — skipping DB dump" >&2
fi

# ---- Capture gh auth + git identity (auth-bundled mode) --------------------
# When NO_AUTH=0 (default), copy the live credential files into bundle/auth/
# so the recipient agent can wear the same identity automatically. This
# subdir is created AFTER the skills/memory/context copy and is NOT walked by
# the scrubber (the scrub only descends into the three managed dirs), so the
# token lands verbatim. EXPORT_STRICT=1 forces NO_AUTH=1 (set above).
AUTH_INCLUDED=0
GH_USER_IN_BUNDLE=""
AUTH_DIR="${STAGE_DIR}/auth"
if [[ "$NO_AUTH" != "1" ]]; then
  mkdir -p "$AUTH_DIR/.config/gh"
  copied=0
  GH_HOSTS="${AGENT_HOME_DIR}/.config/gh/hosts.yml"
  GIT_CONFIG="${AGENT_HOME_DIR}/.gitconfig"
  GIT_CREDS="${AGENT_HOME_DIR}/.git-credentials"
  NETRC_F="${AGENT_HOME_DIR}/.netrc"
  if [[ -f "$GH_HOSTS"   ]]; then cp "$GH_HOSTS"   "$AUTH_DIR/.config/gh/hosts.yml"; copied=$((copied+1)); fi
  if [[ -f "$GIT_CONFIG" ]]; then cp "$GIT_CONFIG" "$AUTH_DIR/.gitconfig";          copied=$((copied+1)); fi
  if [[ -f "$GIT_CREDS"  ]]; then cp "$GIT_CREDS"  "$AUTH_DIR/.git-credentials";    copied=$((copied+1)); fi
  if [[ -f "$NETRC_F"    ]]; then cp "$NETRC_F"    "$AUTH_DIR/.netrc";              copied=$((copied+1)); fi
  chmod 600 "$AUTH_DIR/.config/gh/hosts.yml" 2>/dev/null || true
  chmod 600 "$AUTH_DIR/.git-credentials"     2>/dev/null || true
  chmod 600 "$AUTH_DIR/.netrc"               2>/dev/null || true
  chmod 644 "$AUTH_DIR/.gitconfig"           2>/dev/null || true
  if [[ "$copied" -ge 1 ]]; then
    AUTH_INCLUDED=1
    GH_USER_IN_BUNDLE="$(awk -F': *' '/^[[:space:]]+user:/ {print $2; exit}' "$AUTH_DIR/.config/gh/hosts.yml" 2>/dev/null || true)"
    if [[ -n "$GH_USER_IN_BUNDLE" && "$GH_USER_IN_BUNDLE" != "xpander-fullstack-generalist" ]]; then
      echo "warn: bundled gh user is '$GH_USER_IN_BUNDLE', not 'xpander-fullstack-generalist'" >&2
    fi
    cat > "$AUTH_DIR/README.md" <<EOF
# auth/ - GitHub + git identity for the imported agent

Applied verbatim by agent_import.sh (Phase 2) when manifest.auth_included is true.
The recipient agent comes online as xpander-fullstack-generalist without Phase 3.

Layout:
- .config/gh/hosts.yml  - gh CLI auth (0600)
- .gitconfig            - git user.name / user.email (0644)
- .git-credentials      - https push creds (0600)
- .netrc                - curl + tools that read .netrc (0600)

WARNING: contains a live GitHub PAT. Treat the bundle as a secret.
For external sharing use EXPORT_STRICT=1 (which forces EXPORT_NO_AUTH=1).
EOF
    echo "-> auth bundled: $copied file(s) under auth/ (gh user: ${GH_USER_IN_BUNDLE:-unknown})" >&2
  else
    echo "info: NO_AUTH=0 but no credential files were found under $AGENT_HOME_DIR -- skipping auth bundle" >&2
    rm -rf "$AUTH_DIR"
  fi
else
  echo "info: NO_AUTH=1 -- skipping auth bundle (recipient must run Phase 3 onboarding)" >&2
fi

# ---- Pattern scrub (post-copy, pre-zip) -------------------------------------
# Rewrites token-shaped strings inside text files in the staging dir.
# Emits scrub_report.json. If EXPORT_STRICT=1, aborts on any hit.
# NOTE: the scrubber only walks skills/, memory/, context/ -- it intentionally
# skips the auth/ subdir so bundled credentials are preserved.
SCRUB_REPORT="${STAGE_DIR}/scrub_report.json"
SCRUB_HITS=$(python3 - "$STAGE_DIR" "$STRICT" "$SCRUB_REPORT" <<'PY'
import json, os, re, sys
stage, strict, report_path = sys.argv[1], sys.argv[2] == '1', sys.argv[3]

# (kind, regex). Keep regexes tight enough to avoid stomping example text;
# we still allow opt-out via the literal marker '<noscrub>' on the same line.
PATTERNS = [
    ('github_pat_classic',  re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}')),
    ('github_pat_finegrain', re.compile(r'github_pat_[A-Za-z0-9_]{60,}')),
    ('openai_key',          re.compile(r'sk-(?:proj-)?[A-Za-z0-9_\-]{20,}')),
    ('aws_access_key_id',   re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b')),
    ('aws_secret_access_key', re.compile(r'aws_secret_access_key\s*=\s*([A-Za-z0-9/+=]{40})')),
    ('slack_token',         re.compile(r'xox[abprs]-[A-Za-z0-9-]{10,}')),
    ('bearer_token',        re.compile(r'(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}')),
    ('xpander_key',         re.compile(r'\bxpd_[A-Za-z0-9]{20,}')),
]

# Detect text vs binary by sniffing the first 8KB.
def is_text(path):
    try:
        with open(path, 'rb') as fh:
            chunk = fh.read(8192)
    except OSError:
        return False
    if b'\x00' in chunk:
        return False
    # Reject obvious binaries by extension to avoid mangling.
    if path.lower().endswith(('.zip', '.png', '.jpg', '.jpeg', '.gif', '.pdf',
                              '.gz', '.tar', '.tgz', '.woff', '.woff2', '.ico',
                              '.bin', '.so', '.dylib', '.exe')):
        return False
    try:
        chunk.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False

report = {'files': [], 'totals': {}}
totals = {k: 0 for k, _ in PATTERNS}
files_with_hits = 0

# Only scrub the three managed dirs. The auth/ subdir is intentionally
# excluded from this walk so bundled credentials survive.
MANAGED_DIRS = ('skills', 'memory', 'context')
walk_roots = [os.path.join(stage, d) for d in MANAGED_DIRS if os.path.isdir(os.path.join(stage, d))]
for walk_root in walk_roots:
  for root, _, names in os.walk(walk_root):
    for n in names:
        p = os.path.join(root, n)
        if not is_text(p):
            continue
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        new_text = text
        per_file = {}
        for kind, rx in PATTERNS:
            def repl(m, _kind=kind, _per=per_file):
                # honour <noscrub> opt-out: skip if the literal marker is
                # present anywhere on the same line as the match.
                line_start = new_text.rfind('\n', 0, m.start()) + 1
                line_end = new_text.find('\n', m.end())
                line = new_text[line_start: line_end if line_end != -1 else len(new_text)]
                if '<noscrub>' in line:
                    return m.group(0)
                _per[_kind] = _per.get(_kind, 0) + 1
                return f'<REDACTED:{_kind}>'
            new_text = rx.sub(repl, new_text)
        if per_file:
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(new_text)
            rel = os.path.relpath(p, stage)
            report['files'].append({'path': rel, 'hits': per_file})
            files_with_hits += 1
            for k, v in per_file.items():
                totals[k] += v

report['scope'] = list(MANAGED_DIRS)
report['totals'] = totals
report['files_with_hits'] = files_with_hits
report['strict'] = strict
report['total_redactions'] = sum(totals.values())
with open(report_path, 'w') as fh:
    json.dump(report, fh, indent=2, sort_keys=True)
print(report['total_redactions'])
if strict and report['total_redactions'] > 0:
    # exit 7 — distinct so the shell wrapper can recognise strict-fail
    sys.exit(7)
PY
) || {
  rc=$?
  if [[ $rc -eq 7 ]]; then
    echo >&2
    echo "❌ EXPORT_STRICT=1: aborting because tokens were detected." >&2
    echo "   See: $SCRUB_REPORT" >&2
    echo "   Remove or redact the offending content, then re-run." >&2
    rm -rf "$STAGE_DIR"
    exit 7
  fi
  echo "scrub failed (exit $rc)" >&2
  exit $rc
}

# ---- Build manifest.json ----------------------------------------------------
MANIFEST="${STAGE_DIR}/manifest.json"
python3 - "$STAGE_DIR" "$TS" "$LABEL" "$SCRUB_REPORT" "$AUTH_INCLUDED" "$GH_USER_IN_BUNDLE" > "$MANIFEST" <<'PY'
import hashlib, json, os, sys
stage, ts, label, scrub_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
auth_included = sys.argv[5] == '1'
gh_user = sys.argv[6] or 'xpander-fullstack-generalist'

with open(scrub_path) as fh:
    scrub = json.load(fh)

files = []
total_bytes = 0
for root, _, names in os.walk(stage):
    for n in names:
        p = os.path.join(root, n)
        rel = os.path.relpath(p, stage)
        if rel == 'manifest.json':
            continue
        with open(p, 'rb') as fh:
            data = fh.read()
        files.append({
            'path': rel,
            'size': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
        })
        total_bytes += len(data)
files.sort(key=lambda f: f['path'])

manifest = {
    'bundle_version': '2.1',
    'created_utc': ts,
    'label': label or None,
    'agent': {
        'identity': 'xpander-fullstack-generalist',
        'email': 'ai_employee_2@xpander.ai',
        'role': 'xpander.ai developer',
        'gh_user': gh_user,
    },
    'secrets_excluded': not auth_included,
    'auth_included': auth_included,
    'auth_paths': sorted([f['path'] for f in files if f['path'].startswith('auth/')]) if auth_included else [],
    'scrub': {
        'strict': scrub['strict'],
        'redactions': scrub['total_redactions'],
        'files_with_redactions': scrub['files_with_hits'],
        'kinds': {k: v for k, v in scrub['totals'].items() if v > 0},
        'scope': scrub.get('scope', ['skills', 'memory', 'context']),
    },
    'onboarding_required': not auth_included,
    'counts': {'files': len(files), 'total_bytes': total_bytes},
    'top_level_dirs': sorted({f['path'].split('/', 1)[0] for f in files}),
    'files': files,
    'notes': 'Generated by workspace/dev-knowledge/skills/agent_export.sh (v2.1). See REPLICATION_GUIDE.md.',
}
print(json.dumps(manifest, indent=2))
PY

# ---- Write BOOTSTRAP.md (clone-side runbook, full content, no truncation) --
# This file is what the recipient (clone) agent reads end-to-end. It contains
# the no-truncation contract, the import procedure, the identity interview,
# the apply phase, and the report-back checklist. The user-facing prompt to
# the clone collapses to: "unzip the bundle, read BOOTSTRAP.md, follow it".
cat > "${STAGE_DIR}/BOOTSTRAP.md" <<'BOOTSTRAP_EOF'
# 🧬 BOOTSTRAP — Clone Agent Runbook (read this end-to-end before acting)

You are a fresh clone being bootstrapped from this bundle. You will:
  1. Honor the no-truncation contract (Phase 0).
  2. Import the bundle into your workspace (Phase A).
  3. Interview the user for your identity & settings (Phase B).
  4. Apply the answers (Phase C).
  5. Report back and STOP (Phase D).

═══════════════════════════════════════════════════════════════
PHASE 0 — NO-TRUNCATION CONTRACT (BINDING)
═══════════════════════════════════════════════════════════════

You MUST operate on FULL file contents at every step. Truncated previews are
forbidden as a basis for ANY decision.

A. If ANY tool result contains "[TRUNCATED OUTPUT]" with a context_id, you
   MUST immediately call xpworkspace-context-retrieve with that context_id
   to get the full plaintext. Do NOT proceed on the preview.

B. When reading files with xpworkspace-file-read:
   - First, run xpworkspace-bash `wc -l <path>` to get the line count.
   - File ≤ 400 lines: read the whole thing in one call.
   - File > 400 lines: read in explicit start_line/end_line ranges of ≤ 400
     lines each, sequentially. Verify coverage: sum of (end-start+1) across
     reads MUST equal `wc -l`.
   - NEVER skip the middle of a file. NEVER summarize before reading fully.

C. When inspecting via xpworkspace-bash with `cat`/`head`/`tail`:
   - Do NOT use bare `cat <bigfile>` for files > 200 lines (silent truncation).
   - For big files use `wc -l`, `grep -n`, `sed -n 'A,Bp'`, or use
     xpworkspace-file-read with line ranges.

D. The import script uses `shutil.copy2` and `executescript` — it copies and
   replays files byte-exact. Trust the script. Truncation risk is ONLY on
   YOUR read path.

E. Before declaring any phase "done", verify the relevant inputs were read
   in full (line counts match, no unresolved [TRUNCATED OUTPUT] markers).

If you violate this contract: STOP and re-read with full-content rules.

═══════════════════════════════════════════════════════════════
PHASE A — IMPORT THE BUNDLE
═══════════════════════════════════════════════════════════════

1. Read workspace/dev-knowledge/skills/agent_import.md IN FULL (wc -l first; range-read if
   > 400 lines).

2. Dry-run (the bundle URL is the one the user gave you):
     bash workspace/dev-knowledge/skills/agent_import.sh --dry-run <BUNDLE_URL>
   Read every field of the JSON response. Confirm: sha256_ok=true,
   auth_will_auto_apply=true, no [TRUNCATED OUTPUT] markers.

3. Apply with merge mode:
     bash workspace/dev-knowledge/skills/agent_import.sh --mode=merge <BUNDLE_URL>
   Confirm in the JSON: applied=true, auth_apply.applied=true,
   db_apply.errors=[].

4. Verify auth was auto-applied:
     gh auth status
     git config --global user.name
     git config --global user.email
   Expected gh user: xpander-fullstack-generalist (you will rename in B/C).

5. Confirm task_queue restored (use the local-db tool):
     SELECT count(*) FROM task_queue;
     SELECT id, title, status FROM task_queue ORDER BY started_at DESC;

6. Read these files IN FULL (wc -l first; range-read if needed):
     workspace/dev-knowledge/skills/MUST_READ.md
     workspace/dev-knowledge/skills/known_repos.md
     workspace/dev-knowledge/skills/task_queue.md
     workspace/dev-knowledge/skills/planning_workflow.md
   Skipping or skimming MUST_READ.md = protocol violation.

═══════════════════════════════════════════════════════════════
PHASE B — INTERVIEW THE USER (one question per xpask_for_information call,
                              wait for the answer before sending the next)
═══════════════════════════════════════════════════════════════

You are inheriting from source agent "Gilfoyle" but YOU are a separate
identity. Ask these in order, ONE AT A TIME via xpask_for_information:

  1. "What name should I go by? (source is 'Gilfoyle' — pick something
      distinct, e.g. 'Dinesh', 'Bertram', 'Jared', or your own.)"

  2. "What's my primary scope?
        a) Same as source — full xpander.ai dev (skills + repos + PRs)
        b) Read-only / advisory (no pushes, no PRs)
        c) Narrow scope — specify which repos or skill areas
      Which one, and any details?"

  3. "Tone & personality preference?
        a) Match source — concise, dry, Gilfoyle-style snark allowed
        b) Strictly professional, no snark
        c) Custom — describe it"

  4. "Default git/PR identity — should I commit as
     'xpander-fullstack-generalist' (inherited from auth/) or do you want
     a different bot identity? If different, give me name + email + how to
     obtain the token."

  5. "Any repos from known_repos.md I should NOT touch, or any new repos
      to add?"

  6. "task_queue: keep inherited rows (active + history) or wipe
      completed/cancelled history and start fresh?"

  7. "Notion access — same scope as source, or restricted? If restricted,
      list the page/database IDs I'm allowed to touch."

  8. "Anything else I should know, do, or avoid? (specific tickets to
      start with, PR review backlog, current incident, etc.)"

═══════════════════════════════════════════════════════════════
PHASE C — APPLY THE INTERVIEW ANSWERS
═══════════════════════════════════════════════════════════════

After ALL 8 answers are collected, write FULL CONTENT (no truncation,
no ellipses, no "...") to the following:

1. workspace/dev-knowledge/memory/clone_identity.md — full content with:
     - my name
     - scope
     - tone
     - git identity decision
     - repo allow/deny list
     - task_queue policy
     - notion scope
     - free-form notes from Q8
   Use xpworkspace-file-write mode='w'. If content > 3,500 chars, follow the
   chunked-writes protocol (mode='w' for chunk 1, mode='a' for the rest).
   Verify final file via wc -l.

2. If Q4 chose a different git identity:
     - Backup current ~/.gitconfig to workspace/tmp/gitconfig.bak.<ts>
     - Update ~/.gitconfig with the new name/email
     - If a new gh PAT is needed, ASK FOR IT via xpask_for_information
       (sensitive=true, do NOT log/echo) BEFORE writing it.

3. If Q6 = wipe history:
     DELETE FROM task_queue WHERE status IN ('completed','cancelled');

4. If Q5 changed the repo list:
     - Read workspace/dev-knowledge/skills/known_repos.md IN FULL (line-range if big)
     - Annotate (not delete) — append "EXCLUDED for <clone-name>" or
       "ADDED for <clone-name>" lines so source agent's view stays intact
     - Write back via xpworkspace-file-write or xpworkspace-file-edit.

5. Append one line to workspace/dev-knowledge/memory/decisions.md:
     YYYY-MM-DD — Bootstrapped as <name>; scope=<scope>; tone=<tone>.
   Use xpworkspace-file-write mode='a'.

6. List for the user the steps that REQUIRE the xpander.ai UI (you cannot
   do these yourself):
     - Update agent display name to <name>
     - Update agent instructions/goals if scope or tone changed
     - Confirm Notion MCP scope matches Q7

═══════════════════════════════════════════════════════════════
PHASE D — REPORT BACK, THEN STOP
═══════════════════════════════════════════════════════════════

Final message must include (verified, not assumed):
  ✅ Bundle imported — file counts (added/conflicts/identical) from script JSON
  ✅ sha256_ok: true (cite from script output)
  ✅ Auth verified — paste gh auth status + git config name/email
  ✅ task_queue row count (cite SQL output)
  ✅ MUST_READ.md fully read (cite wc -l = total lines read)
  ✅ My new name + scope + tone (1-line summary)
  ✅ workspace/dev-knowledge/memory/clone_identity.md written — cite wc -l
  ⏳ Manual xpander.ai UI steps remaining

Then STOP. Do NOT pick up tickets or repo work until the user gives the
green light.
BOOTSTRAP_EOF

# ---- Write REPLICATION_GUIDE.md --------------------------------------------
cat > "${STAGE_DIR}/REPLICATION_GUIDE.md" <<'EOF'
# 🧬 Replication Guide — Importing This Agent Bundle

This bundle contains the persistent brain of an xpander.ai agent: its skills,
memory, and context.

## 1. Inspect the Bundle

```
.
├── manifest.json          # checksums, file inventory, agent metadata
├── scrub_report.json      # per-file token redactions applied during export
├── REPLICATION_GUIDE.md   # this file
├── skills/                # reusable capabilities (read MUST_READ.md first)
├── memory/                # persistent decisions, lessons learned (no secrets/)
└── context/               # docs, specs, plans (context/plans/*.md)
```

Verify integrity:

```bash
python3 -c "
import hashlib, json
m=json.load(open('manifest.json'))
bad=[f['path'] for f in m['files']
     if hashlib.sha256(open(f['path'],'rb').read()).hexdigest()!=f['sha256']]
print('OK' if not bad else 'CORRUPT: '+','.join(bad))
"
```

## 2. What's NOT in This Bundle (and what you must supply)

- **Secrets:** anything under `workspace/dev-knowledge/memory/secrets/**` is excluded.
- **Credentials on disk:** `.env*`, `*.pem`, `*.key`, `id_rsa*`, `.netrc`,
  `.git-credentials`, `*.bak.*` are excluded.
- **GitHub tokens:** the source agent's `~/.config/gh/hosts.yml`,
  `~/.gitconfig`, `~/.git-credentials`, `~/.netrc` are NOT in this bundle.
  The recipient agent must run onboarding (Phase 3) to provide its own.
- **Cloned repos:** any working trees under `/agent/data/dev` are excluded —
  re-clone them via the URLs listed in `skills/known_repos.md`.
- **Agent profile:** xpander.ai instructions / goals / connected tools are not
  workspace files — copy from the source agent's profile UI.

The `scrub_report.json` shows what (if anything) was pattern-redacted in text
files. If the report has 0 redactions, the source workspace was already clean.

## 3. Use the Companion Import Skill

The recommended flow is the three-phase import:

```bash
# Phase 1 — dry-run (no changes)
bash workspace/dev-knowledge/skills/agent_import.sh --dry-run <bundle-url>

# Phase 2 — apply with chosen mode
bash workspace/dev-knowledge/skills/agent_import.sh --mode=merge <bundle-url>

# Phase 3 — onboard (writes gh + git identity for THIS agent)
#  Either user types 'onboard' to trigger, or the LLM auto-detects
#  onboarding_required.json under workspace/tmp/import_<ts>/.
bash workspace/dev-knowledge/skills/agent_import.sh --onboard --inputs=<inputs.json>
```

See `workspace/dev-knowledge/skills/agent_import.md` and `agent_onboarding.md` (post-import).

## 4. Manual Fallback

```bash
unzip /path/to/agent_bundle_<ts>.zip -d /tmp/import
cp -a /tmp/import/agent_bundle_*/skills  workspace/
cp -a /tmp/import/agent_bundle_*/memory  workspace/
cp -a /tmp/import/agent_bundle_*/context workspace/
```

> ⚠️ Manual mode skips the integrity check, conflict planning, and onboarding.
> Use the import skill unless you have a reason not to.

## 5. Bootstrap the New Agent

After file merge AND onboarding:

1. Read `workspace/dev-knowledge/skills/MUST_READ.md`
2. Read `workspace/dev-knowledge/skills/known_repos.md`
3. `ls workspace/dev-knowledge/skills/` and read any task-relevant skill
4. Read `workspace/dev-knowledge/memory/lessons/lessons_learned.md`
5. Read `workspace/dev-knowledge/memory/agent_identity.md` (created by onboarding)
6. Read `workspace/dev-knowledge/memory/workspace_setup.md`

## 6. Smoke Test

Ask the new agent: *"Read MUST_READ.md and summarize your conventions."* It
should reference branch rules, ticket numbers, PR conventions, and the
planning skill.
EOF

# ---- Create the zip --------------------------------------------------------
( cd "$OUT_DIR" && zip -qr "${STAGE_NAME}.zip" "$STAGE_NAME" )

# ---- Cleanup staging dir ---------------------------------------------------
rm -rf "$STAGE_DIR"

# ---- Output ----------------------------------------------------------------
ZIP_SIZE="$(du -h "$ZIP_PATH" | cut -f1)"
ZIP_SHA="$(sha256sum "$ZIP_PATH" | cut -d' ' -f1)"
echo
echo "✅ Bundle ready (v2.1)"
echo "   zip          : $ZIP_PATH  ($ZIP_SIZE)"
echo "   sha256(zip)  : $ZIP_SHA"
if [[ "$AUTH_INCLUDED" == "1" ]]; then
  echo "   auth_included: YES (gh user: ${GH_USER_IN_BUNDLE:-xpander-fullstack-generalist})"
  echo "   onboarding   : NOT required — import auto-applies auth/ on Phase 2"
else
  echo "   auth_included: no"
  echo "   onboarding   : required — recipient must run Phase 3"
fi
if [[ "$SCRUB_HITS" -gt 0 ]]; then
  echo "   ⚠️  scrub    : $SCRUB_HITS redaction(s) applied (skills/memory/context only)"
else
  echo "   scrub        : clean (0 redactions)"
fi
echo
echo "Next steps:"
echo "  1. xpworkspace-file-share path=$ZIP_PATH"
echo "  2. Send the URL to the recipient agent."
echo "  3. They run: bash workspace/dev-knowledge/skills/agent_import.sh --dry-run <url>"
echo "     then     : bash workspace/dev-knowledge/skills/agent_import.sh --mode=merge <url>"
echo
if [[ "$AUTH_INCLUDED" == "1" ]]; then
  echo "  ⚠️  This bundle contains a live GitHub PAT under auth/. Treat as secret."
  echo "      For external sharing, re-run with EXPORT_STRICT=1 (also forces NO_AUTH=1)."
fi
if [[ "$STRICT" != "1" && "$SCRUB_HITS" -gt 0 ]]; then
  echo "  ℹ️  For external sharing, re-run with EXPORT_STRICT=1 to fail-fast on tokens."
fi
