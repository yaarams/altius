#!/usr/bin/env bash
# agent_import.sh — Download, verify, and merge an agent bundle.
#
# v2.1 changes (matches export v2.1):
#   - When the bundle's manifest reports `auth_included: true`, Phase 2
#     automatically applies `auth/` into the agent's HOME (gh hosts.yml,
#     .gitconfig, .git-credentials, .netrc) with proper perms and patches
#     workspace_setup.md + writes agent_identity.md — no Phase 3 required.
#   - Existing credential files in HOME are backed up to
#     <target-root>/tmp/import_<ts>_home_backup/ before being overwritten.
#   - Set IMPORT_NO_AUTO_AUTH=1 (env) or pass --no-auto-auth to skip the
#     auto-apply and fall back to the v2.0 onboarding flow even when the
#     bundle includes auth/.
#
# See workspace/dev-knowledge/skills/agent_import.md for the full skill spec.

set -euo pipefail

# ---- Defaults --------------------------------------------------------------
MODE=""
DRY_RUN=0
KEEP_STAGING=0
TARGET_ROOT="workspace"
URL=""
ONBOARD=0
INPUTS=""
HOME_DIR="${AGENT_HOME:-/agent/data/.home}"
FORCE=0
NO_AUTO_AUTH="${IMPORT_NO_AUTO_AUTH:-0}"

usage() {
  cat <<USAGE >&2
Usage:
  Phase 1/2 (file merge):
    agent_import.sh [--dry-run|--mode=MODE] [--keep-staging] [--target-root DIR]
                    [--no-auto-auth] [--home DIR] <URL>
    Modes: merge | overwrite-conflicts | overwrite-all | skip

    For v2.1+ bundles with auth_included=true, Phase 2 also auto-applies
    auth/ into HOME (gh hosts.yml, .gitconfig, .git-credentials, .netrc) and
    patches workspace_setup.md + agent_identity.md — no Phase 3 needed.
    Pass --no-auto-auth (or set IMPORT_NO_AUTO_AUTH=1) to suppress that and
    fall back to onboarding.

  Phase 3 (onboarding — credentials & identity):
    agent_import.sh --onboard --inputs=<path-to-onboarding_inputs.json> \\
                    [--home DIR] [--target-root DIR] [--force]
    Writes gh hosts.yml, .gitconfig, .git-credentials, .netrc into <home>
    (default: /agent/data/.home), patches workspace/dev-knowledge/memory/workspace_setup.md
    Git Identity block, and creates workspace/dev-knowledge/memory/agent_identity.md.
    Existing credential files are backed up to
    <target-root>/tmp/import_<ts>_home_backup/ before overwrite. Refuses to
    overwrite already-onboarded files unless --force is set.
USAGE
  exit 1
}

# ---- Parse args ------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --mode=*) MODE="${1#--mode=}"; shift ;;
    --mode) MODE="$2"; shift 2 ;;
    --keep-staging) KEEP_STAGING=1; shift ;;
    --target-root) TARGET_ROOT="$2"; shift 2 ;;
    --target-root=*) TARGET_ROOT="${1#--target-root=}"; shift ;;
    --onboard) ONBOARD=1; shift ;;
    --inputs=*) INPUTS="${1#--inputs=}"; shift ;;
    --inputs) INPUTS="$2"; shift 2 ;;
    --home) HOME_DIR="$2"; shift 2 ;;
    --home=*) HOME_DIR="${1#--home=}"; shift ;;
    --force) FORCE=1; shift ;;
    --no-auto-auth) NO_AUTO_AUTH=1; shift ;;
    -h|--help) usage ;;
    --) shift; URL="${1:-}"; shift || true ;;
    -*) echo "unknown flag: $1" >&2; usage ;;
    *) URL="$1"; shift ;;
  esac
done

