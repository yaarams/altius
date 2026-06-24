---
name: my-orchestration-master
description: Use when executing complex dev plans (3+ steps) autonomously. Triggers: "orca", "master flow", "work autonomously", "god mode", "YOLO mode", "execute the plan", "build this while I sleep", plan MD files, multi-repo coordination.
orchestration_version: "2.5.0"
compatibility:
  claude_code: ">=2.1"
  tools: [git, pytest, docker, npm]
---

# Orchestration Master v2.5 - Autonomous Multi-Agent Development Execution

## Overview

**Core Principle:** Transform implementation plans into production-ready code through coordinated multi-agent execution with continuous documentation, error recovery, and context management.

This is NOT just "execute a plan" - this is **industrial-grade autonomous development** with:
- Definition of Ready verification (formal handoff gate from planner)
- Slim governance (budget + escalation, not scope re-statement)
- Pattern reuse (institutional knowledge)
- Continuous journal trail (never lose context)
- Multi-agent coordination with checkpointing
- Context compression (prevent context rot)
- Saga pattern error recovery (compensation logic)
- UX/style validation (consistent product identity)
- Traceability verification (PRD → task → test → verified)
- Learning loop (post-mortems that improve future runs)
- ADR promotion (decisions → SharedKnowledge/decisions/)
- Verification at every stage
- Versioned deliverables (implementation summaries with version control)
- **Session continuity protocol (proactive resume prompt generation before context exhaustion)**

**Operates in three modes:**
1. **New System Mode** - Build from scratch (repos, architecture, full stack)
2. **Feature Integration Mode** - Modify existing codebase (add features, refactor, integrate)
3. **Fast Track Mode** - Small features with lightweight governance (< 2 hours)

Mode is **auto-detected** from plan content and scope.

---

## Relationship with Planning Master

```
┌────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT PIPELINE                     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  /my-research-master            →  00-00_PRD*.md + 10-00_RESEARCH*.md   │
│       ↓                                                    │
│  /my-planning-master     →  20-00_PLANNING_v{X.Y}.md          │
│       ↓                                                    │
│  /my-orchestration-master (THIS SKILL)                     │
│       → Receives plan from planner                         │
│       → Creates 30-05___GOVERNANCE.md (formal execution boundaries)│
│       → Executes across phases 0-5                         │
│       → Outputs 30-00_IMPLEMENTATION-SUMMARY_v{X.Y}.md        │
│       → Plus all execution deliverables                    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**The planning master handles iterative planning with the user.** By the time a plan reaches this skill, it should be concrete, with file-level specificity, architecture decisions made, and scope aligned. This skill validates and EXECUTES that plan.

**If no plan from `/my-planning-master` exists:**
- The orchestrator can still accept raw plans (backward compatible)
- Phase 0 will do heavier validation
- Phase 1 will do more planning work
- But the preferred flow is: Planner → Orchestrator

---

## SharedKnowledge Repository

**Location:** `C:\Projects\SharedKnowledge\`

This is the **team's institutional memory**. All orchestration runs reference it.

```
C:\Projects\SharedKnowledge\
├── patterns/                    # Reusable technical solutions
│   ├── ui/                      # UI component patterns
│   ├── backend/                 # API, auth, DB patterns
│   └── integration/             # Third-party integration patterns
├── lessons/                     # Post-mortem learnings
│   ├── INDEX.md                 # Searchable lesson index
│   └── YYMMDD_<task>_lessons.md # Individual lessons
├── decisions/                   # Architecture Decision Records (ADRs)
│   ├── INDEX.md                 # Searchable ADR index
│   └── YYMMDD_ADR-NNN_title.md  # Individual ADRs (promoted from plans)
├── standards/                   # Team-wide standards
│   ├── CODING_PREFERENCES.md    # Coding standards (team version)
│   ├── UX_STYLE_PROFILE.md      # Visual/interaction standards
│   ├── GIT_WORKFLOW.md          # Branch, commit, PR standards
│   └── TESTING_STANDARDS.md     # Test requirements
├── guides/                      # Reference guides & best practices
│   └── claude-code-elite-guide.md # Example: Claude Code usage guide
├── runbooks/                    # Operational procedures
│   └── *.md                     # Deployment, rollback, maintenance procedures
├── governance/                  # Templates
│   ├── GOVERNANCE_TEMPLATE.md   # Full governance template
│   ├── FEATURE_BRIEF_TEMPLATE.md # Lightweight governance
│   └── examples/                # Real examples for reference
└── orchestration/               # This skill + history
    ├── CHANGELOG.md             # Version history
    └── COMPATIBILITY.md         # Tool compatibility
