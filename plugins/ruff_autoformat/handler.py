"""
Ruff Auto Format Plugin — automatically lint & format Python files after agent edits.

Listens to tool_executed events for file-writing tools (write_file, str_replace,
file_edit, file_create). When the target is a .py file, runs ruff check --fix
and ruff format.

If ruff check finds unfixable errors, they are injected into the agent's
conversation via a message interceptor so the agent can fix them.

Ruff discovery order:
  1. ruff (system PATH)
  2. uv run ruff (project-managed via uv)
  3. .venv/bin/ruff (virtualenv in project root)
"""

import os
import shutil
import subprocess
import threading

PLUGIN_ID = 'ruff_autoformat'

_WRITE_TOOLS = {
    'write_file':  'file_path',
    'str_replace': 'file_path',
    'file_edit':   'filename',
    'file_create': 'filename',
}

_ruff_cmd_cache: list | None = None

_pending_errors: dict = {}
_pending_lock = threading.Lock()


def _find_project_root(file_path: str) -> str | None:
    """Walk up from file_path looking for pyproject.toml, setup.py, or .venv/."""
    d = os.path.dirname(os.path.abspath(file_path))
    for _ in range(20):
        if (os.path.isfile(os.path.join(d, 'pyproject.toml'))
                or os.path.isfile(os.path.join(d, 'setup.py'))
                or os.path.isdir(os.path.join(d, '.venv'))):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _resolve_ruff(file_path: str) -> list | None:
    """Resolve the ruff command, caching the result."""
    global _ruff_cmd_cache
    if _ruff_cmd_cache is not None:
        return _ruff_cmd_cache

    if shutil.which('ruff'):
        _ruff_cmd_cache = ['ruff']
        return _ruff_cmd_cache

    if shutil.which('uv'):
        try:
            r = subprocess.run(
                ['uv', 'run', 'ruff', '--version'],
                capture_output=True, timeout=10,
            )
            if r.returncode == 0:
                _ruff_cmd_cache = ['uv', 'run', 'ruff']
                return _ruff_cmd_cache
        except Exception:
            pass

    root = _find_project_root(file_path)
    if root:
        venv_ruff = os.path.join(root, '.venv', 'bin', 'ruff')
        if os.path.isfile(venv_ruff) and os.access(venv_ruff, os.X_OK):
            _ruff_cmd_cache = [venv_ruff]
            return _ruff_cmd_cache

    return None


def _run_ruff(ruff_cmd: list, file_path: str, agent_id: str, sdk):
    errors = []
    try:
        r1 = subprocess.run(
            [*ruff_cmd, 'check', '--fix', file_path],
            capture_output=True, text=True, timeout=30,
        )
        r2 = subprocess.run(
            [*ruff_cmd, 'format', file_path],
            capture_output=True, text=True, timeout=30,
        )

        if r1.returncode != 0:
            output = (r1.stdout or '').strip()
            if output:
                errors.append(output)
            if r1.stderr:
                sdk.log(f"ruff check: {r1.stderr.strip()}", level="warn")

        if r2.returncode != 0 and r2.stderr:
            sdk.log(f"ruff format: {r2.stderr.strip()}", level="warn")

        if not errors:
            sdk.log(f"ruff OK: {file_path}")

    except subprocess.TimeoutExpired:
        sdk.log(f"ruff timeout on {file_path}", level="warn")
    except Exception as e:
        sdk.log(f"ruff error: {e}", level="error")

    if errors:
        with _pending_lock:
            if agent_id not in _pending_errors:
                _pending_errors[agent_id] = []
            _pending_errors[agent_id].append({
                'file': file_path,
                'errors': '\n'.join(errors),
            })


def _message_interceptor(agent_id: str, content: str, messages: list):
    """Inject ruff errors into the agent's conversation before the next LLM call."""
    with _pending_lock:
        agent_errors = _pending_errors.pop(agent_id, None)

    if not agent_errors:
        return None

    parts = ['[ruff] Lint errors found after your last edit. Please fix them:\n']
    for entry in agent_errors:
        parts.append(f"**{entry['file']}**:\n```\n{entry['errors']}\n```")

    return {'inject': '\n'.join(parts)}


def on_tool_executed(event, sdk):
    tool_name = event.get('tool_name', '')
    if tool_name not in _WRITE_TOOLS:
        return

    if event.get('has_error'):
        return

    args = event.get('tool_args', {})
    path_key = _WRITE_TOOLS[tool_name]
    file_path = args.get(path_key, '')
    if not file_path or not file_path.endswith('.py'):
        return

    agent_id = event.get('agent_id', '')

    enabled_agents = sdk.config.get('ENABLED_AGENTS', '').strip()
    if enabled_agents:
        allowed = {a.strip() for a in enabled_agents.split(',') if a.strip()}
        if agent_id not in allowed:
            return

    ruff_cmd = _resolve_ruff(file_path)
    if not ruff_cmd:
        sdk.log("ruff not found (tried: ruff, uv run ruff, .venv/bin/ruff)", level="warn")
        return

    _run_ruff(ruff_cmd, file_path, agent_id, sdk)


# ─── Register hooks ──────────────────────────────────────────────────────────

try:
    from backend.plugin_manager import register_message_interceptor
    register_message_interceptor(_message_interceptor)
except Exception:
    pass
