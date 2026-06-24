# Orchestration Master v2.0 - Usage Examples

## Overview

This file shows **exactly** how to invoke the `my-orchestration-master` skill for different scenarios, including the new v2.0 features: Strategic Governance, Pattern Library, Learning Loop, and Fast Track Mode.

---

## Basic Invocation Pattern

```markdown
# User provides:
1. Plan file path (MD format)
2. Optional: Coding preferences file(s)
3. Mode instruction: "work autonomously", "god mode", "YOLO mode"

# Claude invokes skill:
/skill my-orchestration-master

# Claude follows phases:
Phase -1: Strategic Governance (set boundaries)
Phase 0: Validate plan + check SharedKnowledge
Phase 1: Planning (apply patterns)
Phase 2: Implementation (parallel sub-agents)
Phase 3: Testing
Phase 4: Review + UX Validation
Phase 5: Post-Mortem (learning loop)
→ Deliverables created + SharedKnowledge updated
```

---

## Example 1: Full Governance - New Feature in Existing App

### User Prompt:

```
I have a development plan for TopNote. Execute it autonomously.

Plan file: /mnt/c/Projects/SuperTools/docs/plans/export_feature.md

Coding preferences:
- C:\Projects\SuperTools\claude\MY_PERSONAL_CODING_PREFERENCES.md

Work in god mode - I'm going to sleep, expect results in the morning.
```

### What Happens:

```markdown
# Claude loads skill automatically (matches "god mode" trigger)

# Phase -1: Strategic Governance
→ Analyzes plan complexity: UI feature, file operations, testing
→ Risk assessment: Medium (new component, no breaking changes)
→ Creates: docs/master/260201_0230_ExportFeature/GOVERNANCE.md
  - Business objective: Self-service export for users
  - Scope: Export dialog, markdown formatter, menu integration
  - Budget: 3 hours, 80k tokens, 6 agents max
  - Breaking changes: No
→ Decision: PROCEED with Full Governance
→ Creates: CHECKPOINT_BARRIER_Governance.json

# Phase 0: Validate Plan + SharedKnowledge
→ Searches SharedKnowledge/patterns/:
  - ✅ Found: dialog_pattern.md (95% match)
  - ✅ Found: file_operations.md (applicable)
→ Searches SharedKnowledge/lessons/:
  - ✅ Found: 260115_TaskAPI_lessons.md (error handling insights)
→ Loads: CODING_PREFERENCES.md, UX_STYLE_PROFILE.md
→ Validates: Objective clear ✅, 8 checklist items ✅
→ Mode: Feature Integration

# Setup
→ Creates: docs/master/260201_0230_ExportFeature/
→ Creates: JOURNAL_ExportFeature.md (first entry with patterns to apply)

# Phase 1: Planning
→ Spawns sub-agent: "Architect"
→ Architect reads: custom_titlebar.py, settings_dialog.py
→ Architect applies: dialog_pattern.md as template
→ Architect outputs: 8 tasks, 2 parallel groups
→ Creates: CHECKPOINT_BARRIER_Planning.json

# Phase 2: Implementation
→ Group A (parallel):
  - Spawns "Dev Eng #1": Create export_dialog.py (using dialog_pattern.md)
  - Spawns "Dev Eng #2": Implement markdown formatter (using file_operations.md)
→ Group B (after Group A):
  - Spawns "Dev Eng #3": Add hamburger menu item
  - Spawns "Dev Eng #4": Write unit tests
→ All agents reach checkpoint
→ Creates: CHECKPOINT_BARRIER_Implementation.json

# Phase 3: Testing
→ Spawns "Test Engineer": Runs pytest, verifies output
→ Spawns "QA Specialist": Edge case testing (empty notes, special chars)
→ Bugs found: 4 (fixed: 3, deferred: 1)
→ Creates: CHECKPOINT_BARRIER_Testing.json

# Phase 4: Review + UX Validation
→ Spawns "Code Reviewer": Checks quality, plan compliance ✅
→ Spawns "UX Integrator": Validates against UX_STYLE_PROFILE.md
  - Layout rules ✅
  - Color/typography ✅
  - Interaction standards ✅
→ Creates: UX_VALIDATION_ExportFeature.md
→ Verdict: ✅ Ready

# Phase 5: Post-Mortem (Learning Loop)
→ Spawns "Learning Analyst"
→ Creates: LESSONS_LEARNED_ExportFeature.md
  - What worked: Pattern reuse saved 30 min
  - What failed: Initial hardcoded path
  - New pattern: export_dialog_pattern.md
→ Copies to: SharedKnowledge/lessons/260201_ExportFeature_lessons.md
→ Updates: SharedKnowledge/lessons/INDEX.md
→ Creates: SharedKnowledge/patterns/ui/export_dialog_pattern.md

# Deliverables
→ Creates: SUMMARY_ExportFeature.md
→ Creates: TECH_DEBT_ExportFeature.md
→ Updates: CHANGELOG.md, README.md

# Final Message to User:
"Export feature complete. See docs/master/260201_0230_ExportFeature/ for full journal and summary.
Learning: SharedKnowledge updated with new export_dialog_pattern.md"
```

