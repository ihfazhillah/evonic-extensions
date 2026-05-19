# Evonic Extensions

Custom plugins, skills, and tools for [Evonic](https://evonic.dev).

## What's Included

### Plugins

| Plugin | Description |
|--------|-------------|
| **ruff_autoformat** | Automatically runs `ruff check --fix` and `ruff format` on Python files after an agent edits them. Injects unfixable lint errors into the agent's conversation. Discovers ruff via: system PATH, `uv run ruff`, or `.venv/bin/ruff`. |
| **tsc_checker** | Automatically runs TypeScript type checking on `.ts`/`.tsx` files after an agent edits them. Injects type errors into the agent's conversation. Discovers tsc via: system PATH, `npx tsc`, or `node_modules/.bin/tsc`. |

### Skills

| Skill | Description |
|-------|-------------|
| **project_planner** | Structured 6-phase workflow: discovery, multi-aspect analysis, peer review via sub-agents, delegation mapping, kanban task creation, and monitoring. Designed for the super/lead agent. |
| **human_qa_workflow** | Human-in-the-loop QA: enumerate targets, plan verification strategy, delegate execution to agents, collect pass/fail results, coordinate fixes. Loop until human is satisfied. |

### Tools

| Tool | Description |
|------|-------------|
| **setup_workspace** | Git branch and worktree management. Create branches, create worktrees for parallel agent work, list them, and clean up when done. |

## Installation

### Prerequisites

- A running [Evonic](https://evonic.dev) instance
- Git

### Steps

1. Clone this repo next to your evonic directory:

```bash
cd ~/Projects
git clone <repo-url> evonic-extensions
```

2. Create symlinks from your evonic installation to the extensions:

```bash
EVONIC=~/Projects/evonic
EXT=~/Projects/evonic-extensions

# Plugin: ruff_autoformat
ln -s $EXT/plugins/ruff_autoformat $EVONIC/plugins/ruff_autoformat

# Plugin: tsc_checker
ln -s $EXT/plugins/tsc_checker $EVONIC/plugins/tsc_checker

# Skill: project_planner
ln -s $EXT/skills/project_planner $EVONIC/skills/project_planner

# Skill: human_qa_workflow
ln -s $EXT/skills/human_qa_workflow $EVONIC/skills/human_qa_workflow

# Tool: setup_workspace
ln -s $EXT/tools/setup_workspace.json $EVONIC/tools/setup_workspace.json
ln -s $EXT/backend/tools/setup_workspace.py $EVONIC/backend/tools/setup_workspace.py
```

3. Restart evonic (or it will hot-reload tools automatically).

4. Assign the extensions to your agents via the Web UI or CLI:
   - **ruff_autoformat**: enabled globally (all agents) by default, or set `ENABLED_AGENTS` in plugin config
   - **tsc_checker**: enabled globally by default, or set `ENABLED_AGENTS` in plugin config. Set `TSC_ARGS` for extra tsc flags (default: `--noEmit`)
   - **project_planner**: assign the skill to your lead/super agent (also needs `kanban` and `subagent` skills)
   - **human_qa_workflow**: assign to your lead/super agent (also needs `kanban` skill)
   - **setup_workspace**: assign the tool to any agent that needs git branch management

### Uninstall

Remove the symlinks — the evonic project is untouched:

```bash
rm $EVONIC/plugins/ruff_autoformat
rm $EVONIC/plugins/tsc_checker
rm $EVONIC/skills/project_planner
rm $EVONIC/skills/human_qa_workflow
rm $EVONIC/tools/setup_workspace.json
rm $EVONIC/backend/tools/setup_workspace.py
```

---

## Creating Your Own Extensions

### Creating a Plugin

Plugins are event-driven extensions that react to platform events.

#### Directory structure

```
plugins/my_plugin/
├── plugin.json    # Manifest
└── handler.py     # Event handlers
```

#### plugin.json

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "What this plugin does",
  "author": "Your Name",
  "enabled": true,
  "events": ["tool_executed", "turn_complete"],
  "variables": [
    {
      "name": "MY_VAR",
      "label": "My Variable",
      "type": "string",
      "default": "",
      "description": "Configurable from the UI"
    }
  ]
}
```

**Available events:**

| Event | When it fires |
|-------|--------------|
| `message_received` | User sends a message |
| `processing_started` | Agent starts processing |
| `tool_executed` | After a tool call completes |
| `llm_thinking` | LLM is generating |
| `llm_response_chunk` | Streaming response chunk |
| `final_answer` | Agent produces final response |
| `turn_complete` | Full turn finished (tools + response) |
| `message_sent` | Response delivered to user |
| `session_created` | New session started |
| `summary_updated` | Conversation summarized |
| `state_transition` | Agent state changed |
| `kanban_task_created` | Kanban task created |
| `kanban_task_updated` | Kanban task updated |
| `schedule_fired` | Scheduled job triggered |
| `schedule_created` | New schedule created |
| `schedule_cancelled` | Schedule removed |

**Variable types:** `string`, `number`, `boolean`, `textarea`

#### handler.py

Each event you listen to needs an `on_{event_name}` function:

```python
def on_tool_executed(event, sdk):
    """Called after any tool executes."""
    tool_name = event.get('tool_name', '')
    agent_id = event.get('agent_id', '')
    args = event.get('tool_args', {})
    result = event.get('tool_result', {})
    has_error = event.get('has_error', False)

    # Your logic here
    sdk.log(f"Tool {tool_name} executed by {agent_id}")


def on_turn_complete(event, sdk):
    """Called when an agent finishes a full turn."""
    agent_id = event.get('agent_id', '')
    message = event.get('message', '')

    # Access plugin config
    my_var = sdk.config.get('MY_VAR', '')

    # Send a message to a user
    sdk.send_message(agent_id, external_user_id, channel_id, "Hello")

    # Make an HTTP request
    resp = sdk.http_request('POST', 'https://api.example.com/hook', json={'text': message})

    # Use plugin's own database
    with sdk.get_db_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, msg TEXT)")
        conn.execute("INSERT INTO logs (msg) VALUES (?)", (message,))
        conn.commit()
