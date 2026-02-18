# CLAUDE.MD — MDEMG Agent Contract

> **Purpose:** single authoritative contract for interacting with MDEMG.
> The file is the agent's rulebook: CMS first, Plan Mode for architecture, strict execution rules for safety.

---

## ⚠️ MANDATORY: Use CMS (Conversation Memory System)

**FAILURE TO USE CMS = CONTEXT LOSS EVERY 20–30 MINUTES.**
Treat CMS as an identity service. If CMS is unavailable, act conservatively and **do not** make irreversible changes without explicit user confirmation.

### First action on every session — resume memory (MUST)

Run immediately at session start (hooks or MCP bridge should run automatically):

```bash
curl -s -X POST http://localhost:9999/v1/conversation/resume \
  -H "Content-Type: application/json" \
  -d '{"space_id":"mdemg-dev","session_id":"claude-core","max_observations":10}'
```

* If resume returns observations → ACK with a **one-line summary** before any new reasoning.
* If CMS unreachable → announce: **`CMS unavailable — memory disconnected`** and require explicit confirmation for irreversible actions.
* If resume returns 0 observations but the space has data → create an anomaly observation and trigger RSIC micro assessment.

---

## DURING SESSION — Observe only high-signal events (MANDATORY)

Call `/v1/conversation/observe` **silently** for **high-signal** items only. Do NOT store chain-of-thought or transient silly stuff.

**Allowed obs_types:**

* `decision` — architectural / irreversible choices (persist only when locked/approved)
* `correction` — explicit user corrections or rejections
* `preference` — user style/tool preferences
* `learning` — durable new domain conventions or constraints
* `error` / `blocker` — test/build failures, unresolved blockers
* `progress` — milestone / successful builds (use sparingly)

**Observe example (decision):**

```bash
curl -s -X POST http://localhost:9999/v1/conversation/observe \
  -H "Content-Type: application/json" \
  -d '{
    "space_id":"mdemg-dev",
    "session_id":"claude-core",
    "content":"Decision: adopt event-driven architecture for ingestion pipeline due to O(N) polling cost",
    "obs_type":"decision"
  }'
```

**Rules**

* Observe silently (no announcements like “I stored X” unless user requests).
* Never dump CMS contents into the working prompt; only recall the minimal necessary items.
* Only explicitly observed items become durable memory.
* Novelty (surprise) makes observations persist longer; co-activation reinforces them.

---

## PROTECTED SPACE

* `mdemg-dev` is protected. The API and tools refuse destructive operations on this space. Do not attempt to bypass protections.

---

## HOOKS & ENFORCEMENT (they are enforced)

These hooks are active and non-optional:

* `session-start.sh` — runs resume, prints short summary, triggers anomaly checks.
* `pre-compact.sh` — snapshots current session into CMS before compaction.
* `pre-bash-check.*` — blocks destructive shell commands until explicit confirmation.
* `post-tool-observe.py` — auto-captures tool results and important edits (configurable).

Do not remove or disable hooks without documented, org-approved exception.

---

## RSIC — Recursive Self-Improvement Cycle (summary)

CMS runs autonomous maintenance cycles:

* **Micro:** per-session quick health checks
* **Meso:** every 6h or N sessions — edge & retrieval remediation
* **Macro:** daily — topology + hidden layer reconsolidation

Actions include: prune decayed edges, trigger consolidation, graduate volatiles, tombstone stale low-value observations. If RSIC reports degradation, follow the investigation checklist surfaced by hooks.

---

## PLAN MODE — SENIOR ENGINEER REVIEW (YC-style super-prompt)

**Plan Mode is mandatory and must be invoked explicitly before any code changes** (activation: `@plan`, `@plan-mode`, or UI button). No code changes during Plan Mode.

### Activation / Behavior

* On activation: **do not modify files**; produce only analysis and recommendations.
* Follow stages in order: **Architecture → Code Quality → Tests → Performance**.
* For every issue: provide file:line evidence where possible, 2–3 options, trade-offs, and recommend one. **Pause for approval**.
* Only after explicit user approval persist a recommendation as an `obs_type:"decision"`.

### YC-style Plan Mode Super-Prompt (drop into agent system prompt)