# ---- Branch: --onboard takes a different path (no URL/download required) ---
if [[ $ONBOARD -eq 1 ]]; then
  if [[ -z "$INPUTS" ]]; then
    echo "error: --onboard requires --inputs=<path-to-onboarding_inputs.json>" >&2
    exit 1
  fi
  if [[ ! -f "$INPUTS" ]]; then
    echo "error: inputs file not found: $INPUTS" >&2
    exit 1
  fi
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  HOME_BACKUP="${TARGET_ROOT}/tmp/import_${TS}_home_backup"
  mkdir -p "$HOME_BACKUP"
  python3 - "$INPUTS" "$HOME_DIR" "$TARGET_ROOT" "$HOME_BACKUP" "$FORCE" <<'PY'
import json, os, re, shutil, stat, subprocess, sys
inputs_path, home_dir, target_root, backup_dir, force = sys.argv[1:6]
force = int(force)

with open(inputs_path) as fh:
    answers = json.load(fh)

required = ['agent_name', 'git_user_name', 'git_user_email', 'gh_user', 'gh_token']
missing = [k for k in required if not answers.get(k)]
if missing:
    print(json.dumps({'error': 'missing_required_fields', 'missing': missing}, indent=2))
    sys.exit(1)

agent_name      = answers['agent_name']
git_user_name   = answers['git_user_name']
git_user_email  = answers['git_user_email']
gh_user         = answers['gh_user']
gh_token        = answers['gh_token']
xpander_email   = answers.get('xpander_email', '')
notion_ws       = answers.get('notion_workspace', '')

# ---- Targets --------------------------------------------------------------
gh_hosts        = os.path.join(home_dir, '.config', 'gh', 'hosts.yml')
gitconfig       = os.path.join(home_dir, '.gitconfig')
git_credentials = os.path.join(home_dir, '.git-credentials')
netrc           = os.path.join(home_dir, '.netrc')
setup_md        = os.path.join(target_root, 'memory', 'workspace_setup.md')
identity_md     = os.path.join(target_root, 'memory', 'agent_identity.md')

# ---- Refuse rerun without --force -----------------------------------------
existing = [p for p in (gh_hosts, gitconfig, git_credentials, netrc) if os.path.isfile(p)]
if existing and not force:
    print(json.dumps({
        'error': 'already_onboarded',
        'existing_files': existing,
        'hint': 'rerun with --force to overwrite (existing files will be backed up first)',
    }, indent=2))
    sys.exit(2)