```

### How to Use SharedKnowledge

**All SK reads use the `sk-scout` agent definition:** Dispatch via `Agent` tool with `subagent_type: "sk-scout"`. The agent is haiku, read-only, scans all SK folders, and returns a concise summary (max 30 lines). This protects the main orchestration context from content bloat.

**Before Execution (Phase -1 / Phase 0):**
1. Check `patterns/` for existing solutions
2. Check `lessons/` for past mistakes to avoid
3. Check `decisions/` for prior ADRs that constrain architecture
4. Check `standards/` for team rules to follow
5. Check `guides/` for reference material relevant to the feature domain
6. Check `runbooks/` for operational procedures that constrain implementation

**After Execution (Phase 5):**
1. Write lessons learned to `lessons/`
2. Create new patterns if novel solutions were developed
3. Update standards if new rules discovered
4. Promote ADRs to `decisions/` (if plan marks them for promotion)
5. Create/update `runbooks/` if new operational procedures were established
6. Reference relevant `guides/` in lessons if they informed execution

**Best Practices:**
- **Pattern reuse > redesign** - Always check patterns first
- **Learn from others** - Read lessons before similar tasks
- **Respect prior decisions** - Check ADRs before making new architecture choices
- **Contribute back** - Every run should add knowledge
- **Index everything** - Update INDEX.md for searchability
- **Version patterns** - Note which patterns are deprecated

---

## When to Use

**Use when:**
- Plan has 3+ major implementation steps
- User expects autonomous work (2+ hours)
- User says "work autonomously", "god mode", "YOLO mode"
- Given a plan `.md` file to execute (ideally `20-00_PLANNING_v*.md` from `/my-planning-master`)
- User is offline/sleeping and expects progress in morning
- Multi-repo coordination required
- Complex integration across systems
- Team alignment needed (governance documents)

**Use Fast Track Mode when:**
- Plan has 1-3 steps
- Estimated time < 2 hours
- Low risk (no breaking changes)
- Clear, well-scoped feature

**Don't use when:**
- Single trivial task (< 30 min)
- User wants step-by-step approval
- Exploratory research (no concrete plan) → use `/my-research-master`
- Need to create the plan first → use `/my-planning-master`
- Just reading code or answering questions

---

## The Iron Laws

```
1.  JOURNAL EVERY DECISION - No silent changes allowed
2.  CHECKPOINT BEFORE PHASES - Context exhaustion must be recoverable
3.  SPAWN SUB-AGENTS AGGRESSIVELY - Never do serial work that could be parallel
4.  TEST BEFORE CLAIMING DONE - No "it should work" - verify with actual execution
5.  ORCHESTRATOR READS ZERO SOURCE CODE - Only orchestration artifacts (journal, plan, governance). Sub-agents read their own files.
6.  ASK CLARIFYING QUESTIONS ONLY IF PLAN IS UNCLEAR - Don't use questions as excuse to delay
7.  REUSE PATTERNS BEFORE REDESIGNING - Check SharedKnowledge first
8.  WRITE LESSONS AFTER EVERY RUN - Feed the learning loop
9.  VALIDATE STYLE CONSISTENCY - UX must match existing product
10. RESPECT GOVERNANCE BOUNDARIES - Never exceed approved scope
11. VERSION ALL DELIVERABLES - Implementation summaries are versioned like plans
12. GENERATE RESUME PROMPT BEFORE CONTEXT DEATH - Session continuity is non-negotiable
13. RIGHT-SIZE THE MODEL - Default sub-agents to sonnet. Use haiku for trivial tasks. Reserve opus for genuinely hard reasoning.
14. SUB-AGENTS RETURN STRUCTURED SUMMARIES - Max 40 lines. Never echo file contents back to orchestrator.
```

**Violating any Iron Law = Stop and restart correctly.**

---

## Journal Header Format

**Every journal entry MUST use this header format:**

```
### [YYYY-MM-DD HH:MM {elapsed}] {ctx:XX%} Phase Name
```

**Components:**
- **`YYYY-MM-DD HH:MM`** — Current wall-clock time (actual time, not relative)
- **`{elapsed}`** — Time elapsed since orchestration started, in `{HH:MM}` format (e.g., `{00:00}` at start, `{01:23}` after 1 hour 23 minutes)
- **`{ctx:XX%}`** — Current context window usage percentage, zero-padded (e.g., `{ctx:08%}`)

**Example progression:**
```markdown
### [2026-02-16 21:14 {00:00}] {ctx:08%} Phase -1: Strategic Governance
### [2026-02-16 21:18 {00:04}] {ctx:14%} Phase 0: Plan Validation
### [2026-02-16 21:25 {00:11}] {ctx:22%} Phase 1: Execution Configuration
### [2026-02-16 21:52 {00:38}] {ctx:41%} Phase 2: Implementation — Group A Complete
### [2026-02-16 22:30 {01:16}] {ctx:55%} Phase 3: Testing & QA
### [2026-02-16 22:45 {01:31}] {ctx:58%} ERROR RECOVERY
### [2026-02-16 23:10 {01:56}] {ctx:72%} Session Continuity: Resume Prompt Generated
```

**Tracking rules:**
- Record the orchestration start time when creating the first journal entry (Phase -1)
- Elapsed time is calculated from that start time for every subsequent entry
- Context percentage: estimate from conversation length or use `/context` command if available
- Both elapsed time AND context% are mandatory on every journal header — no exceptions

---

## CRITICAL: How This Skill Works

**This skill is invoked by YOU (the orchestrator), not sub-agents.**

**Workflow:**
1. **User gives you a plan** → You load this skill
2. **You follow the phases** → Create journal, spawn sub-agents, track progress
3. **Sub-agents execute tasks** → They DON'T need this skill, they get task-specific instructions
4. **You aggregate results** → Compile sub-agent outputs into journal
5. **You create versioned deliverables** → `30-00_IMPLEMENTATION-SUMMARY_v{X.Y}.md` + all others

**DO NOT:**
- ❌ Try to pass this skill to sub-agents
- ❌ Expect sub-agents to use orchestration patterns
- ❌ Create "orchestrator sub-agents" (YOU are the orchestrator)
- ❌ Skip version control on deliverables

**YOU are the master orchestrator. Sub-agents are workers. This skill guides YOU.**

---

## Project Structure

All orchestration docs live in:
```
<project_root>/docs/master/YYMMDD_HHMMSS_<short_task>/
├── 00-00_PRD_<feature>.md                  # Input: Product Requirements (from research or user)
├── 10-00_RESEARCH.md                       # Input: Research findings (from /my-research-master)
├── 20-00_PLANNING_v{X.Y}.md               # Input: Implementation plan (from /my-planning-master)
├── 30-00_IMPLEMENTATION-SUMMARY_v{X.Y}.md  # Output: Versioned execution summary (THIS SKILL)
├── 30-05___GOVERNANCE.md                        # Phase -1: Strategic boundaries
├── 30-10___JOURNAL_<short_task>.md              # Continuous append-only log
├── 30-15___CONTEXT-SNAPSHOT.json                # Lightweight state for recovery
├── 30-20___CHECKPOINT-BARRIER_<phase>.json      # Coordinated checkpoints
├── 30-25___UX-VALIDATION_<short_task>.md        # Phase 4: Style consistency report
├── 30-30___TECH-DEBT_<short_task>.md            # Known issues
├── 30-35___LESSONS-LEARNED_<short_task>.md      # Phase 5: Post-mortem
├── 30-40___JOURNAL-ARCHIVE_<timestamp>.md       # Old journal entries (compressed)
└── 30-99___RESUME_PROMPT.md                     # Session continuity: copy-paste to new session
```

**Example:**
```
docs/master/260201_1430_TaskAPI/
├── 00-00_PRD_task-api.md
├── 10-00_RESEARCH.md
├── 20-00_PLANNING_v2.0.md
├── 30-00_IMPLEMENTATION-SUMMARY_v1.0.md
├── 30-05___GOVERNANCE.md
├── 30-10___JOURNAL_TaskAPI.md
├── 30-15___CONTEXT-SNAPSHOT.json
├── 30-20___CHECKPOINT-BARRIER_Governance.json
├── 30-20___CHECKPOINT-BARRIER_Planning.json
├── 30-20___CHECKPOINT-BARRIER_Implementation.json
├── 30-20___CHECKPOINT-BARRIER_Testing.json
├── 30-25___UX-VALIDATION_TaskAPI.md
├── 30-30___TECH-DEBT_TaskAPI.md
├── 30-35___LESSONS-LEARNED_TaskAPI.md
└── 30-99___RESUME_PROMPT.md
```

---

## Versioned Deliverables

### Implementation Summary Version Control

The primary execution output is versioned:

```
30-00_IMPLEMENTATION-SUMMARY_v{major}.{minor}.md
```

**Version Rules:**

| Scenario | Version Change | Example |
|----------|---------------|---------|
| First execution of a plan | v1.0 | 30-00_IMPLEMENTATION-SUMMARY_v1.0.md |
| Re-execution (bug fixes, missed items) | Increment minor | v1.0 → v1.1 |
| Execution of updated plan (new planning version) | Increment major | v1.1 → v2.0 |
| User explicitly requests major bump | Increment major | v1.3 → v2.0 |

**Relationship to Planning Versions:**

```
20-00_PLANNING_v1.0.md  →  30-00_IMPLEMENTATION-SUMMARY_v1.0.md  (first execution)
20-00_PLANNING_v1.0.md  →  30-00_IMPLEMENTATION-SUMMARY_v1.1.md  (re-execution, fixes)
20-00_PLANNING_v2.0.md  →  30-00_IMPLEMENTATION-SUMMARY_v2.0.md  (new plan version)
```

**When re-executing:**
1. Detect existing `30-00_IMPLEMENTATION-SUMMARY_v*.md` in feature folder
2. Identify latest version
3. Determine increment (minor = same plan, major = new plan version)
4. Confirm with user
5. Create new version (previous NOT overwritten)
6. Mark previous as "Superseded by v{X.Y}"

### All Versioned Files

| File | Versioning | Owner |
|------|-----------|-------|
| `20-00_PLANNING_v{X.Y}.md` | Managed by `/my-planning-master` | Planner |
| `30-00_IMPLEMENTATION-SUMMARY_v{X.Y}.md` | Managed by this skill | Orchestrator |

### Non-Versioned Files (Append-Only or One-Per-Run)

| File | Strategy |
|------|----------|
| `30-05___GOVERNANCE.md` | One per execution run (overwritten if re-run) |
| `30-10___JOURNAL_*.md` | Append-only, never overwritten |
| `30-20___CHECKPOINT-BARRIER_*.json` | One per phase per run |
| `30-30___TECH-DEBT_*.md` | Latest version reflects current state |
| `30-35___LESSONS-LEARNED_*.md` | One per execution run |
| `30-25___UX-VALIDATION_*.md` | One per execution run |

---

## Execution Workflow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATION MASTER v2.3                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │  Receive Plan   │  ← 20-00_PLANNING_v{X.Y}.md (from /my-planning-master)   │
│  └────────┬────────┘    or raw plan file (backward compatible)              │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE -1: STRATEGIC GOVERNANCE                                       │   │
│  │ • Build on planner's scope alignment                                │   │
│  │ • Define formal execution boundaries                                │   │
│  │ • Set resource budget (time, tokens, agents)                        │   │
│  │ • Determine risk tolerance                                          │   │
│  │ • Output: 30-05___GOVERNANCE.md                                              │   │
│  └────────┬────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 0: PLAN VALIDATION                                             │   │
│  │ • Validate plan is actionable and complete                          │   │
│  │ • Check SharedKnowledge for patterns/lessons                        │   │
│  │ • Auto-detect mode (New System / Feature / Fast Track)              │   │
│  │ • Load coding preferences and standards                             │   │
│  │ • Determine implementation summary version                          │   │
│  └────────┬────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 1: OPERATIONAL TASK BREAKDOWN                                  │   │
│  │ • Convert plan into executable task groups                          │   │
│  │ • Map dependencies and parallel opportunities                       │   │
│  │ • Assign patterns to tasks                                          │   │
│  │ • Output: 30-20___CHECKPOINT-BARRIER_Planning.json                          │   │
│  └────────┬────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 2: PARALLEL IMPLEMENTATION                                     │   │
│  │ • Spawn sub-agents for each parallel group                          │   │
│  │ • Apply patterns from SharedKnowledge                               │   │
│  │ • Log compensation (undo) for each change                           │   │
│  │ • Output: 30-20___CHECKPOINT-BARRIER_Implementation.json                    │   │
│  └────────┬────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 3: TESTING & QA                                                │   │
│  │ • Run tests (verify output, don't assume)                           │   │
│  │ • Bug hunting (find ≥3 real issues)                                 │   │
│  │ • Edge case testing                                                 │   │
│  │ • Output: 30-20___CHECKPOINT-BARRIER_Testing.json                           │   │
│  └────────┬────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 4: REVIEW & AUDIT                                              │   │
│  │ • Code quality review                                                │   │
│  │ • Plan compliance check                                              │   │
│  │ • UX/Style validation (spawn UX Integrator sub-agent)               │   │
│  │ • Output: 30-25___UX-VALIDATION_<task>.md                                    │   │
│  └────────┬────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 5: POST-MORTEM (LEARNING LOOP)                                 │   │
│  │ • What worked well?                                                  │   │
│  │ • What failed?                                                       │   │
│  │ • New rules to add?                                                  │   │
│  │ • Patterns to create?                                                │   │
│  │ • Output: 30-35___LESSONS-LEARNED_<task>.md                                  │   │
│  │ • Copy to: SharedKnowledge/lessons/                                  │   │
│  └────────┬────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────────┐                                                   │
│  │     DELIVERABLES     │                                                   │
│  │ • 30_IMPL_SUMM_v*.md │                                                   │
│  │ • TECH_DEBT.md       │                                                   │
│  │ • Arch docs          │                                                   │
│  └──────────────────────┘                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase -1: Strategic Governance (PRE-EXECUTION ALIGNMENT)

**Purpose:** Transform the planning master's scope alignment into formal operational boundaries. Prevent misaligned effort and scope creep during execution.

**Philosophy:** Governance is intent formalization, not bureaucracy. The planner aligned on WHAT to build. Governance aligns on HOW to execute safely.

### When to Execute Phase -1

**Full Governance (this phase) when:**
- High-risk changes (breaking changes, API modifications)
- Multi-day effort expected
- Multiple team members involved
- Business-critical feature
- New system development

**Lightweight Governance (Fast Track) when:**
- Low-risk, well-scoped feature
- < 2 hours estimated
- Single contributor
- Non-breaking changes

### Governance Depends on Plan Source

**If plan has DoR (from `/my-planning-master` v1.1+):**

Governance is SLIM. The planner already owns scope, risk, and architecture decisions. Governance ONLY adds execution-specific boundaries. Use the **Slim Governance Template** below.

**If plan is raw (no planner, no DoR):**

Governance is FULL. The orchestrator must establish scope and boundaries from scratch. Use the **Full Governance Template** below. Also ask the user:

1. **Who is this feature for?** (target users)
2. **What problem does it solve?** (business objective)
3. **What outcome is expected?** (success criteria)
4. **How risky is this?** (can it break existing behavior?)
5. **How much effort is acceptable?** (time/token budget)
6. **Can existing behavior change?** (breaking changes allowed?)

### Slim Governance Template (Planner-First Workflow)

**Use when:** Plan has a completed DoR checklist from `/my-planning-master`.

**Location:** `<project_root>/docs/master/<timestamp>_<task>/30-05___GOVERNANCE.md`

```markdown
# Execution Governance

## Orchestration Version
orchestration_version: 2.4.0

## Plan Reference
20-00_PLANNING_v{X.Y}.md - DoR verified: Yes

## Complexity Tier
[Quick / Standard / Complex] (from plan)

## Execution Budget
### Time
- Maximum: [e.g., 4 hours]
- User check-in expected: [e.g., Tomorrow 9 AM]

### Tokens
- Soft limit: [e.g., 200k tokens (1M model) / 100k (200k model)]
- Hard limit: [e.g., 300k tokens (1M model) / 140k (200k model), then STOP]

### Agents
- Maximum parallel: [e.g., 6]
- Specialists allowed: [e.g., Test Eng, QA, UX Integrator]