**Time:** ~2.5 hours
**Sub-agents spawned:** 10 (including UX Integrator and Learning Analyst)
**Checkpoints:** 5 (Governance, Planning, Implementation, Testing, Review)
**Context compressions:** 0 (below 50k tokens)
**SharedKnowledge updates:** 1 new pattern, 1 lesson

---

## Example 2: Fast Track Mode - Small Feature

### User Prompt:

```
Quick feature: Add "Copy to Clipboard" button to export dialog.

Plan: Just add a button next to "Save to File" that copies markdown to clipboard.

Low risk, should take ~1 hour. Fast track please.
```

### What Happens:

```markdown
# Phase -1: Fast Track Governance (Lightweight)
→ Creates Feature Brief (not full GOVERNANCE.md):

# Feature Brief
Goal: Add clipboard copy button to export dialog
Target Users: Users who want quick paste into other apps
Risk Level: Low
Max Effort: 1.5 hours, 3 agents
Do Not Break: Export functionality, save button
Stop If: Tests fail on existing functionality
Approved: Yes - Fast Track Mode

# Phase 0: Validate + SharedKnowledge
→ Searches patterns: button_pattern.md (partial match)
→ No lessons for clipboard operations
→ Mode: Fast Track (< 5 tasks, low risk)

# Phase 1: Planning (Light)
→ 3 tasks identified:
  1. Add clipboard button UI
  2. Implement copy logic
  3. Add unit test
→ No parallel groups (too small)

# Phase 2: Implementation
→ Spawns "Dev Eng #1": All 3 tasks serially
→ Follows button_pattern.md for consistency
→ Done in 30 min

# Phase 3: Testing (Light)
→ Spawns "Test Engineer"
→ Unit test passes ✅
→ Manual test: Click → Paste works ✅
→ No required bug count for Fast Track

# Phase 4: Review (Light)
→ Quick review by orchestrator (no separate sub-agent)
→ Code quality ✅
→ No separate UX validation (minimal UI change)

# Phase 5: Post-Mortem (Brief)
→ 3-bullet lessons:
  1. pyperclip library works well for cross-platform
  2. Consider adding copy confirmation toast
  3. Fast Track appropriate for additive features

# Deliverables
→ SUMMARY_ClipboardCopy.md (brief)
→ No TECH_DEBT (clean implementation)

# Final Message:
"Clipboard copy button added. Fast Track complete in 45 min."
```

**Time:** ~45 minutes
**Sub-agents spawned:** 2
**Checkpoints:** 2 (Planning, Implementation)
**SharedKnowledge updates:** Brief lesson only

---

## Example 3: New System from Scratch (Full Governance)

### User Prompt:

```
Build a multi-tenant task management API from this plan.

Plan: /plans/multi_tenant_task_api.md

Team preferences: C:\Projects\SharedKnowledge\standards\CODING_PREFERENCES.md
Personal preferences: C:\Projects\SuperTools\claude\MY_PERSONAL_CODING_PREFERENCES.md

YOLO mode - full autonomous execution.
```

### What Happens:

```markdown
# Phase -1: Strategic Governance
→ Analyzes: Full system build, DB + API + Auth
→ Risk: High (new system, multi-tenant security)
→ Creates GOVERNANCE.md:
  - Business objective: Scalable task management for SaaS customers
  - Scope: API server, PostgreSQL schema, Redis cache, WebSocket events
  - OUT of scope: Frontend, mobile app
  - Budget: 5 hours, 120k tokens, 8 agents max
  - Breaking changes: N/A (new system)
  - Risk tolerance: Row-level security required, 80% test coverage
→ Decision: PROCEED

# Phase 0: Validate + SharedKnowledge
→ Patterns found:
  - api_structure.md (REST conventions)
  - auth_flow.md (JWT authentication)
  - db_migrations.md (schema patterns)
→ Lessons found:
  - 251201_MultiTenant_lessons.md (tenant isolation tips)
→ Validates: 12 checklist items ✅
→ Mode: New System

# Phase 1: Planning (Architecture Design)
→ Spawns "Architect" sub-agent
→ Architect designs using patterns:
  - Project structure: /api-server/{src,tests,config}
  - DB schema: Users, Tenants, Tasks (with RLS)
  - API routes: /auth, /tasks, /tenants
  - WebSocket: task.created, task.updated
→ Task breakdown: 15 tasks, 4 parallel groups

# Phase 2: Implementation (Heavy Parallelization)
→ Group A (4 agents in parallel):
  - Dev #1: Project scaffold (uses api_structure.md pattern)
  - Dev #2: Database schema + migrations (uses db_migrations.md)
  - Dev #3: JWT auth middleware (uses auth_flow.md)
  - Dev #4: User model + routes
→ Group B (3 agents in parallel):
  - Dev #5: Task model + CRUD
  - Dev #6: Tenant isolation logic (applies lesson from 251201)
  - Dev #7: WebSocket server setup
→ Group C (2 agents in parallel):
  - Dev #8: Integration tests
  - Dev #9: API documentation (Swagger)

# Context Compression (Triggered at 52k tokens)
→ Spawns "Context Curator"
→ Archives 48 old journal entries
→ Updates CONTEXT_SNAPSHOT.json
→ Token count: 52k → 14k (73% reduction)

# Phase 3: Testing
→ Test Engineer: npm test (24 unit tests ✅)
→ QA Specialist: Finds 6 bugs (5 fixed, 1 deferred)
→ Integration Tester: End-to-end API flow ✅
→ Security check: RLS working ✅

# Phase 4: Review + UX Validation
→ Code Reviewer: Quality ✅, Standards ✅
→ UX Integrator: N/A (no UI in this project)
→ Architecture audit: Clean separation, good error handling

# Phase 5: Post-Mortem
→ Creates LESSONS_LEARNED_TaskAPI.md:
  - What worked: Pattern reuse saved 2+ hours
  - What failed: Initial Redis connection pooling wrong
  - New rules: Always test tenant isolation with multiple accounts
  - New pattern: multi_tenant_api_pattern.md
→ Copies to SharedKnowledge
→ Creates new pattern: patterns/backend/multi_tenant_api_pattern.md

# Deliverables
→ SUMMARY_TaskAPI.md
→ TECH_DEBT_TaskAPI.md
→ ARCHITECTURE_TaskAPI.md (complex system → diagram included)
→ All 12 checklist items ✅

# Final Output:
"Multi-tenant API complete. 15 tasks done, 24 tests passing.
SharedKnowledge: New multi_tenant_api_pattern.md created.
See docs/master/260201_1000_TaskAPI/"
```

**Time:** ~4.5 hours
**Sub-agents spawned:** 18
**Checkpoints:** 5
**Context compressions:** 2
**SharedKnowledge updates:** 1 new pattern, 1 lesson, 1 rule update

---

## Example 4: Plan Needs Clarification (Governance Fails)

### User Prompt:

```
Execute this plan: /plans/add_feature_X.md

God mode.
```

### What Happens:

```markdown
# Phase -1: Strategic Governance
→ Attempts to create GOVERNANCE.md
→ FAILS: Cannot determine governance without understanding feature

# Phase 0: Validate Plan
→ Reads /plans/add_feature_X.md
→ Checks:
  - Objective: "Add Feature X" (too vague ❌)
  - Checklist: Missing critical details ❌
  - Tech approach: Not specified ❌

# Validation Result: PLAN UNCLEAR - GOVERNANCE CANNOT BE CREATED

Claude asks user:
---
**Plan validation failed.** The plan is too high-level to execute.

I cannot create governance boundaries without understanding:

1. **What is "Feature X"?** (no description provided)
2. **Who is this for?** (target users unclear)
3. **What problem does it solve?** (business objective missing)
4. **What files/components should be modified?** (scope undefined)
5. **How risky is this?** (can't assess without understanding)
6. **What testing approach should be used?** (no acceptance criteria)

**I need this information to create proper governance.**

Please provide:
- Detailed description of Feature X
- User stories or workflows
- UI mockups (if applicable)
- Success criteria
- Risk assessment (breaking changes?)

Once we refine the plan, I'll create:
`/plans/add_feature_X_REFINED_260201_1430.md`

Then restart Claude Code with the refined plan.

**I will NOT proceed without proper governance. This prevents wasted effort and scope creep.**
---

# STOPS EXECUTION - Does NOT create journal or spawn agents
```

**Key Point:** Orchestration v2.0 requires governance BEFORE execution. If plan is unclear, governance cannot be created, and execution halts.