```

**SDK methods:**

| Method | Purpose |
|--------|---------|
| `sdk.send_message(agent_id, user_id, channel_id, text)` | Send message to a user |
| `sdk.http_request(method, url, headers, json, data, timeout)` | HTTP request |
| `sdk.get_session_messages(session_id, limit)` | Read session history |
| `sdk.get_session(session_id)` | Get session details |
| `sdk.log(message, level)` | Log (level: info/warn/error) |
| `sdk.get_db_connection()` | Context manager for plugin's SQLite DB |
| `sdk.create_schedule(name, trigger_type, trigger_config, action_type, action_config)` | Create scheduled job |
| `sdk.cancel_schedule(schedule_id)` | Cancel a schedule |
| `sdk.list_schedules()` | List plugin's schedules |

#### Optional: routes.py

Add web routes to your plugin:

```python
from flask import Blueprint, jsonify

def create_blueprint():
    bp = Blueprint('my_plugin', __name__, url_prefix='/my-plugin')

    @bp.route('/status', methods=['GET'])
    def status():
        return jsonify({"status": "ok"})

    return bp
```

#### Symlink and activate

```bash
ln -s $EXT/plugins/my_plugin $EVONIC/plugins/my_plugin
```

The plugin loads automatically on next restart if `"enabled": true` in the manifest.

---

### Creating a Skill

Skills are installable packages that give agents new tools and/or behavioral instructions.

#### Directory structure

```
skills/my_skill/
├── skill.json              # Manifest
├── tools.json              # Tool definitions (OpenAI function schema)
├── SYSTEM.md               # System prompt injected into agent (optional)
└── backend/tools/          # Python tool implementations (optional)
    └── my_tool.py
```

#### skill.json

```json
{
  "id": "my_skill",
  "name": "My Skill",
  "version": "1.0.0",
  "description": "What this skill does",
  "brief": "Short one-liner",
  "author": "Your Name",
  "tools_file": "tools.json",
  "super_only": false,
  "lazy_tools": false,
  "variables": [
    {
      "name": "API_KEY",
      "label": "API Key",
      "type": "string",
      "default": "",
      "description": "API key for external service"
    }
  ]
}
```

**Key fields:**
- `tools_file` — points to the JSON file with tool definitions
- `super_only` — if true, only the super agent can use this skill
- `lazy_tools` — if true, tools are only loaded when agent calls `use_skill("my_skill")`

#### tools.json

Array of OpenAI function calling definitions:

```json
[
  {
    "type": "function",
    "function": {
      "name": "my_tool",
      "description": "What this tool does. Be descriptive — the LLM reads this.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Search query"
          },
          "limit": {
            "type": "integer",
            "description": "Max results to return",
            "default": 10
          }
        },
        "required": ["query"]
      }
    }
  }
]
```

Use an empty array `[]` if the skill only provides a SYSTEM.md with no tools.

#### SYSTEM.md

Markdown content that gets injected into the agent's system prompt when this skill is assigned:

```markdown
# My Skill

