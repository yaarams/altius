# Execution Governance

## Orchestration Version
orchestration_version: 2.5.0

## Plan Reference
20-00_PLANNING_v2.1.md — DoR verified: Yes (all mandatory + Complex-tier items checked; CONF-2/CONF-3 resolved)

## Complexity Tier
Complex (from plan)

## Mode
New System (greenfield build at /Users/yaaracohen/Development/altius)

## Execution Budget
### Time
- Maximum: ~6 h autonomous; user check-in on demand
### Tokens (orchestrator context)
- Soft: ~100k → refresh resume prompt. Hard: ~140k → stop + resume.
### Agents
- Max parallel: 4. Specialists: Dev Engineer, Test Engineer, QA, Code Reviewer, Learning Analyst.

## Escalation Conditions
- Crawler cannot authenticate to fo1.altius.finance after retry → STOP, escalate (blocks all).
- Gemini API key invalid / quota → escalate.
- Any need to commit/push or send data externally → confirm with user first.
- Scope change beyond plan v2.1 → escalate.

## Change Policy
- Breaking changes: N/A (greenfield).
- Refactoring scope: full freedom within /Users/yaaracohen/Development/altius.
- Secrets: env-only, never logged, never committed (.gitignore enforced).

## Technical Debt Policy
- Allowed shortcuts: visual polish minimal (not graded); test coverage focus on 19 correctness properties over raw %.
- Required quality: idempotency + extraction correctness + RAG grounding are non-negotiable.

## Environment Adaptations
- SharedKnowledge (C:\Projects\SharedKnowledge) absent on this macOS host → SK Scout skipped; no team patterns/lessons/standards to load. Noted, not a blocker.
- Project not a git repo → orchestrator will `git init` for rollback support (per plan rollback strategy). No remote; no push without user consent.

## Approval
Proceed — auto-approved (Complex tier, DoR complete, user approved plan v2.1 + triggered orchestration).
- Approved at: 2026-06-24