---

## Example 5: Governance Boundary Violation (Escalation)

### Scenario: Implementation Exceeds Scope

```markdown
# GOVERNANCE.md says:
Scope: Export dialog only
Breaking Changes: No
Out of Scope: Config schema changes

# Phase 2: Implementation
→ Dev Eng #3 discovers: "Export needs new config field for default path"
→ This would change config schema (OUT OF SCOPE per governance)

# Orchestrator detects violation:

### [YYYY-MM-DD HH:MM {elapsed}] {ctx:XX%} GOVERNANCE BOUNDARY ALERT

Task: "Implement default export path"
Agent: Dev Eng #3
Issue: Requires config schema change (GOVERNANCE says OUT OF SCOPE)

Options:
1. Implement without config (use hardcoded default) ← Within scope
2. Escalate to user for governance amendment

Decision: ESCALATE TO USER

---
**Governance Boundary Reached**

Dev Eng #3 wants to add a config field for default export path.

This is currently OUT OF SCOPE in GOVERNANCE.md.

Options:
A) Proceed with hardcoded default (stays within scope)
B) Amend governance to allow config change (requires your approval)
C) Defer to future version

Which option?
---

# Waits for user response before continuing
```

**Key Point:** Orchestration v2.0 enforces governance. Scope creep triggers escalation.

---

## Example 6: Learning Loop in Action

### Post-Mortem Creates New Pattern

```markdown
# Phase 5: Post-Mortem

→ Learning Analyst reviews execution:
  - Dev Eng #2 created elegant solution for file versioning
  - This pattern doesn't exist in SharedKnowledge
  - Solution is generalizable

→ Creates LESSONS_LEARNED_FileVersioning.md:

## Patterns to Create
1. **NEW: file_versioning_pattern.md**
   - Problem: Need to version exported files without overwriting
   - Solution: Append timestamp, maintain index, cleanup old versions
   - Implementation: See export_dialog.py lines 45-89
   - Constraints: Max 10 versions, configurable retention
   - Anti-patterns: Don't use incrementing integers (breaks on deletion)

→ Orchestrator creates pattern file:

# Creating new pattern in SharedKnowledge
File: C:\Projects\SharedKnowledge\patterns\backend\file_versioning_pattern.md

---
# File Versioning Pattern

## Problem Context
Applications need to save multiple versions of user files without overwriting.

## When to Use
- Export features with versioning
- Backup systems
- Document history

## Solution
Use timestamp-based naming with index tracking...
[Full pattern content]

## Reference Implementation
- TopNote export: topnote/ui/export_dialog.py:45-89

## Anti-Patterns
- Don't use incrementing integers (gaps on deletion)
- Don't store in flat directory (use YYYY/MM structure)
---

→ Updates SharedKnowledge/patterns/INDEX.md:
  - Added: backend/file_versioning_pattern.md

# Final journal entry:
"Learning Loop: Created file_versioning_pattern.md from this run.
Future exports can reuse this pattern instead of redesigning."
```

---

## Example 7: Multi-Repo with UX Validation

### User Prompt:

```
Integrate STT transcript display across two repos.

Plan: /plans/stt_transcript_ui.md

Working repos:
- Primary: C:\Projects\_Sparki\frontend (UI changes)
- Reference: C:\Projects\Sparkco\frontend\AAA (existing transcript logic)

This adds visible UI - make sure it matches our design system.

God mode.
```

### What Happens:

```markdown
# Phase -1: Governance
→ Creates GOVERNANCE.md:
  - Scope: UI component for transcript display in Primary repo
  - Style requirement: MUST match UX_STYLE_PROFILE.md
  - Breaking changes: No
  - UX Validation: MANDATORY (UI feature)

# Phase 0 + SharedKnowledge
→ Loads: UX_STYLE_PROFILE.md (typography, colors, spacing)
→ Found: transcript_display_pattern.md (from Reference repo docs)
→ Mode: Feature Integration (multi-repo)

# Phase 1: Planning
→ Architect analyzes both repos:
  - Primary: Needs TranscriptPanel component
  - Reference: Has working transcript logic to port
→ Style constraints from UX_STYLE_PROFILE.md:
  - Font: System UI, 14px body
  - Colors: Neutral-700 for text, Primary-500 for highlights
  - Spacing: 16px padding, 8px gaps

# Phase 2: Implementation
→ Dev Eng #1: Port transcript logic
→ Dev Eng #2: Create TranscriptPanel component (applying style rules)
→ Dev Eng #3: Style integration tests

# Phase 4: Review + UX Validation (CRITICAL)
→ Spawns "UX Integrator" sub-agent
→ UX Integrator compares TranscriptPanel to UX_STYLE_PROFILE.md:

### UX Validation Report

## Component: TranscriptPanel

### Typography
- ✅ Font family: System UI (matches profile)
- ✅ Body text: 14px (matches profile)
- ⚠️ Timestamp: 11px (profile says 12px minimum)
  → FIX REQUIRED: Increase to 12px

### Colors
- ✅ Text color: Neutral-700
- ✅ Highlight: Primary-500
- ✅ Background: Neutral-50

### Spacing
- ✅ Padding: 16px
- ⚠️ Line gap: 6px (profile says 8px)
  → FIX REQUIRED: Increase to 8px

### Required Fixes
1. Timestamp font size: 11px → 12px
2. Line gap: 6px → 8px

## Verdict
❌ UX NEEDS FIXES - 2 issues found

→ Dev Eng #2 fixes issues
→ Re-validates: ✅ UX APPROVED

# Phase 5: Post-Mortem
→ Lesson: "Always check UX_STYLE_PROFILE.md spacing rules early"
→ Updates: Added spacing checklist to transcript_display_pattern.md

# Final Output:
"Transcript UI integrated. UX validated - 2 issues fixed before delivery.
See UX_VALIDATION_TranscriptUI.md for full compliance report."
```

---

## Directory Structure After v2.0 Execution

```
<project_root>/
├── docs/
│   └── master/
│       └── 260201_1430_ExportFeature/
│           ├── GOVERNANCE.md                    # NEW: Phase -1 output
│           ├── JOURNAL_ExportFeature.md
│           ├── JOURNAL_ARCHIVE_260201_1600.md
│           ├── CONTEXT_SNAPSHOT.json
│           ├── CHECKPOINT_BARRIER_Governance.json   # NEW
│           ├── CHECKPOINT_BARRIER_Planning.json
│           ├── CHECKPOINT_BARRIER_Implementation.json
│           ├── CHECKPOINT_BARRIER_Testing.json
│           ├── UX_VALIDATION_ExportFeature.md   # NEW: Phase 4 output
│           ├── SUMMARY_ExportFeature.md
│           ├── TECH_DEBT_ExportFeature.md
│           └── LESSONS_LEARNED_ExportFeature.md # NEW: Phase 5 output
├── topnote/
│   └── ui/
│       ├── export_dialog.py         # NEW
│       └── ...
└── tests/
    └── test_export.py              # NEW

# SharedKnowledge (separate repo - also updated):
C:\Projects\SharedKnowledge\
├── patterns/
│   └── ui/
│       └── export_dialog_pattern.md    # NEW: Created from this run
├── lessons/
│   ├── INDEX.md                        # UPDATED
│   └── 260201_ExportFeature_lessons.md # NEW: Copied from project
└── standards/
    └── CODING_PREFERENCES.md           # Possibly updated with new rules
```

---

## When NOT to Use Orchestration

**Don't use for:**
- Single file edits (< 30 min)
- Exploratory questions ("How does X work?")
- Code reviews (use code-review skill)
- Quick bug fixes (use systematic-debugging skill)
- Research tasks (no concrete plan)

**Use Fast Track Mode for:**
- Small features (< 2 hours)
- Low-risk additions
- Well-scoped tasks
- Single contributor work

**Use Full Governance for:**
- Complex features (> 2 hours)
- Multi-person coordination
- High-risk changes
- New system development
- Breaking changes

---

## Version Comparison

| Feature | v1.0 | v2.0 |
|---------|------|------|
| **Governance** | None | Phase -1 (Full + Fast Track) |
| **Pattern Library** | None | SharedKnowledge integration |
| **Learning Loop** | None | Phase 5 (Post-Mortem) |
| **UX Validation** | None | Phase 4 (UX Integrator) |
| **Phases** | 0-4 | -1 to 5 |
| **Checkpoints** | 3-4 | 5-6 |
| **Knowledge Updates** | None | Automatic pattern/lesson creation |
| **Team Support** | Basic | Full workflow rules |
| **Versioning** | None | Semantic versioning in headers |

---

## Bottom Line

**Orchestration v2.0 = Industrial-grade autonomous development with institutional learning.**

- Provide plan + preferences + "god mode"
- Claude establishes governance boundaries FIRST
- Claude reuses patterns from SharedKnowledge
- Claude executes with full audit trail
- Claude validates UX consistency
- Claude creates lessons for future runs
- Knowledge accumulates across your team

**Quality + Speed + Transparency + Learning = Orchestration Master v2.0**
