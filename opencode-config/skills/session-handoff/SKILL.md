# Session Handoff Protocol

Use this skill when working on a project across multiple parallel sessions, or when handing off work to a new session.

## When to Trigger

- User says "handoff", "pass to next session", "split work", "parallel session"
- User is about to end a session with incomplete work
- User wants 2 sessions working on the same project simultaneously

## Handoff File Format

Create/update `.session-handoff.json` in the project root:

```json
{
  "version": 1,
  "created_at": "ISO-8601 timestamp",
  "session_id": "current session identifier",
  "project": "project name",
  "scope": {
    "this_session": "what THIS session is responsible for",
    "other_session": "what the OTHER session should handle"
  },
  "completed": [
    "task 1 that was finished",
    "task 2 that was finished"
  ],
  "in_progress": [
    {
      "task": "what is being worked on",
      "files_touched": ["path/to/file1.py", "path/to/file2.py"],
      "status": "description of current state",
      "blockers": "any blockers or decisions needed"
    }
  ],
  "pending": [
    "task that hasn't started yet"
  ],
  "decisions_made": [
    {
      "decision": "what was decided",
      "reason": "why",
      "affects": ["which files/modules"]
    }
  ],
  "warnings": [
    "don't touch X because Y",
    "file Z has uncommitted experimental changes"
  ],
  "file_locks": [
    {
      "path": "src/module.py",
      "locked_by": "session-1",
      "reason": "actively refactoring"
    }
  ]
}
```

## Protocol Rules

### Starting a Session (Reader)

1. Check if `.session-handoff.json` exists in project root
2. If yes: read it, understand scope boundaries, respect file locks
3. If no: proceed normally, create handoff file if user requests parallel work

### During Work (Writer)

1. Update `in_progress` as you work
2. Add `file_locks` for files you're actively modifying
3. Add `decisions_made` for any architectural choices
4. Add `warnings` for anything the other session must know

### Ending a Session (Handoff)

1. Move completed items from `in_progress` to `completed`
2. Update `pending` with remaining work
3. Remove your `file_locks`
4. Add final `warnings` about state

### Anti-Collision Rules

- **Never edit files locked by another session**
- **Never contradict decisions made by another session** without explicit user approval
- **Always check handoff file before starting work** on shared modules
- **Scope must be non-overlapping** — if unclear, ask user to clarify boundaries

## Example Usage

User: "I want session 1 to handle backend API, session 2 to handle frontend"

Session 1 creates:
```json
{
  "scope": {
    "this_session": "Backend API: src/api/, src/models/, tests/api/",
    "other_session": "Frontend: frontend/, src/templates/, static/"
  },
  "file_locks": [
    {"path": "src/api/", "locked_by": "session-1", "reason": "building new endpoints"}
  ],
  "warnings": [
    "API contract not finalized yet — frontend should mock responses until handoff update"
  ]
}
```

## Integration with Existing Tools

- Works alongside `.opencode-context.md` (project context)
- Works alongside `claude-mem` (cross-session memory)
- Handoff file should be `.gitignore`d (ephemeral coordination, not source)