You have access to the my_tool function. Use it when the user asks about ...

## Rules
- Always validate input before calling the tool
- Present results in a table format
```

#### backend/tools/my_tool.py

Python implementation. The filename must match the `function.name` in tools.json:

```python
def execute(agent_ctx: dict, args: dict) -> dict:
    """Tool implementation.

    Args:
        agent_ctx: Agent context with id, session_id, workspace, skill_config, etc.
        args: Arguments from the LLM matching the tool's parameter schema.

    Returns:
        dict with 'result' on success or 'error' on failure.
    """
    query = args.get('query', '')
    if not query:
        return {'error': "Missing required argument: 'query'"}

    # Access skill variables
    api_key = agent_ctx.get('skill_config', {}).get('API_KEY', '')

    # Your logic here
    return {'result': f"Found results for: {query}"}
```

#### Symlink and assign

```bash
ln -s $EXT/skills/my_skill $EVONIC/skills/my_skill
```

Then assign the skill to an agent via Web UI (`/skills`) or CLI (`evonic skill`).

---

### Creating a Tool

Tools are standalone functions that agents can call. Unlike skill tools, they live in evonic's global tool registry.

#### Files needed

```
tools/my_tool.json              # Tool definition (for LLM)
backend/tools/my_tool.py        # Python implementation
```

Both filenames must match the `function.name`.

#### tools/my_tool.json

```json
{
  "id": "my_tool",
  "name": "My Tool",
  "description": "Human-readable description for the UI",
  "function": {
    "name": "my_tool",
    "description": "Description the LLM sees. Be specific about when and how to use this tool.",
    "parameters": {
      "type": "object",
      "properties": {
        "action": {
          "type": "string",
          "enum": ["create", "list", "delete"],
          "description": "What to do"
        },
        "name": {
          "type": "string",
          "description": "Name of the resource"
        }
      },
      "required": ["action"]
    }
  },
  "mock_response": "var args = ARGS; console.log(JSON.stringify({result: 'mock', action: args.action}));",
  "mock_response_type": "javascript",
  "created_at": "2026-01-01T00:00:00.000000",
  "updated_at": "2026-01-01T00:00:00.000000"
}
```

**`mock_response`** is used in eval/test mode. It receives `ARGS` (the tool arguments) and must `console.log(JSON.stringify(...))` the result.

#### backend/tools/my_tool.py

```python
def execute(agent: dict, args: dict) -> dict:
    """Tool implementation.

    Args:
        agent: Agent context dict with keys:
            - id / agent_id: Agent identifier
            - session_id: Current session
            - workspace: Agent's working directory
            - sandbox_enabled: 0 or 1
            - is_super: Boolean
            - assigned_tool_ids: List of authorized tools
        args: Arguments from the LLM.

    Returns:
        dict — never raise exceptions, always return a dict.
    """
    action = args.get('action', '')

    if action == 'list':
        return {'result': 'success', 'items': ['a', 'b', 'c']}

    if action == 'create':
        name = args.get('name', '')
        if not name:
            return {'error': "Missing required argument: 'name'"}
        return {'result': 'success', 'message': f"Created {name}"}

    return {'error': f"Unknown action: {action}"}
```

**Running shell commands from a tool:**

```python
from backend.tools.lib.exec_backend import registry

def execute(agent: dict, args: dict) -> dict:
    session_id = (agent or {}).get('session_id') or 'default'
    backend = registry.get_backend(session_id, agent)

    result = backend.run_bash('ls -la', timeout=30, env={})
    # Returns: {stdout, stderr, exit_code, execution_time}

    if result.get('exit_code', -1) != 0:
        return {'error': result.get('stderr', 'command failed')}

    return {'result': result.get('stdout', '')}
```

#### Symlink and assign

```bash
ln -s $EXT/tools/my_tool.json $EVONIC/tools/my_tool.json
ln -s $EXT/backend/tools/my_tool.py $EVONIC/backend/tools/my_tool.py
```

The tool registry auto-discovers new tools. Assign the tool to agents via Web UI or API.

---

## Choosing the Right Extension Type

| I want to... | Use |
|--------------|-----|
| React to events (tool calls, messages, turns) | **Plugin** |
| Add web routes or dashboard cards | **Plugin** |
| Block or modify tool behavior | **Plugin** (tool guards, interceptors) |
| Give an agent new callable functions | **Skill** (with tools) or **Tool** |
| Change how an agent behaves via system prompt | **Skill** (with SYSTEM.md) |
| Add a reusable function for any agent | **Tool** |

## License

MIT
