#!/usr/bin/env bash
# Armature Stop hook — harness-feedback.sh
# Event: Stop
# Invariant: NONE — advisory-only, no enforcement backing per PRD G8
#
# Behavior:
#   Surfaces one curated cross-project lesson per Stop event, filtered by
#   current SDLC phase.  Lessons are drawn from .armature/lessons.yaml
#   (primary) plus local .armature/antipatterns.md and
#   .armature/postmortems/*.md with mtime < 30 days (secondary candidates).
#
# Selection:
#   Pick the lesson with the highest id (lexicographic max) from the set of
#   lessons filtered for the current phase.  If the filtered set is empty,
#   fall back to random.choice across the full corpus.
#
# Output:
#   HTML comment to stdout:
#     <!-- HARNESS-FEEDBACK
#     lesson-id=<id>
#     phase=<phase>
#     title=<sanitized title>
#     -->
#   Prose to stderr:
#     HARNESS-FEEDBACK [<id>]: <title>
#       <text lines, 2-space indent>
#
# Exit codes:
#   0  always — advisory hook, never blocks work.
#
# Hotfix bypass:
#   If .armature/session/phase == "Hotfix" (ASCII-only strip), emit
#   ADVISORY to stderr and exit 0 WITHOUT emitting the HTML comment.
#
# Defensive patterns applied (M1-M6):
#   - NUL-byte rejection before decode (L001)
#   - ASCII-only .strip(' \t\n\r') for phase reads (L008)
#   - python3 -> python fallback (M2)
#   - || true on advisory Python block under set -euo pipefail (L004)
#   - HTML comment value sanitization: replace -- with - -, strip newlines,
#     cap at 200 chars (auto-reviewer.sh pattern)
#
# Cross-platform: bash + Git Bash (Windows) compatible.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve Python interpreter (python3 preferred, python fallback).
# ---------------------------------------------------------------------------
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
fi

if [ -z "$PYTHON" ]; then
    echo "ADVISORY: Python not available; harness-feedback skipped" >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Resolve REPO_ROOT via git, fall back to current directory.
# ---------------------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# ---------------------------------------------------------------------------
# Hotfix bypass — Python inline block (NOT heredoc to avoid stdin hijack).
# ASCII-only strip (L008: Unicode whitespace bypass).
# ---------------------------------------------------------------------------
export _HF_REPO_ROOT="$REPO_ROOT"