## Escalation Conditions
- [When to stop and ask user]
- [Blockers that require human decision]
- Rollback trigger: [from plan's Orchestrator Execution Config]

## Change Policy
- Breaking changes: [Yes / No]
- Refactoring scope: [from plan constraints]

## Technical Debt Policy
- Allowed shortcuts: [e.g., Skip i18n for v1]
- Required quality: [e.g., 80% test coverage minimum]

## Approval
[Proceed / Downgrade tier / Replan / Escalate]
- Approved at: [timestamp]
- Auto-approved: [Yes if Quick tier / No - user confirmed]
```

**Note:** Scope, risk, architecture, and business objective are NOT restated here — they live in the plan. Governance references the plan, not duplicates it.

### Full Governance Template (No Planner)

**Use when:** Plan is raw, has no DoR, or came from outside the pipeline.

**Location:** `<project_root>/docs/master/<timestamp>_<task>/30-05___GOVERNANCE.md`

```markdown
# Strategic Governance Assessment

## Orchestration Version
orchestration_version: 2.4.0

## Plan Reference
[Path to raw plan file]

## Business Objective
[Primary business or product problem addressed]

## Expected Impact
[Observable improvement after deployment]

## Target Users
[Who benefits from this feature]

## Scope Boundaries
### In Scope
- [Explicit functional items]
- [Technical components to modify]

### Out of Scope
- [What we will NOT do]
- [Features deferred to future]

## Risk Assessment
### Risk Level: [Low / Medium / High / Critical]

### Risk Tolerance
- Acceptable failure rate: [e.g., < 1% error rate]
- Acceptable regression: [e.g., No existing tests may break]

## Technical Debt Policy
- Allowed shortcuts: [e.g., Skip i18n for v1]
- Required quality: [e.g., 80% test coverage minimum]

## Resource Budget
### Time Limit
- Maximum execution: [e.g., 4 hours]
- User check-in expected: [e.g., Tomorrow 9 AM]

### Token Budget
- Soft limit: [e.g., 200k tokens (1M model) / 100k (200k model)]
- Hard limit: [e.g., 300k tokens (1M model) / 140k (200k model), then STOP]

### Agent Allocation
- Maximum parallel agents: [e.g., 6]
- Specialist agents allowed: [e.g., Test Eng, QA, UX Integrator]

## Change Policy
### Breaking Changes: [Yes / No]
- If yes, migration path: [Required / Optional / N/A]

### Refactoring Scope
- [Files/modules allowed to refactor]

### API Stability
- [Backward compatibility requirements]

## Exit Criteria
[Objective completion definition - what "done" looks like]

## Escalation Conditions
- [When to stop and ask user]
- [Blockers that require human decision]

## Approval Decision
[Proceed / Downgrade to Fast Track / Replan / Escalate to User]

## Governance Approved By
- Timestamp: [YYYY-MM-DD HH:MM]
- Approver: [User / Auto-approved based on plan clarity]
```

### Enforcement

- **Execution cannot proceed without governance approval**
- **Constraints override lower-level decisions** (if governance says "no breaking changes", Phase 2 cannot introduce them)
- **Budget exceeded = STOP and escalate** (don't continue past token/time limits)

### Journal Entry (Phase -1):

```markdown
### [YYYY-MM-DD HH:MM {00:00}] {ctx:XX%} Phase -1: Strategic Governance

Governance Type: Full Governance (high-risk feature)
Plan Source: 20-00_PLANNING_v2.0.md (from /my-planning-master)

Business Objective: Reduce export support requests by enabling self-service

Scope (from plan):
- IN: Export dialog, markdown formatter, hamburger menu integration
- OUT: Import feature, cloud sync, export history

Resource Budget:
- Time: 3 hours max
- Tokens: 80k soft, 120k hard
- Agents: 6 max parallel

Risk: Medium (new UI component, no breaking changes)

Decision: PROCEED

30-05___GOVERNANCE.md created at docs/master/260201_1430_ExportFeature/30-05___GOVERNANCE.md

Next: Phase 0 (Plan Validation)
```

---

## Fast Track Mode (Lightweight Governance)

**For small, low-risk features that don't need full governance ceremony.**

### Feature Brief Template

```markdown
# Feature Brief

## Goal
[One sentence: What are we building?]

## Plan Reference
[Path to 20-00_PLANNING_v*.md or "inline plan"]

## Target Users
[Who benefits?]

## Risk Level
[Low / Medium] (High/Critical → use full governance)

## Max Effort
- Time: [e.g., 2 hours]
- Agents: [e.g., 3 max]

## Do Not Break
- [Critical behavior that must remain unchanged]

## Stop If
- [Conditions that require escalation]

## Approved
[Yes - Fast Track Mode]
```

### Example Feature Brief

```markdown
# Feature Brief

## Goal
Add "Export All Notes" button to hamburger menu

## Plan Reference
20-00_PLANNING_v1.0.md

## Target Users
Power users who want markdown backups

## Risk Level
Low (additive feature, no existing code modified)

## Max Effort
- Time: 1.5 hours
- Agents: 3 max

## Do Not Break
- Existing hamburger menu items
- Desktop switching functionality

## Stop If
- Export requires modifying config schema
- Tests fail on existing functionality

## Approved
Yes - Fast Track Mode
```

### Fast Track Workflow

```
Feature Brief → Phase 0 → Phase 1 (light) → Phase 2 → Phase 3 (light) → Phase 4 (light) → Deliverables
```

**Differences from Full Mode:**
- No 30-05___GOVERNANCE.md (use Feature Brief instead)
- Phase 1: 3-5 tasks max (not 8-15)
- Phase 3: Basic testing (no required bug count)
- Phase 4: Light review (no mandatory UX Integrator)
- Phase 5: Brief lessons (3 bullets max)

---

## Phase 0: Plan Validation (MANDATORY FIRST STEP)

**Purpose:** Validate the incoming plan is solid, actionable, and complete. If the plan came from `/my-planning-master`, this is a quick validation. If it's a raw plan, this is more thorough.

**Spawn Sub-Agent:** "Plan Validator"

### SharedKnowledge Check (via SK Scout Agent)

**Dispatch via `Agent` tool with `subagent_type: "sk-scout"`:**

```
Scan SharedKnowledge for content relevant to: [task being executed].
```

The `sk-scout` agent definition handles all folder scanning, format, and constraints automatically (haiku, read-only, 8 SK folders, max 30 lines).

**Before validation, apply SK Scout results:**

1. **Patterns** (`C:\Projects\SharedKnowledge\patterns\`):
   - Search for relevant patterns
   - If found: Note in journal, prefer reuse
   - If not found: Flag for potential pattern creation post-execution

2. **Lessons** (`C:\Projects\SharedKnowledge\lessons\`):
   - Search INDEX.md for similar past tasks
   - If found: Load lessons, apply constraints
   - Common issues from past runs become formal constraints

3. **Decisions** (`C:\Projects\SharedKnowledge\decisions\`):
   - Search INDEX.md for prior ADRs in this domain
   - If found: Respect prior decisions, note constraints in journal
   - Flag any conflicts between plan ADRs and prior ADRs

4. **Standards** (`C:\Projects\SharedKnowledge\standards\`):
   - Load CODING_PREFERENCES.md
   - Load UX_STYLE_PROFILE.md (for UI tasks)
   - Load relevant domain standards

6. **Preferences** (`C:\Projects\SharedKnowledge\preferences\`):
   - ALWAYS load `team/default.md` — contains locked tech stack versions and workflow rules
   - Run `whoami`, load `personal/<username>.md` if it exists — contains personal overrides
   - Technology constraints from preferences OVERRIDE any assumptions from codebase analysis

5. **Guides** (`C:\Projects\SharedKnowledge\guides\`):
   - Skim for reference material relevant to the feature domain
   - If found: Note in journal for sub-agent instruction enrichment

6. **Runbooks** (`C:\Projects\SharedKnowledge\runbooks\`):
   - Skim for operational procedures that constrain implementation
   - If found: Note constraints in journal and governance

### DoR Verification (Planner-First Workflow)

**If plan is `20-00_PLANNING_v*.md` with DoR checklist (from planner v1.1+):**

Walk the DoR checklist from the plan document:
- If all mandatory items checked → **fast path** (proceed immediately)
- If Standard/Complex items missing for declared tier → flag to user, recommend completing them or downgrading tier
- If mandatory items missing → **stop**, recommend re-planning with `/my-planning-master`

Record DoR verification result in journal.

### Validation Checks

**For plans WITH DoR (quick verification):**
- [ ] DoR checklist complete for declared tier
- [ ] Complexity tier declared and consistent with plan scope
- [ ] Governance approved (Phase -1 complete)
- [ ] Relevant patterns identified
- [ ] Past lessons loaded

**For plans WITHOUT DoR (full validation):**
- [ ] Objective is clear and measurable
- [ ] Checklist has concrete deliverables (not vague goals)
- [ ] Technical approach is specified (or can be inferred)
- [ ] No major unknowns that would block execution
- [ ] Success criteria are testable
- [ ] Governance approved (Phase -1 complete)
- [ ] Relevant patterns identified
- [ ] Past lessons loaded

### Plan Source Detection

**If plan is `20-00_PLANNING_v*.md` (from planner):**
- Quick validation (plan already has file-level specificity)
- Load architecture decisions from plan
- Load scope alignment from plan
- Proceed faster through Phase 0/1

**If plan is a raw file (no planner):**
- Full validation required
- May need to ask clarifying questions
- May need to create refined plan
- Consider recommending `/my-planning-master` first

**If plan is too high-level or unclear:**
1. Recommend running `/my-planning-master` first
2. If user insists: Ask clarifying questions to fill gaps
3. Create refined `HL_PLAN_REFINED_<timestamp>.md`
4. Ask user to approve refined plan before proceeding
5. **STOP - do not proceed with unclear plan**

### Implementation Summary Version Detection

**Check for existing `30-00_IMPLEMENTATION-SUMMARY_v*.md` in the feature folder:**
- If none exist: Will create v1.0
- If exists: Determine increment (minor = re-execution, major = new plan version)
- Log version decision in journal

### Journal Entry Format:

```markdown
### [YYYY-MM-DD HH:MM {elapsed}] {ctx:XX%} Phase 0: Plan Validation

Plan File: 20-00_PLANNING_v2.0.md (from /my-planning-master)
Governance: docs/master/260201_1430_Export/30-05___GOVERNANCE.md
Implementation Summary: Will create v2.0 (new plan version, previous was v1.1)

SharedKnowledge Check (via SK Scout sub-agent):
- Patterns found: dialog_pattern.md (95% match), form_validation.md (partial)
- Lessons loaded: 260115_TaskAPI_lessons.md (relevant: error handling insights)
- Decisions: None relevant
- Standards: CODING_PREFERENCES.md ✅, UX_STYLE_PROFILE.md ✅
- Guides: None relevant
- Runbooks: None relevant

Validation Results:
- ✅ Objective clear: "Add export functionality to TopNote"
- ✅ 8 checklist items, all actionable
- ✅ Tech stack: PySide6, markdown format
- ✅ Governance approved (Medium risk, 3hr budget)
- ✅ Architecture decisions pre-made by planner
- ⚠️ No existing export pattern - will create post-execution

Decision: Plan is valid, proceeding to execution.

Patterns to Apply:
- dialog_pattern.md: Use for ExportDialog layout
- Past lesson: Always validate file permissions before write

Mode: Feature Integration (detected from "Add to TopNote")

Next: Phase 1 (Operational Task Breakdown)
```

---

## Mode Detection (Auto)

**If plan declares a complexity tier (from planner v1.1+), use it.** Otherwise auto-detect:

**New System Mode Indicators:**
- Plan mentions "create project", "scaffold", "new repo"
- No existing codebase references
- Full stack setup (DB + API + frontend)
- Keywords: "build from scratch", "new system", "greenfield"
- Typical tier: Complex

**Feature Integration Mode Indicators:**
- Plan references existing files/components
- Mentions refactoring or extending
- Codebase path provided
- Keywords: "add to", "integrate", "modify", "enhance"
- Typical tier: Standard (can be Quick for small additions)

**Fast Track Mode Indicators:**
- Feature Brief provided (not full governance)
- Low risk assessment
- < 5 tasks expected
- < 2 hours estimated
- Typical tier: Quick

---

## Phase 1: Execution Configuration

**Purpose:** Configure the execution environment for sub-agents. This is about HOW to run tasks, not WHAT the tasks are. The plan already defines the work; this phase prepares the machinery.

### From Planning Master Output (Preferred Path)

If plan is `20-00_PLANNING_v*.md` with DoR:
- Tasks are already defined with file-level specificity — **do NOT re-create them**
- Architecture decisions are already made — **do NOT re-decide them**
- Dependencies are already mapped — **do NOT re-map them**
- Parallel groups are already identified — **use them directly**
- Read the Orchestrator Execution Config section from the plan

**Phase 1 ONLY does:**
1. Map plan tasks to agent assignments (which agent gets which tasks)
2. Confirm execution ordering from plan's parallel groups
3. Set up monitoring triggers (when to compress context, when to checkpoint)
4. Load patterns + preferences into agent instruction templates
5. Prepare agent-specific instructions (coding prefs, standards, pattern refs)

**Do NOT spawn an "Execution Planner" sub-agent** — the orchestrator does this inline. The plan already contains the breakdown.

### From Raw Plan (No Planner)

If plan is raw (no DoR, no file-level tasks):
- Read existing architecture (5-10 key files)
- Identify integration points
- Plan backwards-compatible changes
- List files to modify
- Note patterns being applied
- Create the task breakdown that the planner would have created
- **Spawn Sub-Agent:** "Execution Planner" (only for raw plans)

### Pattern Library Integration

**Before task assignment, check `C:\Projects\SharedKnowledge\patterns\`:**

```markdown
Pattern Search Results:
- ui/dialog_pattern.md → Applicable (export is a dialog)
- ui/form_validation.md → Not applicable (no form input)
- backend/file_operations.md → Applicable (file write)

Decision: Apply dialog_pattern.md and file_operations.md
```

**Pattern Reuse Rule:**
- If suitable pattern exists → **MUST use it** (no redesign)
- If no pattern exists → Design solution, flag for pattern creation
- If pattern is partial match → Adapt, document deviations

### UX Style Check

**For UI tasks, load `C:\Projects\SharedKnowledge\standards\UX_STYLE_PROFILE.md`:**

- Visual layout rules
- Component usage patterns
- Color and typography norms
- Interaction standards
- Terminology guidelines

**All new UI must match existing style profile.**

### Output

- Detailed task breakdown (8-15 tasks for full, 3-5 for fast track)
- Dependencies mapped
- Parallel work identified
- Patterns to apply per task

### Checkpoint Barrier:

```json
{
  "phase": "Planning",
  "orchestration_version": "2.3.0",
  "timestamp": "2026-02-01T14:30:00Z",
  "completed_by": ["planner-agent-001"],
  "governance_ref": "docs/master/260201_1430_Export/30-05___GOVERNANCE.md",
  "plan_source": "20-00_PLANNING_v2.0.md",
  "implementation_summary_version": "v2.0",
  "tasks_created": 12,
  "patterns_applied": ["dialog_pattern.md", "file_operations.md"],
  "parallel_groups": [
    ["task-1", "task-2", "task-3"],
    ["task-4", "task-5"]
  ],
  "state": {
    "mode": "feature-integration",
    "project_root": "/mnt/c/Projects/SuperTools/TopNote",
    "files_to_modify": ["custom_titlebar.py", "export_dialog.py"]
  }
}
```

---

## Phase 2: Parallel Implementation

**Aggressive Sub-Agent Spawning - This Is NOT Optional**

**For EVERY independent task group, spawn separate sub-agents:**

```markdown
Group A (parallel):
  → Spawn Sub-Agent: "Dev Engineer #1" → Task 1
  → Spawn Sub-Agent: "Dev Engineer #2" → Task 2

Group B (sequential after Group A):
  → Wait for Group A barrier
  → Spawn Sub-Agent: "Dev Engineer #3" → Task 3
  → Spawn Sub-Agent: "Dev Engineer #4" → Task 4
```

### Context Hygiene (Iron Law #5 — CRITICAL)

**The orchestrator MUST NOT read implementation source code.** Period.

The orchestrator's context is precious — it coordinates, it doesn't implement. Every source file read into the main context is wasted tokens that could have been a whole extra phase.

**Orchestrator MAY read directly (short files only):**
- Checkpoint JSON files (`30-15___CONTEXT-SNAPSHOT.json`, `30-20___CHECKPOINT-BARRIER_*.json`)
- Resume prompt (`30-99___RESUME_PROMPT.md`)
- Feature Brief / Governance — only if short (< 50 lines)
- File **paths** (via Glob/Grep for filenames only — `files_with_matches` mode)
- Sub-agent structured summaries (returned automatically, max 40 lines each)

**Orchestrator MUST delegate to a sub-agent (like SK Scout):**
- Journal reads (`30-10___JOURNAL_*.md`) — spawn a haiku sub-agent: "Read [journal path], summarize the last N entries relevant to [question]. Max 25 lines."
- Plan reads (`20-00_PLANNING_v*.md`) — spawn a haiku sub-agent: "Read [plan path], extract [specific section/task list/dependencies]. Max 30 lines."
- Governance reads (if long) — same pattern
- Any orchestration artifact over ~50 lines

**This is the same pattern as SK Scout** — protect the orchestrator's context by having cheap sub-agents digest long files and return concise summaries.

**Orchestrator MUST NOT read (ever):**
- Implementation source code (`.py`, `.ts`, `.vue`, `.js`, etc.)
- Config files, test files, or any project source
- Full sub-agent transcripts (only the returned summary)

**Sub-agents are self-sufficient.** Give them:
- Task description + file paths to find/modify
- Pattern references (filenames, not content — the sub-agent reads them)
- Coding preferences (reference path, not file content)
- Style profile path (not content)

If the orchestrator catches itself about to read a source file, **STOP** — that's a sub-agent's job.

### Model Selection (Iron Law #13)

Every `Task` tool call MUST include an explicit `model` parameter:

| Task Type | Model | Why |
|-----------|-------|-----|
| SK Scout (via `sk-scout` agent def) | `haiku` | Skimming INDEX files — model pinned in agent definition |
| Simple edits (add field, wire prop, rename) | `haiku` | Fast, cheap, 3-line changes |
| Standard implementation (new function, integrate pattern) | `sonnet` | **Default — 90% of tasks** |
| Complex multi-file feature, novel logic | `sonnet` | Still sufficient |
| Architecture-sensitive refactoring, tricky edge cases | `opus` | Only when genuinely needed |
| Code review / QA / UX validation | `sonnet` | Pattern matching, not invention |
| Plan Validator / Learning Analyst | `sonnet` | Structured analysis |

**DEFAULT is `sonnet`.** You must justify upgrading to `opus` in the journal.

### Sub-Agent Instructions Include:

- Task description (what to build/modify)
- File paths to find and modify (the sub-agent reads them, not the orchestrator)
- **Pattern to apply** (filename reference, e.g., "Read and follow `C:\Projects\SharedKnowledge\patterns\ui\dialog_pattern.md`")
- **Style profile** (path to `UX_STYLE_PROFILE.md` — sub-agent reads it)
- Coding preferences (path to preferences file — sub-agent reads it)
- Testing requirements
- Saga pattern: Log "how to undo this change"

### Sub-Agent Return Protocol (Iron Law #14)

Every sub-agent instruction MUST end with this return directive:

```
When complete, return ONLY this structured summary (max 40 lines).
Do NOT echo file contents. Do NOT narrate your process.

## Result: [SUCCESS / PARTIAL / FAILED]
## Files Modified
- path/to/file.py (lines X-Y): [what changed]
- path/to/new_file.py (new): [purpose]
## Key Decisions
- [decision and why]
## Compensation (how to undo)
- [revert instructions]
## Issues / Blockers
- [any problems, or "None"]
```

**The orchestrator journals this summary directly.** No need to re-read the modified files.

If the summary indicates a problem, the orchestrator can:
- **Resume** the sub-agent (`resume` parameter) for follow-up questions
- Read a specific modified file (targeted, not bulk) to verify

### Checkpoint Barrier:

```json
{
  "phase": "Implementation",
  "orchestration_version": "2.3.0",
  "timestamp": "2026-02-01T15:45:00Z",
  "completed_by": ["dev-eng-1", "dev-eng-2", "dev-eng-3", "dev-eng-4"],
  "all_agents_ready": true,
  "patterns_applied": ["dialog_pattern.md", "file_operations.md"],
  "files_modified": ["custom_titlebar.py", "export_dialog.py", "markdown_formatter.py"],
  "compensation_available": true,
  "governance_compliance": {
    "breaking_changes": false,
    "within_scope": true,
    "budget_status": "on_track"
  }
}
```

---

## Phase 3: Testing & QA

**Spawn Sub-Agents:**
1. "Test Engineer" - Run tests, verify coverage
2. "QA Specialist" - Bug hunting, edge cases
3. "Integration Tester" - End-to-end validation

### Mandatory Checks:

- [ ] Unit tests pass (verify output, don't assume)
- [ ] Integration tests pass
- [ ] App builds/runs without errors
- [ ] Manual testing of main workflow
- [ ] Edge cases handled (empty notes, special chars, etc.)
- [ ] Style compliance verified (visual spot-check)

### Bug Discovery (REQUIRED for Full Mode):

**Find ≥3 real issues** (not required for Fast Track)

Look for:
- File permission errors
- Unicode/emoji handling
- Empty state handling
- Concurrent access
- Disk space errors
- Style inconsistencies

### Checkpoint Barrier:

```json
{
  "phase": "Testing",
  "orchestration_version": "2.3.0",
  "timestamp": "2026-02-01T16:30:00Z",
  "completed_by": ["test-eng-1", "qa-specialist-1", "integration-tester-1"],
  "test_results": {
    "unit_tests": "12/12 passed",
    "integration_tests": "5/5 passed",
    "coverage": "94%"
  },
  "bugs_found": 4,
  "bugs_fixed": 3,
  "bugs_deferred": 1
}
```

---

## Phase 4: Review & Audit

**Spawn Sub-Agents:**
1. "Code Reviewer / Auditor" - Quality and compliance
2. "UX Integrator" - Style validation

### Code Review Checklist:

- [ ] Code follows project standards (check preferences files)
- [ ] No obvious bugs or anti-patterns
- [ ] Error handling adequate
- [ ] Logging appropriate (not too verbose)
- [ ] Documentation complete
- [ ] Tests verify actual behavior (not just coverage)
- [ ] Patterns applied correctly
- [ ] Governance boundaries respected

### UX/Style Validation

**Spawn "UX Integrator" Sub-Agent**

**Responsibilities:**
- Compare new UI to UX_STYLE_PROFILE.md
- Check visual layout patterns
- Verify navigation structure
- Validate interaction flows
- Check naming conventions
- Verify information hierarchy
- Check error messaging style

### UX Validation Report (30-25___UX-VALIDATION_<task>.md)

```markdown
# UX Validation Report

## Task
Export Feature for TopNote

## Style Profile Reference
C:\Projects\SharedKnowledge\standards\UX_STYLE_PROFILE.md

## Validation Results

### Layout Rules
- ✅ Dialog follows standard dialog layout
- ✅ Button placement matches pattern
- ✅ Margins and padding consistent

### Component Usage
- ✅ Uses standard QPushButton styling
- ✅ Progress bar matches existing patterns
- ⚠️ File path display uses QLineEdit (acceptable deviation)

### Color and Typography
- ✅ Primary button uses accent color
- ✅ Font sizes match existing dialogs
- ✅ Icon colors follow theme system

### Interaction Standards
- ✅ Cancel button closes without action
- ✅ Success shows snackbar notification
- ✅ Error shows inline message

### Terminology
- ✅ "Export" terminology consistent
- ✅ Button labels match existing patterns

## Deviations

### Justified Deviations
1. File path display uses QLineEdit instead of QLabel
   - Reason: Allows copy-paste of path
   - Impact: Minimal visual difference
   - Approved: Yes

### Required Fixes
None

## Verdict
✅ UX APPROVED - Matches existing style profile
```

### Rule of Strict Integration

**All new functionality must match the existing style profile.**

Deviation is allowed ONLY when:
- Explicit redesign is authorized in governance
- Proven usability failure exists in current pattern

**All deviations must be justified and logged.**

### Traceability Verification (Standard + Complex tiers)

**If plan includes a traceability matrix**, update it with verification status:

```markdown
| PRD Req | Plan Task(s) | Test(s) | Verification |
|---------|-------------|---------|--------------|
| REQ-1 | Task 1.1, 1.2 | test_feature_x | PASS - verified [timestamp] |
| REQ-2 | Task 2.1 | test_feature_y | PASS - verified [timestamp] |
| REQ-3 | Task 3.1 | manual check | PASS - verified [timestamp] |
```

Embed the verified matrix in `30-00_IMPLEMENTATION-SUMMARY_v{X.Y}.md`. Every PRD requirement must show a verification status. Any unverified requirement is flagged.

### Audit Against Plan:

- [ ] All checklist items complete
- [ ] Original objective achieved
- [ ] No scope creep (features not requested)
- [ ] Quality bar met (not just "it works")
- [ ] Within governance boundaries
- [ ] Traceability matrix fully verified (Standard + Complex tiers)

---

## Phase 5: Post-Mortem (LEARNING LOOP)

**MANDATORY after Phase 4** (lighter version for Fast Track)

**Purpose:**
- Convert execution experience into operational knowledge
- Prevent recurrence of mistakes
- Improve efficiency over time
- Feed the SharedKnowledge repository

### Post-Mortem Process

**Spawn Sub-Agent:** "Learning Analyst"

**Analyze the entire execution:**
1. Review all journal entries
2. Identify successes and failures
3. Extract actionable learnings
4. Propose new rules or pattern updates

### Lessons Learned Document (30-35___LESSONS-LEARNED_<task>.md)

```markdown
# Post-Mortem Learning Report

## Task
Export Feature for TopNote

## Plan Source
20-00_PLANNING_v2.0.md (from /my-planning-master)

## Implementation Summary
30-00_IMPLEMENTATION-SUMMARY_v2.0.md

## Execution Summary
- Duration: 2.5 hours
- Agents spawned: 8
- Checkpoints: 4
- Context compressions: 0

## What Worked Well
1. Pattern reuse (dialog_pattern.md) saved ~30 min design time
2. Parallel agent spawning completed Phase 2 in 45 min vs estimated 90 min
3. Early QA involvement caught encoding bug before integration test
4. Planning master pre-resolved architecture decisions (saved Phase 1 time)

## What Failed
1. Initial export path used hardcoded directory - violated portability rule
2. Forgot to check file permissions on first write attempt

## Unexpected Issues
1. QFileDialog on Windows returns forward slashes, caused path join bug
2. Markdown formatter needed explicit UTF-8 encoding declaration

## Coordination Problems
None - clean handoffs between agents

## Time/Token Analysis
- Estimated: 3 hours / 80k tokens
- Actual: 2.5 hours / 62k tokens
- Under budget ✅

## Governance Compliance
- All boundaries respected
- No scope creep
- No breaking changes

## New Rules to Add
1. **Always check file permissions before write operations**
   - Add to: SharedKnowledge/lessons/INDEX.md
   - Category: File Operations

2. **Use pathlib for cross-platform path handling**
   - Add to: SharedKnowledge/standards/CODING_PREFERENCES.md

## Patterns to Create/Update
1. **NEW: export_dialog_pattern.md**
   - Export workflow with progress feedback
   - File format selection UI
   - Path validation

2. **UPDATE: file_operations.md**
   - Add permission check section
   - Add encoding best practices

## Rules to Deprecate
None

## Recommendations for Future Runs
1. For file-heavy operations, spawn dedicated "File Ops Specialist" agent
2. Consider adding export preview before write
3. Track export history for user convenience (future feature)

## Knowledge Base Updates Required
- [ ] Create export_dialog_pattern.md
- [ ] Update file_operations.md with permission checks
- [ ] Add lesson to INDEX.md
- [ ] Update CODING_PREFERENCES.md with pathlib rule
```

### Integration with SharedKnowledge

**After creating 30-35___LESSONS-LEARNED_<task>.md:**

1. **Copy to SharedKnowledge:**
   ```
   Copy: docs/master/260201_1430_Export/30-35___LESSONS-LEARNED_ExportFeature.md
   To: C:\Projects\SharedKnowledge\lessons\260201_ExportFeature_lessons.md
   ```

2. **Update INDEX.md:**
   ```markdown
   # Lessons Index

   ## File Operations
   - 260201_ExportFeature_lessons.md - Permission checks, path handling
   - 260115_TaskAPI_lessons.md - Error handling insights

   ## UI Patterns
   - 260122_STT_lessons.md - Progress indicators
   ```

3. **Create new patterns (if flagged):**
   ```
   Create: C:\Projects\SharedKnowledge\patterns\ui\export_dialog_pattern.md
   ```

4. **Update standards (if rules changed):**
   ```
   Update: C:\Projects\SharedKnowledge\standards\CODING_PREFERENCES.md
   Add: "Use pathlib for all path operations"
   ```

5. **Promote ADRs to SharedKnowledge/decisions/:**

   Check the plan's Architecture Decisions section for ADRs marked "Promote to SharedKnowledge: Yes":
   ```
   Copy ADR-001 to: C:\Projects\SharedKnowledge\decisions\YYMMDD_ADR-001_title.md
   Update: C:\Projects\SharedKnowledge\decisions\INDEX.md
   ```

   This connects the plan's architecture decisions to the team's long-term decision record. Only decisions marked for promotion are copied — not every plan decision needs to be preserved globally.

6. **Create/update runbooks in SharedKnowledge/runbooks/ (NEW in v2.3):**

   If the execution established new operational procedures (deployment steps, rollback procedures, maintenance tasks):
   ```
   Create: C:\Projects\SharedKnowledge\runbooks\YYMMDD_<procedure-name>.md
   ```

   Examples of runbook-worthy discoveries:
   - New deployment procedure for a service
   - Database migration rollback steps
   - Environment-specific configuration procedures
   - Monitoring or alerting setup steps

7. **Reference guides in lessons (NEW in v2.3):**

   If `guides/` content informed execution decisions, note which guides were useful in the lessons document. This helps future orchestration runs find relevant guides faster.

---

## Context Budget Protocol (Iron Laws #5, #13, #14)

**The orchestrator's own context (excluding sub-agent internals) should NEVER exceed ~200k tokens.** If the hygiene rules are followed (no source code reads, structured sub-agent returns, delegate long file reads), this is easily achievable even with the 1M context window.

### Model Prerequisite

**These thresholds require Opus 4.6 with 1M context window.** Before starting an orchestration run, verify the model:

1. **Check statusline** — must show `🤖 Opus 4.6 (1M)`. If it shows a different model or context size, STOP.
2. **Check model ID** — must contain `claude-opus-4-6[1m]` or equivalent 1M-context model.
3. **If model is NOT 1M** — fall back to legacy thresholds: WARNING at ~100k, STOP at ~140k, FORBIDDEN at ~160k.

**Why this matters:** Sonnet models have 200k context windows. Using the 400k STOP threshold on a 200k model would be catastrophic — the session would die before reaching the "warning" zone.

### Context Thresholds (Unified — same for all pipeline skills)

**For 1M context models (Opus 4.6 1M):**

| Threshold | Action |
|-----------|--------|
| **0–200k tokens** | 🟢 Normal operation. No action needed. |
| **200k–300k tokens** | 🟡 **WARNING**: Generate/update resume prompt (`30-99___RESUME_PROMPT.md`). Log to journal. Continue work. |
| **300k–400k tokens** | 🔴 **STOP**: Finalize resume prompt, print user alert, stop all work. User starts new session. |
| **400k+ tokens** | 💀 **FORBIDDEN**: Never reach this zone. Quality degrades significantly above 400k. |

**Fallback for 200k context models (Sonnet, Haiku):**

| Threshold | Action |
|-----------|--------|
| **0–100k tokens** | 🟢 Normal operation. |
| **100k–140k tokens** | 🟡 **WARNING**: Generate/update resume prompt. |
| **140k–160k tokens** | 🔴 **STOP**: Finalize resume, alert user, stop. |
| **160k+ tokens** | 💀 **FORBIDDEN**: Never reach this zone. |

**How to check:** Use `/context` command, check statusline (🟢💾XXXk/1M), or estimate from conversation length.

**There is no "compression" step.** Prevention (hygiene) replaces cure (compact). If context is high, it means the orchestrator read too much — fix the cause, don't treat the symptom.

**Note:** Although the 1M model supports 1M tokens, accuracy degrades from ~97% (0-200k) to ~76% (at 1M). The 400k hard ceiling keeps sessions in the 93%+ accuracy zone.

### Context Snapshot

At every phase transition, update `30-15___CONTEXT-SNAPSHOT.json`:

### Example Snapshot:

```json
{
  "orchestration_version": "2.3.0",
  "timestamp": "2026-02-01T16:30:00Z",
  "phase": "Testing",
  "mode": "feature-integration",
  "project": "TopNote Export Feature",
  "governance_ref": "docs/master/260201_1430_Export/30-05___GOVERNANCE.md",
  "plan_source": "20-00_PLANNING_v2.0.md",
  "implementation_summary_version": "v2.0",
  "patterns_applied": ["dialog_pattern.md", "file_operations.md"],
  "active_tasks": [
    "Test edge cases",
    "Fix Unicode bug"
  ],
  "recent_decisions": [
    "Use async export to prevent UI freeze",
    "Add progress dialog for large exports",
    "Defer progress bar to v3.22"
  ],
  "open_issues": [
    "Progress indicator needed (low priority)"
  ],
  "next_steps": [
    "Complete QA testing",
    "Run code review",
    "UX validation"
  ],
  "budget_status": {
    "time_used": "1.5 hours",
    "time_budget": "3 hours",
    "tokens_used": 52000,
    "token_budget": 80000
  },
  "token_count": 52000,
  "journal_entries_archived": 45
}
```

---

## Session Continuity Protocol (CRITICAL - Iron Law #12)

**Problem:** Long orchestration runs exhaust the context window. On 1M models, quality degrades well before the window fills. When context gets too high, accuracy drops, `/compact` fails, and ALL progress tracking exists only in-session memory. The user is stranded.

**Solution:** Proactive resume prompt generation — inspired by [Anthropic's "initializer agent" pattern](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) and production patterns from Google/OpenAI agent frameworks.

### When to Trigger

**Automatic triggers (orchestrator MUST monitor):**

| Trigger | Action |
|---------|--------|
| Context reaches ~200k tokens (1M model) / ~100k (200k model) | **WARNING**: Generate/update resume prompt. Log to journal. Continue work normally. |
| Context reaches ~300k tokens (1M model) / ~140k (200k model) | **STOP**: Finalize resume prompt, print user alert, stop all work. User starts new session. |
| Phase transition (any phase completes) | **ROUTINE**: Update resume prompt as part of checkpoint barrier |
| Every 30 minutes of wall-clock execution | **PERIODIC**: Refresh resume prompt with latest state |

**How to check context:** Use `/context` command or estimate from conversation length. When in doubt, generate the resume prompt — it costs nothing but can save hours.

**Note:** With proper context hygiene (Iron Laws #5, #13, #14), reaching 200k should be rare on a 1M model. If you hit 200k, something is wrong — check if you accidentally read source files or consumed full sub-agent transcripts.

### User Alert Messages (MUST print to terminal)

**CRITICAL RULE: The alert MUST be the ABSOLUTE LAST output of the conversation.**
Save all files, then print the alert as your FINAL message.
Do NOT output anything after the alert — no "let me continue", no tool calls, no summaries.

**At ~200k tokens (1M model) / ~100k (200k model) — generate resume prompt silently, log to journal, continue working.**

No user alert needed. Just ensure `30-99___RESUME_PROMPT.md` is current.

**At ~300k tokens (1M model) / ~140k (200k model) — save files, then print this as your ABSOLUTE FINAL output, then STOP:**

```
============================================================
  🔴 CONTEXT AT ~300k — STOPPING FOR SESSION CONTINUITY
============================================================

Resume file saved to:
  <PATH>/30-99___RESUME_PROMPT.md

Start a new session to continue:

  1. Exit:  Ctrl+C or close terminal
  2. Start: claude
  3. Paste the following into the new session:

     Resume an in-progress orchestration run.
     Read: <PATH>/30-99___RESUME_PROMPT.md
     After reading, invoke /my-orchestration-master and skip completed phases.

Full guide: C:\Projects\SharedKnowledge\guides\session-continuity-guide.md
============================================================
```

**After printing the alert: OUTPUT NOTHING. The alert IS your final message.**

### Pipeline Resume File Convention

All pipeline skills use `XX-99` as the resume file — always the last file in each prefix range:

| Prefix | Skill | Resume File | Contents |
|--------|-------|-------------|----------|
| `10-xx` | Research | `10-99___RESUME_STATE.md` | Research progress, completed/remaining steps |
| `20-xx` | Planning | `20-99___RESUME_STATE.md` | Planning progress, decisions made, open questions |
| `30-xx` | Orchestration | `30-99___RESUME_PROMPT.md` | Full resume prompt with task status, git state, next actions |

**Find any resume file:** `find docs/master/ -name "*99___RESUME*" -type f`

The orchestrator should be aware that upstream resume files may exist if the prior pipeline stages were interrupted and resumed.

### Resume Prompt File: `30-99___RESUME_PROMPT.md`

**Location:** `<project_root>/docs/master/<timestamp>_<task>/30-99___RESUME_PROMPT.md`

This file is the **single artifact a new session needs** to continue work. It is:
- **Self-contained** — everything needed to resume, no chain of file reads required before understanding state
- **Copy-paste ready** — user copies content directly into a new Claude session
- **Always current** — updated at every checkpoint and context threshold
- **Structured for LLM consumption** — not prose, but actionable instructions

### Resume Prompt Template

```markdown
# ORCHESTRATION RESUME PROMPT
<!-- Generated: [YYYY-MM-DD HH:MM] | Orchestration v2.5 | Context: [X]% -->

## IMMEDIATE CONTEXT
You are resuming an in-progress orchestration run. Do NOT restart from Phase 0.

**Project:** [project name and root path]
**Branch:** [git branch name]
**Feature folder:** [full path to docs/master/<timestamp>_<task>/]
**Orchestration mode:** [New System / Feature Integration / Fast Track]
**Complexity tier:** [Quick / Standard / Complex]

## CURRENT STATE
**Current phase:** [Phase N: Name]
**Phase status:** [In progress / Blocked / Completing]

### Completed Phases
- [x] Phase -1: Governance → 30-05___GOVERNANCE.md
- [x] Phase 0: Validation → Plan validated
- [x] Phase 1: Execution Config → [N] tasks mapped
- [ ] Phase 2: Implementation → [N/M] task groups done
- [ ] Phase 3: Testing
- [ ] Phase 4: Review
- [ ] Phase 5: Post-Mortem

## TASK STATUS
<!-- From TodoWrite/TaskList state at time of generation -->

### Completed Tasks
| Task | Description | Files Modified |
|------|-------------|---------------|
| [ID] | [description] | [file1.py, file2.py] |

### In-Progress Tasks
| Task | Description | What's Done | What Remains |
|------|-------------|-------------|-------------|
| [ID] | [description] | [partial work] | [remaining steps] |

### Blocked / Pending Tasks
| Task | Description | Blocked By | Notes |
|------|-------------|-----------|-------|
| [ID] | [description] | [dependency] | [context] |

## KEY FILES TO READ (in order)
1. **[path/to/JOURNAL.md]** — Execution log (read last 50 lines for recent context)
2. **[path/to/CONTEXT-SNAPSHOT.json]** — Machine-readable state
3. **[path/to/GOVERNANCE.md]** — Boundaries and budget (skim)
4. **[path/to/PLANNING_v*.md]** — Original plan (reference, don't re-read fully)

## GIT STATE
**Branch:** [branch name]
**Last meaningful commit:** [hash] - [message]
**Uncommitted changes:** [summary of staged/unstaged files, or "none"]
**New files created this session:** [list]

## CRITICAL DECISIONS MADE (do not revisit)
1. [Decision] — Reason: [why]
2. [Decision] — Reason: [why]
3. [Decision] — Reason: [why]

## OPEN ISSUES / BLOCKERS
1. [Issue] — Impact: [what's affected] — Suggested: [resolution]

## IMMEDIATE NEXT ACTIONS
<!-- These are the EXACT steps to take, in order -->
1. Read the journal file (last 50 lines): [path]
2. Read the context snapshot: [path]
3. [First actual work action]
4. [Second actual work action]
5. [Third actual work action]

## RESUME INSTRUCTIONS
1. Invoke `/my-orchestration-master` skill
2. Skip Phases -1 through [last completed phase] — they are DONE
3. Resume at: **Phase [N], Task [ID]: [description]**
4. The governance, plan, and task breakdown are already in the feature folder — read them, don't recreate
5. After resuming, update this resume prompt file with new state

## BUDGET REMAINING
- **Time:** [X hours remaining of Y budget]
- **Tokens:** [Fresh 1M context — prioritize implementation over re-reading]
- **Agents:** [Max N parallel]
```

### Generation Process

**When generating the resume prompt, the orchestrator MUST:**

1. **Snapshot the task list** — Capture ALL tasks with their exact status (completed, in-progress, blocked, pending)
2. **Read git state** — Branch, last commit, uncommitted changes (`git status`, `git log -1`)
3. **Summarize decisions** — Extract from journal the 3-5 most important decisions that a new session must NOT revisit
4. **List modified files** — What was changed this session (from journal + git diff)
5. **Define next actions concretely** — Not "continue implementation" but "implement circuit breaker in src/utils/circuit_breaker.py following the pattern in SharedKnowledge/patterns/..."
6. **Write to disk immediately** — Don't buffer in context, write to `30-99___RESUME_PROMPT.md`

### Resume Prompt Update Protocol

```
Phase transition     → Full regeneration of 30-99___RESUME_PROMPT.md
Task completion      → Update TASK STATUS section only
Context at ~200k (1M model)  → Full regeneration + journal entry "Context warning: resume prompt updated"
Context at ~300k (1M model)  → Final generation + STOP ALL WORK + print alert to user
Every 30 min         → Refresh TASK STATUS and IMMEDIATE NEXT ACTIONS sections
```

### What Happens in the New Session

The user:
1. Exits the exhausted session
2. Opens the resume prompt file (it's on disk at a known location)
3. Starts a new `claude` session
4. Pastes the resume prompt content
5. Claude reads the referenced files, picks up the task list, and continues

**The new session does NOT:**
- Re-run Phase -1 (governance is done)
- Re-run Phase 0 (validation is done)
- Re-create the task breakdown
- Re-read the entire plan from scratch
- Re-make decisions that were already made

### Integration with `/my-prepare-for-context-reset`

If the user manually invokes `/my-prepare-for-context-reset` during an orchestration run:
- The skill MUST detect orchestration artifacts (look for `docs/master/` and `30-10___JOURNAL_*.md`)
- If found: Generate an orchestration-aware resume prompt using the template above
- If not found: Fall back to the standard context reset template

### Red Flags - Session Continuity

| Thought | Reality |
|---------|---------|
| "Context is fine, I'll generate the resume prompt later" | Generate it NOW. You won't get "later" if context explodes |
| "The checkpoint files are enough to resume" | JSON checkpoints are for machines. Humans need the resume prompt |
| "I'll just compact and continue" | Don't rely on compact. Prevention (hygiene) > cure (compact). Resume prompt is your safety net |
| "Sub-agents still have work to do, I can't stop" | Write the resume prompt WHILE agents work. It's not either/or |
| "The user can figure out where we were from the journal" | 500-line journals are unreadable. The resume prompt is the distilled version |
| "I need to read the journal/plan to understand state" | Spawn a haiku sub-agent to summarize it. Don't pull it into orchestrator context |

### Journal Entry (Session Continuity):

```markdown
### [YYYY-MM-DD HH:MM {elapsed}] {ctx:XX%} Session Continuity: Resume Prompt Generated

Context Level: ~200k/1M tokens (WARNING zone)
Trigger: Context threshold warning (200k on 1M model)

Resume Prompt: docs/master/260201_1430_Export/30-99___RESUME_PROMPT.md
Current Phase: Phase 2 (Implementation)
Tasks Complete: 5/12
Tasks In Progress: 3/12
Tasks Remaining: 4/12

Key State Captured:
- All completed task outputs and file changes
- 3 critical architecture decisions (not to revisit)
- 2 open issues with suggested resolutions
- Concrete next 5 actions for new session

Action: Continue work. Resume prompt will auto-update at next checkpoint.
```

---

## Error Recovery (Saga Pattern)

**When Sub-Agent Fails:**

1. **Auto-retry with different approach** (attempt 1/3)
2. **Spawn "Debug Specialist"** sub-agent (attempt 2/3)
3. **Document failure, continue with other tasks** (attempt 3/3 - circuit breaker)
4. **Escalate to user** (if critical blocker or governance boundary hit)

### Circuit Breaker Pattern:

```markdown
### [YYYY-MM-DD HH:MM {elapsed}] {ctx:XX%} ERROR RECOVERY

Task: "Add WebSocket notifications"
Agent: Dev Eng #5
Error: ModuleNotFoundError: No module named 'socketio'

Recovery Attempt 1: Install missing dependency
→ pip install python-socketio
→ Result: ✅ Success, retrying task

(If failed again)
Recovery Attempt 2: Spawn Debug Specialist
→ Investigate: Is socketio compatible with Python 3.11?
→ Result: Version conflict detected, use socket.io v4

(If failed again)
Recovery Attempt 3: Circuit breaker OPEN
→ Document blocker in 30-30___TECH-DEBT_<task>.md
→ Mark task as DEFERRED
→ Continue with other tasks
→ Flag for user review
→ Note in LESSONS_LEARNED for future prevention
```

### Compensation Metadata (Undo Strategy):

Every change includes how to reverse it:

```markdown
Files Modified:
- topnote/ui/export_dialog.py (new file)

Compensation:
- Delete topnote/ui/export_dialog.py
- Remove import from topnote/ui/__init__.py line 23
- Restore custom_titlebar.py to commit abc123
- Delete tests/test_export.py
```

---

## Final Deliverables

When all checklist items complete:

### 1. 30-00_IMPLEMENTATION-SUMMARY_v{X.Y}.md (PRIMARY OUTPUT)

```markdown
# Implementation Summary: [Feature Name]

**Version:** v{X.Y}
**Created:** [YYYY-MM-DD HH:MM]
**Orchestration Version:** 2.3.0
**Complexity Tier:** [Quick / Standard / Complex]
**Status:** [Complete / Partial / Superseded by v{X.Y+1}]

## Plan Reference
- Plan: 20-00_PLANNING_v{X.Y}.md
- DoR Verified: [Yes / N/A (no DoR)]
- Governance: 30-05___GOVERNANCE.md

## Objective
[What was built]

## Results
✅ All [N] checklist items complete
✅ [N] unit tests + [N] integration tests passing
✅ [Feature description and user impact]
✅ UX validated against style profile

## Patterns Applied
- [pattern name] (from SharedKnowledge)

## Architecture
- [Component]: [file path] ([N] lines)
- [Component]: [file path] ([N] lines modified)

## Traceability (Standard + Complex tiers)

| PRD Req | Plan Task(s) | Test(s) | Verification |
|---------|-------------|---------|--------------|
| REQ-1 | Task 1.1 | test_x | PASS |
| REQ-2 | Task 2.1 | test_y | PASS |

## Testing
- Unit test coverage: [X]% on [scope]
- Integration tests: [description]
- Regression: [existing tests verified]
- Edge cases: [description]

## UX Validation
[Status] - See 30-25___UX-VALIDATION_[task].md

## Known Issues (see 30-30___TECH-DEBT_<task>.md)
- [Known issue] (deferred to [future version])

## ADRs Promoted to SharedKnowledge
- [ADR-001: title] → SharedKnowledge/decisions/[filename]
- (or "None")

## Lessons Learned
- See 30-35___LESSONS-LEARNED_[task].md
- Copied to: SharedKnowledge/lessons/[filename]

## User Impact
[End-user-facing description of what changed]

## Version History
| Version | Date | Changes |
|---------|------|---------|
| v{X.Y} | [date] | [description] |
```

### 2. 30-30___TECH-DEBT_<task>.md

```markdown
# [Feature] - Technical Debt & Future Work

## Deferred Items
1. **[Item]**
   - Priority: [Low/Med/High]
   - Reason: [Why deferred]
   - Proposed: [Future solution]

## Workarounds / Hacks
[Any shortcuts taken]

## Assumptions Made
[Assumptions that could change]

## Future Enhancements
[Natural next steps]

## Pattern Gaps Identified
[Missing patterns flagged for SharedKnowledge]
```

### 3. Architecture Docs (if complex)

**When to create:**
- New system with 5+ components
- Complex data flows
- Multi-repo coordination

**Format:**
- System architecture diagram (if tool available)
- Component interaction description
- Data flow documentation

---

## Team Workflow Rules

**Purpose:** Ensure governance is shared and operational across the team.

### Rules

1. **Governance and plans are distributed**
   - All team members can access docs/master/
   - SharedKnowledge is the single source of truth

2. **No work without documented intent**
   - Every task has governance (full or fast track)
   - Every decision is journaled

3. **No undocumented scope expansion**
   - If it's not in governance, it's not approved
   - Scope changes require governance amendment

4. **All major decisions are logged**
   - Architecture choices → Journal
   - Trade-offs → Journal
   - Deviations → Journal with justification

5. **Knowledge flows back to SharedKnowledge**
   - Every run produces lessons
   - Novel patterns get documented
   - Standards evolve based on learnings

### Dual Control Model

**Strategic Control (Phase -1):**
- Defines objectives and boundaries
- Answers: "Should we do this and how far?"
- Owner: Team lead / User

**Operational Control (Phases 0-5):**
- Monitors execution in real time
- Answers: "Are we still within limits?"
- Owner: Orchestrator (Claude)

**Both controls are mandatory.**

---

## Coding Preferences Integration

### Auto-Discovery Order:

```
1. C:\Projects\SharedKnowledge\preferences\team\default.md (team baseline — tech stack constraints, workflow)
2. C:\Projects\SharedKnowledge\preferences\personal\<USERNAME>.md (personal overrides — run whoami)
3. C:\Projects\SharedKnowledge\standards\CODING_PREFERENCES.md (team coding standards)
4. <project_root>/.claude/CODING_PREFERENCES.md (project-specific overrides)
5. Environment variable: $CLAUDE_PREFERENCES_PATH
```

**If multiple found:**
- Team preferences (items 1-3) set baseline
- Personal preferences (item 2) override team defaults where conflicts exist
- Project preferences (item 4) override all for project-specific rules
- Log all sources in journal

### UX Style Profile Discovery:

```
1. C:\Projects\SharedKnowledge\standards\UX_STYLE_PROFILE.md (team)
2. <project_root>/docs/UX_STYLE_PROFILE.md (project)
```

---

## Red Flags - STOP Immediately

These rationalizations mean you're violating orchestration principles:

- ❌ "Feature is small, I'll just code it myself" → Use sub-agents anyway (parallelization matters)
- ❌ "I'll document at the end" → Journal DURING work, not after (you'll forget context)
- ❌ "Mental checklist is fine" → Create formal task breakdown (long sessions lose track)
- ❌ "Context is fine, no need to worry" → Monitor context via statusline, generate resume prompt at WARNING zone (200k on 1M model)
- ❌ "Tests will probably pass" → Run tests, verify output (assumptions fail)
- ❌ "I'll skip checkpoints this time" → Checkpoints are NOT optional (context exhausts)
- ❌ "User might not want this, I'll ask first" → User gave you the plan, execute it (don't delay)
- ❌ "Plan needs clarification, I should ask 5 questions" → Only ask if plan is UNCLEAR (Iron Law #6)
- ❌ "I need user approval on design" → Plan specifies design, implement it (no delays)
- ❌ "Pressure tactics are being used, I should refuse" → Pressure = urgency, not manipulation (execute)
- ❌ "This violates good practices" → Orchestration IS good practice (follow phases)
- ❌ "I can't proceed without mockups" → Plan has checklist, that's sufficient (don't block)
- ❌ "I'll redesign this pattern, I can do better" → Reuse SharedKnowledge patterns (Iron Law #7)
- ❌ "Post-mortem is optional" → Write lessons EVERY run (Iron Law #8)
- ❌ "UX is fine, no need to check" → Validate against style profile (Iron Law #9)
- ❌ "Governance is bureaucracy" → It's intent formalization (Iron Law #10)
- ❌ "I'll skip versioning, it's just one run" → Version ALL deliverables (Iron Law #11)
- ❌ "Context is fine, I'll write the resume prompt later" → Context death is sudden and unrecoverable (Iron Law #12)
- ❌ "The checkpoint JSON files are enough" → Checkpoints are for machines, resume prompts are for humans + LLMs (Iron Law #12)
- ❌ "Let me read the source files to understand before dispatching" → Sub-agents read their own files. You coordinate, you don't implement (Iron Law #5)
- ❌ "I need to see the full sub-agent output to verify" → The 40-line structured summary tells you everything. If not, resume the agent (Iron Law #14)
- ❌ "This task is complex, it needs Opus" → 90% of tasks work fine on Sonnet. Justify the upgrade in journal (Iron Law #13)
- ❌ "Let me read the journal to check what happened" → Spawn a haiku sub-agent to summarize it for you (Iron Law #5)

**All of these mean: Stop. Follow the orchestration workflow correctly.**

---

## Orchestration Checklist

Use TodoWrite to create todos for each item:

### Phase -1: Governance
- [ ] Plan source identified (20-00_PLANNING_v*.md with DoR or raw plan)
- [ ] Governance template selected (Slim if DoR present, Full if raw plan)
- [ ] 30-05___GOVERNANCE.md created (or Feature Brief for Quick tier)
- [ ] Execution budget set (time, tokens, agents)
- [ ] Escalation conditions defined
- [ ] Change policy set
- [ ] Approval decision logged
- [ ] 30-20___CHECKPOINT-BARRIER_Governance.json created

### Phase 0: Validation
- [ ] DoR checklist verified (if present — fast path)
- [ ] Complexity tier confirmed (from plan or auto-detected)
- [ ] SharedKnowledge scanned via SK Scout sub-agent (patterns, lessons, decisions, standards, guides, runbooks)
- [ ] Plan file received and read
- [ ] Plan validation complete (quick for DoR plans, full for raw)
- [ ] Mode auto-detected (New System / Feature / Fast Track)
- [ ] Standards loaded (CODING_PREFERENCES, UX_STYLE_PROFILE)
- [ ] Implementation summary version determined

### Setup
- [ ] Created docs/master/YYMMDD_HHMMSS_<task>/ directory (or using existing)
- [ ] Created 30-10___JOURNAL_<task>.md with first entry
- [ ] Recorded orchestration start time (for elapsed time tracking in journal headers)
- [ ] Auto-discovered coding preferences (or noted none found)
- [ ] Logged preferences file location in journal

### Phase 1: Execution Configuration
- [ ] Plan tasks mapped to agent assignments
- [ ] Execution ordering confirmed from plan's parallel groups
- [ ] Monitoring triggers set (compression, checkpoints)
- [ ] Agent instruction templates prepared (patterns, preferences, standards)
- [ ] Pattern library checked (verify plan's pattern references exist)
- [ ] 30-20___CHECKPOINT-BARRIER_Planning.json created
- [ ] (Raw plans only: task breakdown created, execution planner spawned)

### Phase 2: Implementation
- [ ] Model selected per sub-agent (default sonnet, justify opus in journal) — Iron Law #13
- [ ] Sub-agents spawned for each parallel group with structured return directive — Iron Law #14
- [ ] Zero source code read in orchestrator context — Iron Law #5
- [ ] Each sub-agent received: task + file paths + pattern refs + prefs path (not content)
- [ ] Each sub-agent returned ≤40-line structured summary (not full transcript)
- [ ] **Feature logging included** — Entry/Decision/Result/Error points per `standards/FEATURE_LOGGING.md`
- [ ] All agents reached checkpoint barrier
- [ ] Git status logged (read-only)
- [ ] 30-20___CHECKPOINT-BARRIER_Implementation.json created

### Phase 3: Testing
- [ ] Test Engineer sub-agent spawned
- [ ] QA Specialist sub-agent spawned
- [ ] Tests executed (verified output, not assumed)
- [ ] ≥3 bugs discovered and fixed (or deferred) - Full Mode only
- [ ] Health checks passed (app builds/runs)
- [ ] 30-20___CHECKPOINT-BARRIER_Testing.json created

### Phase 4: Review
- [ ] Code Reviewer sub-agent spawned
- [ ] UX Integrator sub-agent spawned (Full Mode)
- [ ] Plan compliance verified
- [ ] Code quality verified
- [ ] 30-25___UX-VALIDATION_<task>.md created (Full Mode)
- [ ] No silent changes (all in journal)
- [ ] Governance boundaries verified

### Phase 5: Post-Mortem
- [ ] Learning Analyst sub-agent spawned
- [ ] 30-35___LESSONS-LEARNED_<task>.md created
- [ ] New patterns identified
- [ ] Rules to add/update identified
- [ ] Copied to SharedKnowledge/lessons/
- [ ] INDEX.md updated
- [ ] New patterns created (if flagged)
- [ ] Standards updated (if rules changed)
- [ ] ADRs marked "promote" copied to SharedKnowledge/decisions/
- [ ] decisions/INDEX.md updated (if ADRs promoted)
- [ ] Runbooks created/updated in SharedKnowledge/runbooks/ (if new procedures discovered)
- [ ] Guides referenced in lessons (if guides informed execution)

### Context Hygiene & Session Continuity
- [ ] Zero source code files read in orchestrator context (Iron Law #5)
- [ ] Long orchestration artifacts delegated to haiku sub-agents (journal, plan reads)
- [ ] All sub-agents returned ≤40-line structured summaries (Iron Law #14)
- [ ] All sub-agents dispatched with explicit model parameter (Iron Law #13)
- [ ] 30-15___CONTEXT-SNAPSHOT.json updated at phase transitions
- [ ] Orchestration version included in all checkpoints
- [ ] 30-99___RESUME_PROMPT.md generated (first version at Phase 1 completion)
- [ ] Resume prompt updated at every phase transition
- [ ] Resume prompt updated at ~100k tokens (silent, continue work)
- [ ] At ~140k tokens: finalized resume prompt + STOP + user alert
- [ ] Resume prompt includes: task status, git state, decisions, next actions

### Deliverables
- [ ] 30-00_IMPLEMENTATION-SUMMARY_v{X.Y}.md created
- [ ] 30-30___TECH-DEBT_<task>.md created
- [ ] 30-99___RESUME_PROMPT.md current (always kept up to date)
- [ ] Architecture docs created (if complex)
- [ ] All original checklist items complete
- [ ] SharedKnowledge updated with learnings
- [ ] Previous implementation summary marked as superseded (if re-execution)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-01 | Initial orchestration skill |
| 2.0.0 | 2026-02 | Added: Strategic Governance (Phase -1), Pattern Library, Learning Loop (Phase 5), UX Validation, Fast Track Mode, Team Workflow, SharedKnowledge integration, Versioning |
| 2.1.0 | 2026-02 | Added: Planning Master integration, versioned deliverables (30-00_IMPLEMENTATION-SUMMARY_v*.md), slimmed Phase 0/1 for planner-first workflow, version control for all output files, pipeline relationship diagram |
| 2.2.0 | 2026-02 | Added: DoR verification gate, slim governance template (planner-first), renamed Phase 1 to Execution Configuration, complexity tiers (Quick/Standard/Complex), traceability matrix verification in Phase 4, ADR promotion to SharedKnowledge/decisions/ in Phase 5, implementation summary includes traceability and ADR promotion record |
| 2.3.0 | 2026-02 | Added: Full SharedKnowledge integration via SK Scout sub-agent (guides/, runbooks/, decisions/ reads in Phase 0), runbooks write-back in Phase 5, guides reference in lessons, sub-agent pattern to protect main context from SK content bloat, updated SK directory tree with all folders |
| 2.4.0 | 2026-02 | Added: Session Continuity Protocol (Iron Law #12) — proactive resume prompt generation at context thresholds (70%/85%/90%), 30-99___RESUME_PROMPT.md as standard deliverable, phase-transition auto-updates, integration with /my-prepare-for-context-reset, structured resume template for copy-paste into new sessions. Inspired by Anthropic's initializer agent pattern and industry best practices |
| 2.5.0 | 2026-02 | Context Efficiency overhaul — 3 new Iron Laws: #5 rewritten (orchestrator reads ZERO source code), #13 (right-size model per sub-agent, default sonnet), #14 (sub-agents return ≤40-line structured summaries). Replaced context compression with prevention-first approach (context hygiene > compact). Orchestrator delegates long artifact reads to haiku sub-agents (like SK Scout). Simplified thresholds: ~100k=warning+resume, ~140k=STOP. Added model selection matrix and sub-agent return protocol. |

---

## Real-World Impact

**Based on production systems:**
- **Claude Code**: ~90% of codebase written by Claude Code itself using orchestration
- **LangGraph**: Multi-hour workflows with checkpointing in production
- **SagaLLM**: Transaction-style compensation in database agents
- **Claude-Flow**: 60+ coordinated agents with barrier synchronization

**Key benefits:**
- **Context rot eliminated**: Hygiene rules keep orchestrator under 100k tokens
- **Recovery from failures**: Checkpoints enable "resume where I left off"
- **Parallel speedup**: 3-5x faster than serial execution
- **Audit trail**: Complete history of decisions and rationale
- **Error resilience**: Circuit breakers prevent infinite loops
- **Knowledge accumulation**: SharedKnowledge grows with every run
- **Style consistency**: UX validation prevents fragmented UI
- **Team alignment**: Governance ensures everyone knows the "why"
- **Plan-first workflow**: Planning master ensures concrete plans before execution
- **Version history**: Full traceability from plan through implementation
- **Session continuity**: Resume prompts enable multi-session orchestration without progress loss

---

## The Bottom Line

**Orchestration v2.5 = Industrial-grade autonomous development with formal handoff contracts, lean governance, end-to-end traceability, full SharedKnowledge integration, context hygiene, model-aware sub-agent dispatch, and session continuity across context exhaustion.**

Not just "execute a plan" - this is:
- DoR-gated handoff (formal contract from planner, verified before execution)
- Slim governance (budget + escalation only when plan has DoR — no scope re-statement)
- Execution configuration (map tasks to agents, not re-plan them)
- Planning master integration (concrete plans in, versioned summaries out)
- Pattern reuse (leverage past work)
- Continuous documentation (never lose decisions)
- Coordinated multi-agent execution (parallelism)
- Context hygiene (orchestrator reads zero source code, delegates long reads to haiku sub-agents)
- Model-aware dispatch (right-size model per sub-agent — haiku/sonnet/opus)
- Structured returns (sub-agents return ≤40-line summaries, not transcripts)
- Error recovery (compensation logic)
- UX validation (consistent product)
- Traceability verification (PRD req → task → test → PASS/FAIL)
- ADR promotion (architecture decisions → SharedKnowledge/decisions/)
- Learning loop (improve over time)
- Verification (tests actually run)
- Version control (plans AND implementations are versioned)
- Session continuity (resume prompts generated proactively, never lose progress to context death)

**Follow the workflow. Trust the plan's DoR. Use sub-agents aggressively. Read ZERO source code in the orchestrator. Default to sonnet. Require structured returns. Journal everything. Checkpoint religiously. Reuse patterns. Write lessons. Version deliverables. Generate resume prompts early and often.**

If you skip steps or rationalize shortcuts, you'll lose context, miss bugs, and deliver poor quality.

**The Iron Laws exist for a reason - production systems prove they work.**