Use this exact block to force repeated review loops and rigorous decisions. Make the agent **repeat until approval**.

```
PLAN MODE — SENIOR ENGINEER (YC PROMPT)
You are now in Plan Mode. This is an analysis-only mode. DO NOT write or modify code.
Follow these stages in strict order: Architecture → Code Quality → Tests → Performance.
For each stage:
  1) Identify the top 3 issues (if any). For each issue include exact file:line evidence.
  2) For each issue, present 2–3 concrete options. Each option must include:
     - Implementation steps (bullet list)
     - Estimated effort (S/M/L: hours)
     - Risk (brief)
     - Maintenance cost (low/medium/high)
  3) For each issue, recommend exactly one option and say why (one short sentence).
  4) For each recommendation, show the exact command(s) or patch snippet required to implement it.
  5) STOP and ask: "Approve recommendation X? (yes/no)". Wait for explicit user approval before proceeding to Execution Mode.
Additional rules:
  - If the analysis requires recalling prior decisions, call MEMORY.recall(query) first and include the relevant observation IDs in evidence.
  - When you propose an irreversible action, explicitly verify with the user (no defaults).
  - Do not perform any changes without the user's “yes” approval for that specific recommendation.
  - If asked to re-run Plan Mode, incorporate new CMS observations since last run.
  - Summarize the final plan in 4 lines: (what, why, risk, next step).
End Plan Mode only when user approves a recommendation or explicitly cancels.
```

**Enforcement:** the agent must call CMS `recall` at the start of Plan Mode and before final recommendation if there are prior decisions related to the same scope.

---

## PLAN MODE → CMS BRIDGE (persisting decisions)

After the user approves a Plan Mode recommendation, persist it:

```bash
curl -s -X POST http://localhost:9999/v1/conversation/observe \
  -H "Content-Type: application/json" \
  -d '{"space_id":"mdemg-dev","session_id":"claude-core","content":"<Concise decision text>","obs_type":"decision"}'
```

*Do not persist rejected alternatives unless the user explicitly requests saving them as `learning`.*

When re-litigated later, call `/v1/conversation/recall` to fetch the observed decision rather than re-arguing.

---

## EXECUTION MODE — rules & handoff

Enter Execution Mode **only after** explicit approval of Plan Mode recommendations.

Execution Mode rules:

* Implement only the approved changes.
* Do not introduce new abstractions without returning to Plan Mode.
* Persist new locked decisions immediately to CMS.
* Respect pre-bash destructive checks. Any destructive operation must require explicit, inline confirmation.
* Run long-running tasks in foreground and stream output to the user.

---

## SKILL REGISTRY (CMS-backed)

* Skills are pinned observations. Thin skill files in `.claude/skills/` are pointers that call CMS to recall content.
* Recall a skill:

```bash
curl -s -X POST http://localhost:9999/v1/skills/<name>/recall \
  -H "Content-Type: application/json" \
  -d '{"space_id":"mdemg-dev"}'
```

Pinned observations start permanent (stability=1.0). Without CMS, skills are unavailable.

---

## TOOL USAGE: automatic recall triggers (make agent choose memory)

The agent should automatically call `memory.recall(...)` when any of these occur in user input or internal reasoning:

**Trigger words / contexts**

* Architecture changes: `refactor`, `redesign`, `re-architect`, `restructure`
* Irreversible operations: `drop`, `truncate`, `reset`, `migrate`, `destroy`
* Preference-sensitive choices: `style`, `formatting`, `convention`, `preference`
* High uncertainty / re-check: `not sure`, `I think`, `maybe`, `do we`
* Cross-file edits or multi-module changes

**Tool schema (short guidance for MCP tool definitions)**

* `memory.recall({"space_id":"mdemg-dev","query":"...","top_k":N})` → returns observations + evidence (file:line)
* `memory.observe({"space_id":"mdemg-dev","session_id":"...","content":"...","obs_type":"..."})` → returns obs_id
* `memory.consolidate({"space_id":"mdemg-dev"})` → trigger hidden layer creation

Agents should prefer recall **before** they finalize recommendations or take destructive actions.

---