# ---- Backup existing -------------------------------------------------------
def backup(src):
    if not os.path.isfile(src):
        return None
    rel = os.path.relpath(src, '/')
    dst = os.path.join(backup_dir, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    os.chmod(dst, 0o600)
    return dst

backups = {p: backup(p) for p in (gh_hosts, gitconfig, git_credentials, netrc, setup_md)}

# ---- Write credential files -----------------------------------------------
def write_secure(path, content, mode):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write(content)
    os.chmod(path, mode)

# gh hosts.yml — match the format `gh auth login` produces
hosts_yml = (
    'github.com:\n'
    f'    user: {gh_user}\n'
    f'    oauth_token: {gh_token}\n'
    '    git_protocol: https\n'
)
write_secure(gh_hosts, hosts_yml, 0o600)

# .gitconfig — minimal global config
gitcfg = (
    '[user]\n'
    f'\tname = {git_user_name}\n'
    f'\temail = {git_user_email}\n'
    '[init]\n'
    '\tdefaultBranch = main\n'
    '[pull]\n'
    '\trebase = false\n'
)
write_secure(gitconfig, gitcfg, 0o644)

# .git-credentials — for `git push https://github.com/...`
gitcreds = f'https://{gh_user}:{gh_token}@github.com\n'
write_secure(git_credentials, gitcreds, 0o600)

# .netrc — for tools that read it (curl, etc.)
netrc_body = (
    'machine github.com\n'
    f'  login {gh_user}\n'
    f'  password {gh_token}\n'
)
write_secure(netrc, netrc_body, 0o600)

# ---- Patch workspace_setup.md Git Identity block --------------------------
identity_block = (
    f'## Git Identity\n\n'
    f'- `user.name` = `{git_user_name}`\n'
    f'- `user.email` = `{git_user_email}`\n'
    f'- GitHub bot user = `{gh_user}`\n'
    f'- Token storage: `~/.config/gh/hosts.yml` (0600), mirrored to `~/.git-credentials` and `~/.netrc`\n'
    f'- Onboarded by `agent_import.sh --onboard` for agent `{agent_name}`\n'
)
setup_patched = False
if os.path.isfile(setup_md):
    with open(setup_md) as fh:
        body = fh.read()
    pat = re.compile(r'## Git Identity\n.*?(?=\n## |\Z)', re.DOTALL)
    if pat.search(body):
        body = pat.sub(identity_block.rstrip() + '\n', body)
    else:
        body = body.rstrip() + '\n\n' + identity_block
    with open(setup_md, 'w') as fh:
        fh.write(body)
    setup_patched = True

# ---- Write agent_identity.md ----------------------------------------------
identity_doc = (
    f'# Agent Identity\n\n'
    f'- **Agent name:** `{agent_name}`\n'
    f'- **Git author:** `{git_user_name} <{git_user_email}>`\n'
    f'- **GitHub user:** `{gh_user}`\n'
    f'- **Primary xpander.ai user email:** `{xpander_email or "(unset)"}`\n'
    f'- **Notion workspace:** `{notion_ws or "(skipped)"}`\n\n'
    'Token credentials are stored in `~/.config/gh/hosts.yml` (0600). Never commit them.\n'
)
os.makedirs(os.path.dirname(identity_md), exist_ok=True)
with open(identity_md, 'w') as fh:
    fh.write(identity_doc)

# ---- Smoke tests (best-effort, never fail) --------------------------------
def run_smoke(cmd, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=15)
        return {'cmd': ' '.join(cmd), 'rc': out.returncode,
                'stdout': out.stdout.strip()[:500], 'stderr': out.stderr.strip()[:500]}
    except Exception as e:
        return {'cmd': ' '.join(cmd), 'error': str(e)}

smoke = {
    'gh_auth_status': run_smoke(['gh', 'auth', 'status'], {'GH_CONFIG_DIR': os.path.join(home_dir, '.config', 'gh')}),
    'git_config_list': run_smoke(['git', 'config', '--global', '--list'], {'HOME': home_dir}),
}

# ---- Redacted summary -----------------------------------------------------
summary = {
    'onboarded': True,
    'agent_name': agent_name,
    'home': home_dir,
    'wrote': {
        'gh_hosts': gh_hosts,
        'gitconfig': gitconfig,
        'git_credentials': git_credentials,
        'netrc': netrc,
        'agent_identity_md': identity_md,
        'workspace_setup_md_patched': setup_patched,
    },
    'backups': {k: v for k, v in backups.items() if v},
    'gh_token': '<REDACTED>',
    'smoke': smoke,
    'next': [
        f'cat {identity_md}',
        'gh auth status   # confirm token works',
        'git config --global --list   # confirm identity',
        'cat workspace/dev-knowledge/skills/MUST_READ.md',
    ],
}
print(json.dumps(summary, indent=2))
PY
  exit $?
fi

[[ -z "$URL" ]] && usage

if [[ $DRY_RUN -eq 0 && -z "$MODE" ]]; then
  echo "error: must pass --dry-run or --mode=<merge|overwrite-conflicts|overwrite-all|skip>" >&2
  exit 3
fi

if [[ -n "$MODE" ]]; then
  case "$MODE" in
    merge|overwrite-conflicts|overwrite-all|skip) ;;
    *) echo "error: invalid --mode '$MODE'" >&2; exit 1 ;;
  esac
fi

# ---- Stage -----------------------------------------------------------------
TS="$(date -u +%Y%m%dT%H%M%SZ)"
STAGING="${TARGET_ROOT}/tmp/import_${TS}"
BACKUP="${STAGING}/.backup"
mkdir -p "$STAGING"

