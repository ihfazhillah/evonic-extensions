"""
setup_workspace — create git branches or worktrees for isolated parallel development.

Actions:
  branch          — create and checkout a new branch
  worktree        — create a git worktree with a new branch in a sibling directory
  list            — show branches and worktrees
  remove_worktree — clean up a worktree when done
"""

import os
import re

from backend.tools.lib.exec_backend import registry

_BRANCH_RE = re.compile(r'^[A-Za-z0-9._/\-]+$')
_WORKTREE_BASE = '../worktrees'


def _validate_name(name: str) -> str | None:
    if not name:
        return "Missing required argument: 'name'"
    if not _BRANCH_RE.match(name):
        return f"Invalid branch name: {name!r}. Use alphanumeric, dots, hyphens, underscores, and slashes only."
    if '..' in name:
        return "Branch name must not contain '..'"
    return None


def _run(backend, script: str, timeout: int = 30) -> dict:
    return backend.run_bash(script, timeout=timeout, env={})


def _branch(backend, args: dict) -> dict:
    name = (args.get('name') or '').strip()
    err = _validate_name(name)
    if err:
        return {'error': err}

    base = (args.get('base') or '').strip()
    if base:
        err = _validate_name(base)
        if err:
            return {'error': f"Invalid base: {err}"}

    cmd = f'git checkout -b {name}'
    if base:
        cmd = f'git fetch origin {base} 2>/dev/null; git checkout -b {name} {base}'

    r = _run(backend, cmd)
    if r.get('exit_code', -1) != 0:
        stderr = r.get('stderr', '').strip()
        if 'already exists' in stderr:
            return {'error': f"Branch '{name}' already exists. Use a different name or switch to it with: git checkout {name}"}
        return {'error': f"Failed to create branch: {stderr or 'unknown error'}"}

    return {
        'result': 'success',
        'action': 'branch',
        'branch': name,
        'message': f"Created and switched to branch '{name}'",
    }


def _worktree(backend, args: dict) -> dict:
    name = (args.get('name') or '').strip()
    err = _validate_name(name)
    if err:
        return {'error': err}

    base = (args.get('base') or '').strip()
    if base:
        err = _validate_name(base)
        if err:
            return {'error': f"Invalid base: {err}"}

    dir_name = name.replace('/', '-')
    wt_path = os.path.join(_WORKTREE_BASE, dir_name)

    cmd = f'mkdir -p {_WORKTREE_BASE} && git worktree add {wt_path} -b {name}'
    if base:
        cmd = f'mkdir -p {_WORKTREE_BASE} && git fetch origin {base} 2>/dev/null && git worktree add {wt_path} -b {name} {base}'

    r = _run(backend, cmd, timeout=60)
    if r.get('exit_code', -1) != 0:
        stderr = r.get('stderr', '').strip()
        if 'already exists' in stderr:
            return {'error': f"Branch '{name}' or worktree at '{wt_path}' already exists."}
        return {'error': f"Failed to create worktree: {stderr or 'unknown error'}"}

    abs_path = r.get('stdout', '').strip() or wt_path
    return {
        'result': 'success',
        'action': 'worktree',
        'branch': name,
        'path': wt_path,
        'message': f"Worktree created at '{wt_path}' on branch '{name}'",
    }


def _list(backend) -> dict:
    r_branches = _run(backend, 'git branch --no-color 2>/dev/null')
    r_worktrees = _run(backend, 'git worktree list --porcelain 2>/dev/null')

    branches = []
    current = None
    for line in (r_branches.get('stdout') or '').splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('* '):
            current = line[2:].strip()
            branches.append(current)
        else:
            branches.append(line)

    worktrees = []
    wt = {}
    for line in (r_worktrees.get('stdout') or '').splitlines():
        if line.startswith('worktree '):
            if wt:
                worktrees.append(wt)
            wt = {'path': line[9:].strip()}
        elif line.startswith('branch '):
            wt['branch'] = line[7:].strip().replace('refs/heads/', '')
        elif line == 'bare':
            wt['bare'] = True
        elif not line.strip():
            if wt:
                worktrees.append(wt)
                wt = {}
    if wt:
        worktrees.append(wt)

    return {
        'result': 'success',
        'action': 'list',
        'current_branch': current,
        'branches': branches,
        'worktrees': worktrees,
    }


def _remove_worktree(backend, args: dict) -> dict:
    name = (args.get('name') or '').strip()
    if not name:
        return {'error': "Missing required argument: 'name' (worktree path or branch name)"}

    if '/' in name and not name.startswith('.'):
        dir_name = name.replace('/', '-')
        wt_path = os.path.join(_WORKTREE_BASE, dir_name)
    else:
        wt_path = name

    r = _run(backend, f'git worktree remove {wt_path} --force 2>&1')
    if r.get('exit_code', -1) != 0:
        stderr = r.get('stderr', '') or r.get('stdout', '')
        return {'error': f"Failed to remove worktree: {stderr.strip() or 'unknown error'}"}

    return {
        'result': 'success',
        'action': 'remove_worktree',
        'path': wt_path,
        'message': f"Worktree at '{wt_path}' removed",
    }


def execute(agent: dict, args: dict) -> dict:
    action = (args.get('action') or '').strip()
    if not action:
        return {'error': "Missing required argument: 'action'"}

    session_id = (agent or {}).get('session_id') or 'default'
    backend = registry.get_backend(session_id, agent)

    if action == 'branch':
        return _branch(backend, args)
    elif action == 'worktree':
        return _worktree(backend, args)
    elif action == 'list':
        return _list(backend)
    elif action == 'remove_worktree':
        return _remove_worktree(backend, args)
    else:
        return {'error': f"Unknown action: {action!r}. Use 'branch', 'worktree', 'list', or 'remove_worktree'."}
