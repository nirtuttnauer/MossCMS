# Product planning in Aftur

## Product improvement backlog — 11 October 2026

The owner requested product-management recommendations and new Aftur tickets. [The improvement backlog](IMPROVEMENTS-2026-10-11.md) records 11 new proposals, MC-35–MC-45 / TASK-35–TASK-45, with priorities, user outcomes, repository evidence, scope, acceptance criteria and recommended sequence. [The structured plan](improvements-2026-10-11.json) and [verified MCP receipt](improvements-2026-10-11-aftur.json) contain the same scopes and IDs.

The owner subsequently authorized implementation with “continue” and “use subagents to do these in parralel.” Product changes for TASK-35–TASK-44 are implemented and now recorded as Done following owner acceptance in Aftur. [The editing acceptance report](../editor-acceptance-2026-10-11.md) records integration checks, actual browser evidence and remaining manual checks for TASK-45. The report keeps TASK-45 partial: Safari200% and PostgreSQL evidence are recorded, while standalone Chromium and spoken VoiceOver remain owner-deferred manual checks. Existing MC-01–MC-34 scopes were excluded from the new work. The current MCP bridge preserved native acceptance criteria for all 11 new tickets.

[The execution receipt](improvements-2026-10-11-execution.json) records the current MCP readback and durable evidence checkpoints. The original implementation handoff put ten tasks in Review; the owner subsequently accepted them. TASK-45's [Safari keyboard supplement](../acceptance-2026-10-11/safari-keyboard.md) closes the remaining available keyboard checks, with 271 web tests/build passing and fixture cleanup verified. It remains in Review for owner-deferred standalone Chromium and spoken VoiceOver evidence. The original import receipt remains a historical record of proposal creation.

## Initial release plan — 7 October 2026

The owner requested a project PRD and smaller tasks in the local Aftur application on 7 October 2026.

- [PRD](../PRD.md): current baseline, owner requirements, proposed improvements, acceptance criteria, release gates and open decisions.
- [Task breakdown](TASKS.md): initial readable plan and Aftur task IDs.
- [Structured plan](tasks.json): the same task scopes, acceptance criteria and dependencies, with Aftur IDs.
- [Import receipt](aftur-import.json): readback summary from the scoped MCP interface.

Open `/Users/nirtuttnauer/Documents/Code/MossCMS/ProjectMemory/MossCMS` in Aftur. **More → PRDs & plans** shows the imported PRD and linked proposals. **Tasks** shows the individual tickets. All tasks were proposed for review; no implementation was started or approved by the agent.

The plan distinguishes existing capabilities from proposed next-release work. P3 schema tools are optional. Milestone and priority labels are recorded in each ticket's description because Aftur's current agent proposal interface does not expose those fields separately.

Readback exposed an Aftur import limitation: `propose_task` accepts `acceptance_criteria`, but its bridge currently omits that argument when creating the task. Criteria were therefore saved and verified as attributed notes on each ticket, available in discussion and agent context, as well as in the Markdown/JSON plan. The native acceptance-criteria field remains empty. No approval or storage-authority checks were bypassed to work around this.

Aftur's canonical `project.json` is managed through its app and scoped MCP server. Do not hand-edit it. Its index and lock files are disposable and excluded from source control. Keep the project files together when moving or backing them up, with no writer active.

For later agent work, discover and call tools using Aftur's repository helper:

```sh
/Users/nirtuttnauer/Documents/Code/MossCMS/api/.venv/bin/python \
  /Users/nirtuttnauer/Documents/Code/Aftur/Scripts/aftur_mcp.py list \
  --project /Users/nirtuttnauer/Documents/Code/MossCMS/ProjectMemory/MossCMS
```

Tool arguments are JSON on stdin. Read fresh task context before executing approved work and record progress/evidence through Aftur. Changes to the PRD should be reviewed and reimported with explicit provenance; do not silently replace a prior specification or duplicate proposals. The receipt describes the initial import, not ongoing execution status.