cleanup() {
  if [[ $KEEP_STAGING -eq 1 ]]; then
    return
  fi
  # Preserve .backup outside the staging dir before removing
  if [[ $DRY_RUN -eq 0 && -d "$BACKUP" ]]; then
    if find "$BACKUP" -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
      mv "$BACKUP" "${TARGET_ROOT}/tmp/import_${TS}_backup" 2>/dev/null || true
    fi
  fi
  rm -rf "$STAGING"
}
trap cleanup EXIT

DOWNLOAD="${STAGING}/payload.bin"
echo "→ downloading: $URL" >&2
curl -fsSL -o "$DOWNLOAD" "$URL" || { echo "download failed" >&2; exit 1; }

# ---- Detect payload type ---------------------------------------------------
MAGIC="$(head -c 4 "$DOWNLOAD" | od -An -c | tr -d ' \n' || true)"
ZIP="${STAGING}/bundle.zip"

if [[ "$MAGIC" == "PK"* ]]; then
  cp "$DOWNLOAD" "$ZIP"
  echo "→ detected: raw zip" >&2
else
  # Treat as base64 — strip whitespace, decode, retry
  TMPB64="${STAGING}/payload.b64"
  tr -d ' \r\n\t' < "$DOWNLOAD" > "$TMPB64"
  if base64 -d "$TMPB64" > "$ZIP" 2>/dev/null; then
    BMAGIC="$(head -c 4 "$ZIP" | od -An -c | tr -d ' \n')"
    if [[ "$BMAGIC" != "PK"* ]]; then
      echo "error: decoded payload is not a zip (magic=$BMAGIC)" >&2
      exit 1
    fi
    echo "→ detected: base64-encoded zip (decoded)" >&2
  else
    echo "error: payload is neither a zip nor valid base64" >&2
    exit 1
  fi
fi

# ---- Extract & locate bundle root ------------------------------------------
EXTRACT="${STAGING}/extracted"
mkdir -p "$EXTRACT"
unzip -q "$ZIP" -d "$EXTRACT"
BUNDLE_ROOT="$(find "$EXTRACT" -maxdepth 2 -type f -name manifest.json -printf '%h\n' | head -1)"
if [[ -z "$BUNDLE_ROOT" ]]; then
  echo "error: manifest.json not found inside bundle" >&2
  exit 2
fi
echo "→ bundle root: $BUNDLE_ROOT" >&2

# ---- Run the planner / applier in Python -----------------------------------
python3 - "$BUNDLE_ROOT" "$TARGET_ROOT" "$DRY_RUN" "$MODE" "$BACKUP" "$HOME_DIR" "$NO_AUTO_AUTH" <<'PY'
import hashlib, json, os, shutil, sys
bundle, target, dry_run, mode, backup = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
home_dir = sys.argv[6]
no_auto_auth = sys.argv[7] == '1'

manifest_path = os.path.join(bundle, 'manifest.json')
with open(manifest_path) as fh:
    manifest = json.load(fh)

# 1. Verify integrity
bad = []
for f in manifest['files']:
    p = os.path.join(bundle, f['path'])
    if not os.path.isfile(p):
        bad.append(('missing', f['path']))
        continue
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    if h != f['sha256']:
        bad.append(('sha256', f['path']))
if bad:
    print(json.dumps({'error': 'integrity_failed', 'issues': bad}, indent=2))
    sys.exit(2)

# 2. Build merge plan for the three persistent dirs
MANAGED = ('skills', 'memory', 'context')
plan = {d: {'new': [], 'identical': [], 'conflicts': []} for d in MANAGED}

for f in manifest['files']:
    rel = f['path']
    top = rel.split('/', 1)[0]
    if top not in MANAGED:
        continue
    src = os.path.join(bundle, rel)
    dst = os.path.join(target, rel)
    if not os.path.exists(dst):
        plan[top]['new'].append(rel)
    else:
        local_hash = hashlib.sha256(open(dst, 'rb').read()).hexdigest()
        if local_hash == f['sha256']:
            plan[top]['identical'].append(rel)
        else:
            plan[top]['conflicts'].append(rel)

