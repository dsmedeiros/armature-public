#!/usr/bin/env bash
# Armature PreToolUse hook — check-required-reading
# Event:  PreToolUse(Edit|Write)
# Stdin:  JSON object with a tool_input.file_path field (Claude Code hook payload)
#
# Behavior (MVP — advisory only):
#   1. Parse stdin JSON to extract the target file path.
#   2. Walk up the directory tree from that file to find the nearest agents.md /
#      AGENTS.md, stopping at REPO_ROOT.
#   3. Parse its YAML frontmatter to extract the `adrs` list.
#   4. Resolve each ADR ID to a file via glob: docs/adr/{ID}* (e.g. 0001-…).
#   5. Print an advisory listing the agents.md file and all resolved ADR files.
#   6. Always exit 0 (advisory — never blocks).
#
# Future upgrade path — from advisory to enforcing:
#   A companion PostToolUse(Read) hook could write read-receipt markers to
#   .armature/.read-receipts/<sha256-of-abs-path> whenever the agent reads a
#   file.  This hook would then check for a receipt for each required file and
#   exit 2 (block) if any receipt is missing, turning the advisory into a hard
#   gate.  The MVP exits 0 unconditionally so that existing workflows are not
#   disrupted while the receipt infrastructure is being built.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Resolve python command (python3 preferred, fall back to python)
PYTHON=""
if command -v python3 &>/dev/null; then
  PYTHON="python3"
elif command -v python &>/dev/null; then
  PYTHON="python"
fi

if [ -z "$PYTHON" ]; then
  echo "SKIP: No python available to parse hook payload"
  exit 0
fi

# Read the full stdin payload once
PAYLOAD="$(cat)"

HOOK_PAYLOAD="$PAYLOAD" HOOK_REPO_ROOT="$REPO_ROOT" $PYTHON -c "
import sys, os, json, re, glob

payload_raw = os.environ['HOOK_PAYLOAD']
repo_root   = os.environ['HOOK_REPO_ROOT']

# ---------------------------------------------------------------------------
# 1. Extract target file path from JSON payload
# ---------------------------------------------------------------------------
try:
    payload = json.loads(payload_raw)
except json.JSONDecodeError as e:
    print(f'SKIP: Could not parse hook payload as JSON: {e}')
    sys.exit(0)

file_path = (
    payload.get('tool_input', {}).get('file_path')
    or payload.get('file_path')
    or ''
)

if not file_path:
    print('SKIP: No file_path found in hook payload')
    sys.exit(0)

# Normalise to absolute path
if not os.path.isabs(file_path):
    file_path = os.path.join(repo_root, file_path)
file_path = os.path.normpath(file_path)

# ---------------------------------------------------------------------------
# 2. Walk up the directory tree to find the nearest agents.md / AGENTS.md,
#    stopping at (and including) REPO_ROOT.
# ---------------------------------------------------------------------------
def find_agents_md(start_dir, root):
    current = start_dir
    while True:
        for name in ('agents.md', 'AGENTS.md'):
            candidate = os.path.join(current, name)
            if os.path.isfile(candidate):
                return candidate
        if os.path.normpath(current) == os.path.normpath(root):
            break
        parent = os.path.dirname(current)
        if parent == current:
            # Filesystem root reached before REPO_ROOT
            break
        current = parent
    return None

start_dir = os.path.dirname(file_path)
agents_file = find_agents_md(start_dir, repo_root)

if agents_file is None:
    print(f'SKIP: No governance file found for {file_path}')
    sys.exit(0)

# ---------------------------------------------------------------------------
# 3. Parse YAML frontmatter to extract the adrs field
# ---------------------------------------------------------------------------
try:
    import yaml
    have_yaml = True
except ImportError:
    have_yaml = False

adr_ids = []

try:
    with open(agents_file) as f:
        content = f.read()
except OSError as e:
    print(f'SKIP: Could not read {agents_file}: {e}')
    sys.exit(0)

if content.startswith('---'):
    end = content.find('---', 3)
    if end > 0:
        frontmatter_text = content[3:end]
        if have_yaml:
            try:
                fm = yaml.safe_load(frontmatter_text) or {}
                raw_adrs = fm.get('adrs', [])
                # Normalise: may be a list or a bare string
                if isinstance(raw_adrs, list):
                    adr_ids = [str(a) for a in raw_adrs]
                elif raw_adrs:
                    adr_ids = [str(raw_adrs)]
            except Exception:
                pass
        else:
            # Fallback: regex extraction when PyYAML is unavailable
            adr_ids = re.findall(r'ADR-\d+', frontmatter_text)

# ---------------------------------------------------------------------------
# 4. Resolve each ADR ID to a file path via glob
# ---------------------------------------------------------------------------
def resolve_adr(adr_id, root):
    # Strip the 'ADR-' prefix to get the numeric portion
    numeric = re.sub(r'^ADR-', '', adr_id).lstrip('0') or '0'
    padded  = re.sub(r'^ADR-', '', adr_id)          # e.g. '0001'
    for pattern in (
        os.path.join(root, 'docs', 'adr', f'{padded}-*'),
        os.path.join(root, 'docs', 'adr', f'ADR-{padded}*'),
        os.path.join(root, 'docs', 'adr', f'*{numeric}*'),
    ):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None

def rel(path, root):
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path  # Different drive on Windows — return as-is

# ---------------------------------------------------------------------------
# 5. Build and print the advisory
# ---------------------------------------------------------------------------
agents_rel = rel(agents_file, repo_root)

lines = [f'ADVISORY: Required reading for scope governed by {agents_rel}:',
         f'  - {agents_rel}']

for adr_id in adr_ids:
    resolved = resolve_adr(adr_id, repo_root)
    if resolved:
        lines.append(f'  - {rel(resolved, repo_root)}')
    else:
        lines.append(f'  - {adr_id} (file not found — check docs/adr/)')

lines.append('Ensure you have read these files before modifying code in this scope.')

print('\n'.join(lines))
sys.exit(0)
"

exit 0
