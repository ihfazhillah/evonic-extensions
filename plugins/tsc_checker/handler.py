"""
TSC Type Checker Plugin — automatically run TypeScript type checking after agent edits.

Listens to tool_executed events for file-writing tools (write_file, str_replace,
file_edit, file_create). When the target is a .ts or .tsx file, runs tsc to check
for type errors.

If tsc finds errors, they are injected into the agent's conversation via a
message interceptor so the agent can fix them.

tsc discovery order:
  1. tsc (system PATH)
  2. npx tsc (via npx)
  3. node_modules/.bin/tsc (local project)
"""

import os
import shutil
import subprocess
import threading

PLUGIN_ID = 'tsc_checker'

_WRITE_TOOLS = {
    'write_file':  'file_path',
    'str_replace': 'file_path',
    'file_edit':   'filename',
    'file_create': 'filename',
}

_TS_EXTENSIONS = ('.ts', '.tsx')

_tsc_cmd_cache: list | None = None

_pending_errors: dict = {}
_pending_lock = threading.Lock()


def _find_project_root(file_path: str) -> str | None:
    """Walk up from file_path looking for tsconfig.json or package.json."""
    d = os.path.dirname(os.path.abspath(file_path))
    for _ in range(20):
        if (os.path.isfile(os.path.join(d, 'tsconfig.json'))
                or os.path.isfile(os.path.join(d, 'package.json'))):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _resolve_tsc(file_path: str) -> tuple[list | None, str | None]:
    """Resolve tsc command and project root. Returns (cmd, project_root)."""
    global _tsc_cmd_cache

    root = _find_project_root(file_path)

    if _tsc_cmd_cache is not None:
        return _tsc_cmd_cache, root

    if shutil.which('tsc'):
        _tsc_cmd_cache = ['tsc']
        return _tsc_cmd_cache, root

    if shutil.which('npx'):
        try:
            r = subprocess.run(
                ['npx', 'tsc', '--version'],
                capture_output=True, timeout=15,
                cwd=root,
            )
            if r.returncode == 0:
                _tsc_cmd_cache = ['npx', 'tsc']
                return _tsc_cmd_cache, root
        except Exception:
            pass

    if root:
        local_tsc = os.path.join(root, 'node_modules', '.bin', 'tsc')
        if os.path.isfile(local_tsc) and os.access(local_tsc, os.X_OK):
            _tsc_cmd_cache = [local_tsc]
            return _tsc_cmd_cache, root

    return None, root


def _run_tsc(tsc_cmd: list, file_path: str, project_root: str | None,
             agent_id: str, extra_args: str, sdk):
    errors = []
    try:
        cmd = [*tsc_cmd]
        for arg in extra_args.split():
            if arg.strip():
                cmd.append(arg.strip())

        has_tsconfig = project_root and os.path.isfile(
            os.path.join(project_root, 'tsconfig.json'))

        if has_tsconfig:
            cmd.extend(['--project', os.path.join(project_root, 'tsconfig.json')])
        else:
            cmd.append(file_path)

        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            cwd=project_root,
        )

        if r.returncode != 0:
            output = (r.stdout or '').strip()
            if output:
                if has_tsconfig:
                    relevant = _filter_errors_for_file(output, file_path)
                    if relevant:
                        errors.append(relevant)
                else:
                    errors.append(output)
            if r.stderr:
                sdk.log(f"tsc stderr: {r.stderr.strip()}", level="warn")

        if not errors:
            sdk.log(f"tsc OK: {file_path}")

    except subprocess.TimeoutExpired:
        sdk.log(f"tsc timeout on {file_path}", level="warn")
    except Exception as e:
        sdk.log(f"tsc error: {e}", level="error")

    if errors:
        with _pending_lock:
            if agent_id not in _pending_errors:
                _pending_errors[agent_id] = []
            _pending_errors[agent_id].append({
                'file': file_path,
                'errors': '\n'.join(errors),
            })


def _filter_errors_for_file(tsc_output: str, file_path: str) -> str:
    """When running with tsconfig, filter tsc output to only show errors from the edited file."""
    basename = os.path.basename(file_path)
    lines = tsc_output.splitlines()
    relevant = []
    for line in lines:
        if basename in line or (relevant and line.startswith(' ')):
            relevant.append(line)
    return '\n'.join(relevant)


def _message_interceptor(agent_id: str, content: str, messages: list):
    """Inject tsc errors into the agent's conversation before the next LLM call."""
    with _pending_lock:
        agent_errors = _pending_errors.pop(agent_id, None)

    if not agent_errors:
        return None

    parts = ['[tsc] TypeScript type errors found after your last edit. Please fix them:\n']
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
    if not file_path or not any(file_path.endswith(ext) for ext in _TS_EXTENSIONS):
        return

    agent_id = event.get('agent_id', '')

    enabled_agents = sdk.config.get('ENABLED_AGENTS', '').strip()
    if enabled_agents:
        allowed = {a.strip() for a in enabled_agents.split(',') if a.strip()}
        if agent_id not in allowed:
            return

    tsc_cmd, project_root = _resolve_tsc(file_path)
    if not tsc_cmd:
        sdk.log("tsc not found (tried: tsc, npx tsc, node_modules/.bin/tsc)", level="warn")
        return

    extra_args = sdk.config.get('TSC_ARGS', '--noEmit').strip()
    _run_tsc(tsc_cmd, file_path, project_root, agent_id, extra_args, sdk)


# ─── Register hooks ──────────────────────────────────────────────────────────

try:
    from backend.plugin_manager import register_message_interceptor
    register_message_interceptor(_message_interceptor)
except Exception:
    pass