auth_included = bool(manifest.get('auth_included'))
auth_dir = os.path.join(bundle, 'auth')
auth_files_present = os.path.isdir(auth_dir) and any(
    os.path.isfile(os.path.join(auth_dir, p))
    for p in ('.config/gh/hosts.yml', '.gitconfig', '.git-credentials', '.netrc')
)

summary = {
    'bundle': os.path.basename(bundle),
    'bundle_version': manifest.get('bundle_version'),
    'bundle_created_utc': manifest.get('created_utc'),
    'sha256_ok': True,
    'auth_included': auth_included,
    'auth_files_present': auth_files_present,
    'auth_will_auto_apply': auth_included and auth_files_present and not no_auto_auth,
    'plan': {d: {
        'new': len(plan[d]['new']),
        'identical': len(plan[d]['identical']),
        'conflicts': len(plan[d]['conflicts']),
        'conflict_paths': plan[d]['conflicts'],
        'new_paths': plan[d]['new'],
    } for d in MANAGED},
}

if dry_run:
    print(json.dumps(summary, indent=2))
    sys.exit(0)

# 3. Apply
if mode == 'skip':
    summary['applied'] = False
    summary['reason'] = 'mode=skip'
    print(json.dumps(summary, indent=2))
    sys.exit(0)

os.makedirs(backup, exist_ok=True)
actions = {'added': [], 'overwritten': [], 'kept_local': [], 'unchanged': []}

def add_file(rel):
    src = os.path.join(bundle, rel)
    dst = os.path.join(target, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)

def overwrite_file(rel):
    src = os.path.join(bundle, rel)
    dst = os.path.join(target, rel)
    bk  = os.path.join(backup, rel)
    os.makedirs(os.path.dirname(bk), exist_ok=True)
    shutil.copy2(dst, bk)
    shutil.copy2(src, dst)

for d in MANAGED:
    for rel in plan[d]['new']:
        add_file(rel); actions['added'].append(rel)
    for rel in plan[d]['identical']:
        actions['unchanged'].append(rel)
    for rel in plan[d]['conflicts']:
        if mode == 'merge':
            actions['kept_local'].append(rel)
        elif mode in ('overwrite-conflicts', 'overwrite-all'):
            overwrite_file(rel); actions['overwritten'].append(rel)
    if mode == 'overwrite-all':
        for rel in plan[d]['identical']:
            # already same content — no need to touch but be explicit
            pass

summary['applied'] = True
summary['mode'] = mode
summary['actions'] = {k: len(v) for k, v in actions.items()}
summary['action_details'] = actions
summary['backup_dir'] = backup if any(actions['overwritten']) else None

# 3b. Apply DB dumps from memory/db/*.sql into the local SQLite DB.
#     The dumps are produced by agent_export.sh and are written to be
#     idempotent (CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE on PK),
#     so re-running this step is safe. Only runs when files actually
#     landed under <target>/memory/db/.
import sqlite3 as _sq, glob as _glob
db_dir = os.path.join(target, 'memory', 'db')
db_apply = {'files': [], 'tables_touched': [], 'errors': []}
if os.path.isdir(db_dir):
    local_db = os.environ.get('LOCAL_DB', '/agent/data/data/local_db.db')
    os.makedirs(os.path.dirname(local_db), exist_ok=True)
    try:
        conn = _sq.connect(local_db)
        for sql_path in sorted(_glob.glob(os.path.join(db_dir, '*.sql'))):
            try:
                with open(sql_path) as fh:
                    conn.executescript(fh.read())
                conn.commit()
                db_apply['files'].append(os.path.relpath(sql_path, target))
                db_apply['tables_touched'].append(os.path.basename(sql_path).removesuffix('.sql'))
            except Exception as e:
                db_apply['errors'].append({'file': sql_path, 'error': str(e)})
        conn.close()
    except Exception as e:
        db_apply['errors'].append({'file': '<connect>', 'error': str(e)})
summary['db_apply'] = db_apply