## API QUICK REFERENCE (important endpoints)

* Resume: `POST /v1/conversation/resume`
* Observe: `POST /v1/conversation/observe`
* Recall: `POST /v1/conversation/recall`
* Consolidate: `POST /v1/conversation/consolidate`
* Graduate: `POST /v1/conversation/graduate`
* Session health: `GET /v1/conversation/session/health`
* Self-improve assess: `POST /v1/self-improve/assess`
* Skill recall: `POST /v1/skills/{name}/recall`

(Expose only CMS tools to agents; do not expose admin or ingestion endpoints.)

---

## DESTRUCTIVE-OPERATION BLOCKLIST (automatic pre-check)

Before running any shell/db command, run pre-checks. Block and require explicit approval for:

* DB destructive statements (DROP, TRUNCATE, full database restores)
* `rm -rf` patterns and forced recursive deletes
* Git history rewrites (`git push --force`, `git reset --hard` on main)
* Bulk node deletions in the graph

If a command matches the blocklist → refuse until user explicitly permits with exact confirmation text.

---

## SNAPSHOTS & PRE-COMPACTION

* `pre-compact.sh` will snapshot active session state to CMS before compaction.
* Use snapshots to capture active files, blockers, and next steps. Snapshots must be small and focused (task context, not whole repo).

---

## MEMORY SIGNALS & ANOMALIES

* Hooks will surface anomalies (e.g., empty resume when space has nodes).
* If an anomaly occurs, follow the hook checklist and trigger RSIC micro assessment.
* Record anomalies as `error` observations.

---

## QUALITY RULES — WHAT NOT TO STORE

* Do NOT store chain-of-thought, token dumps, or transcript fragments as `decision`.
* Do NOT store speculative brainstorming as durable `decision`.
* Use `learning` for general knowledge and `progress` for milestones (sparingly).
* Only store things you’d want verbatim in a future session.

---

## CONFIG & TUNING (examples)

Tune system behavior through env/config:

```bash
CMS_RESUME_MAX_TOKENS=4000
CMS_RELEVANCE_WEIGHT_RECENCY=0.3
CMS_RELEVANCE_WEIGHT_IMPORTANCE=0.4
CMS_RELEVANCE_WEIGHT_TASK_RELEVANCE=0.3

STABILITY_INCREASE_PER_REINFORCEMENT=0.15
STABILITY_DECAY_RATE=0.1
TOMBSTONE_THRESHOLD=0.05
GRADUATION_STABILITY_THRESHOLD=0.8
```

Keep RSIC safety bounds conservative for production.

---

## VS CODE MCP HINT (how to wire agent → MDEMG)

Use the MCP stdio bridge (bin/mdemg-mcp). Example workspace config:

`.vscode/mcp.json`

```json
{
  "servers": {
    "mdemg": {
      "command": "/home/<user>/mdemg/bin/mdemg-mcp",
      "args": [],
      "env": {
        "MDEMG_ENDPOINT": "http://localhost:9999"
      }
    }
  }
}
```

**Note:** Pointing directly to `http://localhost:9999` as an HTTP MCP server will cause SSE/404 fallbacks; spawn the MCP bridge binary over stdio.

---

## GIT WORKFLOW & ORCHESTRATION (project defaults)

* Development branch: `mdemg-dev01`. Never commit directly to `main`. Use conventional commits.
* Use sub-agents for discrete tasks; orchestrator coordinates.
* Model selection guide: `haiku` for simple tasks, `sonnet` for analysis/tests, `opus` for architecture decisions.

---

## BENCHMARKS & INGESTION (operator notes)

Full ingestion/consolidation is heavy; do not run in interactive sessions unless benchmarking. Use `/v1/memory/ingest-codebase` + consolidation for large scale indexing.

---

## FINAL: Golden Rules (read before acting)

1. **CMS first** — resume on start, observe only high-signal events.
2. **Plan Mode second** — analyze like a staff engineer before code. Pause. Get approval. Lock decisions.
3. **Execution third** — implement only approved decisions and persist locks.

This file is the authoritative contract. Changes must be documented, reviewed, and tested. If you extend behavior, add tests and update Plan Mode + hook expectations.

---