IS_HOTFIX="$("$PYTHON" -c "
import os
p = os.path.join(os.environ.get('_HF_REPO_ROOT', '.'), '.armature', 'session', 'phase')
try:
    with open(p, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8', errors='replace').strip(' \t\n\r')
    print('yes' if text == 'Hotfix' else 'no')
except OSError:
    print('no')
")"

if [ "$IS_HOTFIX" = "yes" ]; then
    echo "ADVISORY: Hotfix phase active — harness feedback bypassed" >&2
    exit 0
fi

# ---------------------------------------------------------------------------
# Main lesson selection and emission — advisory-only Python block.
# || true ensures advisory failures never propagate (L004).
# ---------------------------------------------------------------------------
"$PYTHON" - <<'PYEOF' || true
import os
import random
import sys
import time

REPO_ROOT = os.environ.get("_HF_REPO_ROOT", ".")
LESSONS_PATH = os.path.join(REPO_ROOT, ".armature", "lessons.yaml")
PHASE_FILE = os.path.join(REPO_ROOT, ".armature", "session", "phase")
ANTIPATTERNS_PATH = os.path.join(REPO_ROOT, ".armature", "antipatterns.md")
POSTMORTEMS_DIR = os.path.join(REPO_ROOT, ".armature", "postmortems")

# ---- Sanitize helper (auto-reviewer.sh pattern) ----
def _sanitize(val, max_len=200):
    """Strip newlines, replace --> with - ->, replace -- with - -, cap length."""
    val = str(val)
    val = val.replace("\n", " ").replace("\r", " ")
    val = val.replace("-->", "- ->")
    val = val.replace("--", "- -")
    return val[:max_len]

# ---- 1. Read lessons.yaml bytes; NUL-byte check ----
try:
    with open(LESSONS_PATH, "rb") as fh:
        raw = fh.read()
except OSError:
    sys.stderr.write("harness-feedback: no lessons corpus found\n")
    sys.exit(0)

if b"\x00" in raw:
    sys.stderr.write("harness-feedback: lessons.yaml contains NUL bytes; skipping\n")
    sys.exit(0)

# ---- 2. Parse YAML ----
try:
    import yaml
    data = yaml.safe_load(raw.decode("utf-8", errors="replace"))
except Exception as exc:
    sys.stderr.write("harness-feedback: lessons.yaml parse error: {}\n".format(exc))
    sys.exit(0)

if not isinstance(data, dict):
    sys.stderr.write("harness-feedback: lessons.yaml must be a YAML mapping\n")
    sys.exit(0)

lessons = data.get("lessons", [])
if not isinstance(lessons, list):
    lessons = []

if not lessons:
    sys.stderr.write("harness-feedback: no lessons available\n")
    sys.exit(0)

# ---- 3. Read current phase (ASCII-only strip, L008) ----
current_phase = "Implementation"
try:
    with open(PHASE_FILE, "rb") as pf:
        phase_raw = pf.read()
    current_phase = phase_raw.decode("utf-8", errors="replace").strip(" \t\n\r") or "Implementation"
except OSError:
    pass

# ---- 4. Filter lessons by current phase ----
filtered = []
for lesson in lessons:
    if not isinstance(lesson, dict):
        continue
    phases = lesson.get("phases")
    if not phases:
        # Empty list or absent = universal
        filtered.append(lesson)
    elif isinstance(phases, list) and current_phase in phases:
        filtered.append(lesson)

# ---- 5. Local scan augmentation (best-effort) ----
THIRTY_DAYS = 30 * 24 * 3600
now = time.time()

try:
    if os.path.isfile(ANTIPATTERNS_PATH):
        mtime = os.path.getmtime(ANTIPATTERNS_PATH)
        if (now - mtime) < THIRTY_DAYS:
            filtered.append({
                "id": "LOCAL-ANTIPATTERNS",
                "title": "Recent local antipatterns",
                "phases": [],
                "tags": ["local"],
                "text": "Review .armature/antipatterns.md for recent entries (mtime <30 days).",
            })
except Exception:
    pass

try:
    if os.path.isdir(POSTMORTEMS_DIR):
        recent_pm = False
        for fname in os.listdir(POSTMORTEMS_DIR):
            if not fname.endswith(".md"):
                continue
            if fname.lower() == "readme.md":
                continue
            fpath = os.path.join(POSTMORTEMS_DIR, fname)
            try:
                mtime = os.path.getmtime(fpath)
                if (now - mtime) < THIRTY_DAYS:
                    recent_pm = True
                    break
            except OSError:
                continue
        if recent_pm:
            filtered.append({
                "id": "LOCAL-POSTMORTEMS",
                "title": "Recent local postmortems",
                "phases": [],
                "tags": ["local"],
                "text": "Review .armature/postmortems/ for recent entries (mtime <30 days).",
            })
except Exception:
    pass

# ---- 6. Selection: highest id (lexicographic max) from filtered set ----
if filtered:
    selected = max(filtered, key=lambda l: str(l.get("id", "")))
elif lessons:
    # Random fallback from full corpus
    selected = random.choice(lessons)
else:
    sys.stderr.write("harness-feedback: no applicable lessons\n")
    sys.exit(0)

lesson_id = _sanitize(selected.get("id", "unknown"))
lesson_title = _sanitize(selected.get("title", "(no title)"))
lesson_text = str(selected.get("text", "")).strip()

# ---- 7. Emit HTML comment to stdout ----
print("<!-- HARNESS-FEEDBACK")
print("lesson-id=" + lesson_id)
print("phase=" + _sanitize(current_phase))
print("title=" + lesson_title)
print("-->")

# ---- 8. Emit prose to stderr ----
sys.stderr.write("HARNESS-FEEDBACK [{}]: {}\n".format(lesson_id, lesson_title))
for line in lesson_text.splitlines():
    sys.stderr.write("  {}\n".format(line))

sys.exit(0)
PYEOF

exit 0