# 3c. Auto-apply bundled auth (gh + git identity) when present.
# Triggered when manifest.auth_included is true, the auth/ files actually
# exist on disk, and the operator did not pass --no-auto-auth. Mirrors what
# Phase 3 onboarding would do: writes hosts.yml, .gitconfig, .git-credentials,
# .netrc into HOME with proper perms, patches workspace_setup.md Git Identity
# block, and creates agent_identity.md. Existing files are backed up first.
auth_apply = {'attempted': False, 'applied': False, 'reason': None,
              'wrote': {}, 'backups': {}, 'gh_user': None}
if auth_included and auth_files_present and not no_auto_auth:
    import re as _re
    auth_apply['attempted'] = True
    ts_label = os.path.basename(os.path.dirname(backup.rstrip(os.sep))).removeprefix('import_')
    home_backup = os.path.join(target, 'tmp', f'import_{ts_label}_home_backup')
    os.makedirs(home_backup, exist_ok=True)

    targets = {
        '.config/gh/hosts.yml': (os.path.join(home_dir, '.config', 'gh', 'hosts.yml'), 0o600),
        '.gitconfig':           (os.path.join(home_dir, '.gitconfig'),                  0o644),
        '.git-credentials':     (os.path.join(home_dir, '.git-credentials'),            0o600),
        '.netrc':               (os.path.join(home_dir, '.netrc'),                      0o600),
    }

    def _backup(path):
        if not os.path.isfile(path):
            return None
        rel = os.path.relpath(path, '/')
        bk  = os.path.join(home_backup, rel)
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        shutil.copy2(path, bk)
        try: os.chmod(bk, 0o600)
        except OSError: pass
        return bk

    for rel, (dst, mode_bits) in targets.items():
        src = os.path.join(auth_dir, rel)
        if not os.path.isfile(src):
            continue
        bk = _backup(dst)
        if bk:
            auth_apply['backups'][rel] = bk
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        try: os.chmod(dst, mode_bits)
        except OSError: pass
        auth_apply['wrote'][rel] = dst

    # Read identity values back out for downstream patches.
    gh_user = (manifest.get('agent') or {}).get('gh_user') or 'xpander-fullstack-generalist'
    git_user_name = git_user_email = ''
    gc_path = targets['.gitconfig'][0]
    if os.path.isfile(gc_path):
        with open(gc_path) as fh:
            gc_text = fh.read()
        m = _re.search(r'(?m)^\s*name\s*=\s*(.+)$',  gc_text); git_user_name  = m.group(1).strip() if m else ''
        m = _re.search(r'(?m)^\s*email\s*=\s*(.+)$', gc_text); git_user_email = m.group(1).strip() if m else ''
    auth_apply['gh_user'] = gh_user

    # Patch workspace/dev-knowledge/memory/workspace_setup.md Git Identity block.
    setup_md = os.path.join(target, 'memory', 'workspace_setup.md')
    identity_block = (
        '## Git Identity\n\n'
        f'- `user.name` = `{git_user_name}`\n'
        f'- `user.email` = `{git_user_email}`\n'
        f'- GitHub bot user = `{gh_user}`\n'
        '- Token storage: `~/.config/gh/hosts.yml` (0600), mirrored to `~/.git-credentials` and `~/.netrc`\n'
        '- Onboarded automatically by `agent_import.sh` from a v2.1 bundle (auth_included)\n'
    )
    setup_patched = False
    if os.path.isfile(setup_md):
        bk = _backup(setup_md)
        if bk: auth_apply['backups']['memory/workspace_setup.md'] = bk
        with open(setup_md) as fh:
            body = fh.read()
        pat = _re.compile(r'## Git Identity\n.*?(?=\n## |\Z)', _re.DOTALL)
        body = pat.sub(identity_block.rstrip() + '\n', body) if pat.search(body) else (body.rstrip() + '\n\n' + identity_block)
        with open(setup_md, 'w') as fh:
            fh.write(body)
        setup_patched = True
    auth_apply['workspace_setup_md_patched'] = setup_patched

    # Write agent_identity.md (always replace).
    identity_md = os.path.join(target, 'memory', 'agent_identity.md')
    os.makedirs(os.path.dirname(identity_md), exist_ok=True)
    with open(identity_md, 'w') as fh:
        fh.write(
            '# Agent Identity\n\n'
            f'- **Agent name:** `{gh_user}`\n'
            f'- **Git author:** `{git_user_name} <{git_user_email}>`\n'
            f'- **GitHub user:** `{gh_user}`\n'
            f'- **Source bundle:** `{os.path.basename(bundle)}` (v{manifest.get("bundle_version")})\n\n'
            'Token credentials are stored in `~/.config/gh/hosts.yml` (0600). Never commit them.\n'
        )
    auth_apply['wrote']['memory/agent_identity.md'] = identity_md
    auth_apply['applied'] = True
    auth_apply['home_backup_dir'] = home_backup
elif auth_included and not auth_files_present:
    auth_apply['reason'] = 'manifest.auth_included=true but auth/ files missing on disk'
elif auth_included and no_auto_auth:
    auth_apply['reason'] = 'auth_included present but suppressed by --no-auto-auth'
else:
    auth_apply['reason'] = 'no auth in bundle'
summary['auth_apply'] = auth_apply


# 4. Emit onboarding_required.json if the bundle requested it AND we did
#    not just auto-apply auth ourselves (in which case Phase 3 is moot).
#    We write it OUTSIDE the staging dir so it survives cleanup, into
#    <target>/tmp/import_<ts>_onboarding_required.json. The LLM detects this
#    file post-import and drives Phase 3 via xpask_for_information.
if manifest.get('onboarding_required') and not auth_apply.get('applied'):
    questions = [
        {'id': 'agent_name',       'prompt': "Display name for this agent (e.g. 'xpander-fullstack-generalist')"},
        {'id': 'git_user_name',    'prompt': "Git user.name for commits (e.g. 'moriel-dev-agent')"},
        {'id': 'git_user_email',   'prompt': 'Git user.email for commits'},
        {'id': 'gh_user',          'prompt': 'GitHub username for the bot account'},
        {'id': 'gh_token',         'prompt': 'GitHub PAT (classic) \u2014 needs repo + workflow + read:org', 'sensitive': True},
        {'id': 'xpander_email',    'prompt': 'Primary xpander.ai user email this agent operates for'},
        {'id': 'notion_workspace', 'prompt': "Notion workspace name (or 'skip')", 'optional': True},
    ]
    onboarding_doc = {
        'bundle': os.path.basename(bundle),
        'bundle_version': manifest.get('bundle_version'),
        'questions': questions,
        'instructions': (
            'Ask each question via xpask_for_information one at a time. For '
            "sensitive fields, instruct the user to paste the secret — never log "
            "or echo it. Save answers to a JSON file (e.g. "
            "workspace/tmp/onboarding_inputs.json) with each question id as the "
            'key, then run: bash workspace/dev-knowledge/skills/agent_import.sh --onboard '
            '--inputs=<that-json>. The inputs file lives under tmp/ and is '
            'excluded from the next export by construction.'
        ),
        'next_command': 'bash workspace/dev-knowledge/skills/agent_import.sh --onboard --inputs=<inputs.json>',
    }
    # Resolve persistent path: TS comes from the staging path basename (import_<ts>)
    staging_root = os.path.dirname(backup.rstrip(os.sep))  # .../import_<ts>
    ts_label = os.path.basename(staging_root).removeprefix('import_')
    onb_path = os.path.join(target, 'tmp', f'import_{ts_label}_onboarding_required.json')
    os.makedirs(os.path.dirname(onb_path), exist_ok=True)
    with open(onb_path, 'w') as fh:
        json.dump(onboarding_doc, fh, indent=2)
    summary['onboarding_required'] = True
    summary['onboarding_manifest'] = onb_path

print(json.dumps(summary, indent=2))
PY
