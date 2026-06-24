---
name: my-planning-master
description: Use when creating implementation plans from PRD/research docs. Triggers: "plan this", "create plan", "plan the approach", "planning session", "master flow plan", or when given PRD/research files to plan from.
planning_version: "1.3.0"
compatibility:
  claude_code: ">=2.1"
  tools: [Glob, Grep, Read, Task, AskUserQuestion, WebSearch, WebFetch]
---

# Planning Master v1.3 - Iterative Implementation Planning

## Overview

**Core Principle:** Transform PRD requirements and research findings into concrete, actionable implementation plans through iterative collaboration with the user (dev team member).

This is NOT "read docs and generate a plan." This is **collaborative technical planning** with:
- Deep document ingestion (PRD, research, prior plans)
- Scope alignment (lightweight governance for planning boundaries)
- Deep codebase exploration (understand architecture before planning)
- Iterative Q&A (clarify, resolve, refine - multiple rounds)
- Conflict detection (between requirements, research findings, and codebase reality)
- Version-controlled plan output (plans evolve, history preserved)
- Session continuity (progressive saves + resume state for context exhaustion recovery)
- File-level specificity (not vague - name exact files, components, patterns)

**The planner is a COLLABORATOR, not an order-taker.** It challenges assumptions, surfaces hidden complexity, resolves ambiguity, and ensures the plan is executable before handing off to the orchestration master.

**Output:** `20-00_PLANNING_v{major}.{minor}.md` - A versioned, comprehensive implementation plan ready for execution by `/my-orchestration-master`.

---

## Relationship with Other Skills

```
┌────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT PIPELINE                     │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  /my-research-master          →  00-00_PRD*.md + 10-00_RESEARCH*.md     │
│       ↓                                                    │
│  /my-planning-master   →  20-00_PLANNING_v{X.Y}.md            │
│       ↓                                                    │
│  /my-orchestration-master → 30-00_IMPLEMENTATION-SUMMARY_v*.md│
│                            + all execution deliverables    │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

- **Research** (`/my-research-master`) produces the knowledge foundation
- **Planning** (THIS SKILL) produces the actionable plan
- **Orchestration** (`/my-orchestration-master`) executes the plan

The planner READS research output. The orchestrator READS planning output. Each skill has a clear input/output contract.

---

## When to Use

**Use when:**
- User has PRD + Research docs and needs an implementation plan
- User says "plan this", "create a plan", "plan the approach"
- User provides `00-00_PRD*.md` and/or `10-00_RESEARCH*.md` files
- Before invoking `/my-orchestration-master` for complex features
- Re-planning after scope changes (previous plan exists)
- Multi-repo feature needs coordinated planning
- Technical approach needs iterative refinement with user

**Don't use when:**
- Single trivial task (< 30 min, no planning needed)
- User already has a detailed plan and wants execution → use `/my-orchestration-master`
- Exploratory research phase → use `/my-research-master`
- Quick bug fix → use `/systematic-debugging`
- User just wants to brainstorm ideas → use `/brainstorming`

---

## The Iron Laws of Planning

```
1. INGEST ALL INPUT DOCS FIRST - Never plan without reading everything provided
2. EXPLORE THE CODEBASE DEEPLY - Plans without codebase context are fantasies
3. ASK BEFORE ASSUMING - Ambiguity resolved by questions, not guesses
4. ITERATE UNTIL CONCRETE - Vague plans are useless plans
5. VERSION EVERYTHING - Plans evolve, history must be preserved
6. DETECT CONFLICTS EARLY - Between PRD, research, and codebase reality
7. FILE-LEVEL SPECIFICITY - Name exact files, lines, components to change
8. RESPECT RESEARCH FINDINGS - Don't contradict the research without justification
9. SCOPE ALIGNMENT BEFORE DETAILS - Agree on boundaries before diving deep
10. PLAN FOR THE ORCHESTRATOR - Output must be directly executable by /my-orchestration-master
11. SAVE PROGRESSIVELY - Write plan to disk after each phase, not just at the end
```

**Violating any Iron Law = Stop and restart correctly.**

---

## Complexity Tiers (Auto-Detected)

Every plan is assigned a complexity tier. The tier determines which plan sections are mandatory, how deep the DoR checklist goes, and what governance the orchestrator should use.

**Auto-detection heuristics (dev can override):**

| Tier | Tasks | Repos | Risk | Est. Time | Governance |
|------|-------|-------|------|-----------|------------|
| **Quick** | < 5 | 1 | Low | < 2h | Auto-approve Feature Brief |
| **Standard** | 5-15 | 1-2 | Medium | 2-8h | Full (slim when DoR present) |
| **Complex** | 15+ | 2+ | High | 8h+ | Full + ADR promotion + arch review |

**What each tier requires:**

| Section | Quick | Standard | Complex |
|---------|-------|----------|---------|
| Scope Alignment | Minimal | Full | Full |
| Architecture Decisions (ADR format) | Optional | Required | Required + promote to SharedKnowledge |
| Traceability Matrix | Skip | Required | Required |
| Testing Strategy (extended) | Unit only | Unit + Integration | Unit + Integration + Regression + Perf/Security |
| Risk Register + Rollback | Skip | Required | Required + Dependency Risks |
| DoR Checklist | Mandatory tier only | Full Mandatory + Standard | Full all tiers |
| Orchestrator Execution Config | Minimal | Full | Full + cross-repo coord |
| Peer review of plan | Self-approve | 1 peer | 2 peers |

**Record the tier in the plan metadata header.**

---

## CRITICAL: How This Skill Works

**This skill is invoked by YOU (the planner), working WITH the user.**

**Workflow:**
1. **User gives you input docs** → You load this skill
2. **You ingest all documents** → Understand requirements, research, constraints
3. **You explore the codebase** → Understand architecture, patterns, integration points
4. **You ask iterative questions** → Clarify approach, resolve conflicts, align scope
5. **You synthesize the plan** → Create versioned planning document
6. **User reviews the plan** → Approves, requests changes, or triggers re-planning

**DO NOT:**
- ❌ Skip reading input documents
- ❌ Generate a plan without asking questions first
- ❌ Make architectural decisions without user alignment
- ❌ Produce vague plans ("implement the feature")
- ❌ Ignore codebase patterns and conventions
- ❌ Contradict research findings without explicit justification
- ❌ Start implementation (that's the orchestrator's job)

**YOU are the planner. The user is the decision-maker. Your job is to surface decisions, not make them unilaterally.**

---

## Input Acquisition

### Required Inputs

1. **PRD Document** (`00-00_PRD*.md`)
   - Product Requirements Document
   - Location: `<repo>/docs/master/<timestamp>_<feature>/00-00_PRD*.md`
   - Contains: Requirements, constraints, user stories, acceptance criteria

2. **Research Document** (`10-00_RESEARCH*.md`)
   - Technical research findings
   - Location: `<repo>/docs/master/<timestamp>_<feature>/10-00_RESEARCH*.md`
   - Contains: Industry patterns, codebase patterns, tradeoffs

### Optional Inputs

3. **Previous Plan** (`20-00_PLANNING_v*.md`)
   - Existing plan to iterate on (re-planning scenario)
   - Used to understand what's changing and increment version

4. **Additional Documents**
   - Architecture docs, design specs, wireframes
   - Constraints docs, compliance requirements
   - User-provided notes or instructions

### Input Validation

Before proceeding, validate:

- [ ] PRD document exists and is readable
- [ ] Research document exists and is readable
- [ ] All referenced repos/paths are accessible
- [ ] If re-planning: Previous plan version identified
- [ ] Feature folder identified: `<repo>/docs/master/<timestamp>_<feature>/`

**If input is missing or invalid:**
1. Use `AskUserQuestion` to request missing documents
2. **STOP - do not plan without proper inputs**

---

## The Planning Process

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PLANNING MASTER v1.0                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────┐                                       │
│  │  Receive Input Documents │                                       │
│  └───────────┬──────────────┘                                       │
│              │                                                      │
│              ▼                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 0: DOCUMENT INGESTION & GAP ANALYSIS                   │   │
│  │ • Read PRD, Research, prior plans                            │   │
│  │ • Identify gaps, ambiguities, conflicts                      │   │
│  │ • Surface hidden complexity                                  │   │
│  └───────────┬──────────────────────────────────────────────────┘   │
│              │                                                      │
│              ▼                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 1: SCOPE ALIGNMENT                                     │   │
│  │ • Lightweight governance for planning boundaries              │   │
│  │ • Agree on what's in/out of scope                            │   │
│  │ • Identify constraints and risk areas                        │   │
│  │ • Set planning depth expectations                            │   │
│  └───────────┬──────────────────────────────────────────────────┘   │
│              │                                                      │
│              ▼                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 2: CODEBASE EXPLORATION                                │   │
│  │ • Deep-read architecture and key files                       │   │
│  │ • Discover patterns, conventions, integration points         │   │
│  │ • Map existing components to planned changes                 │   │
│  │ • Identify reusable code and potential conflicts              │   │
│  └───────────┬──────────────────────────────────────────────────┘   │
│              │                                                      │
│              ▼                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 3: ITERATIVE Q&A WITH USER                ◄──────┐    │   │
│  │ • Ask structured questions per category           │      │    │   │
│  │ • Resolve conflicts between PRD/research/code     │      │    │   │
│  │ • Clarify technical approach decisions             │      │    │   │
│  │ • Surface trade-offs for user decision             │      │    │   │
│  │ • Repeat until plan is concrete                    ──────┘    │   │
│  └───────────┬──────────────────────────────────────────────────┘   │
│              │                                                      │
│              ▼                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ PHASE 4: PLAN SYNTHESIS                                      │   │
│  │ • Create versioned 20-00_PLANNING_v{X.Y}.md                    │   │
│  │ • Detailed task breakdown with file-level specificity        │   │
│  │ • Dependency mapping and parallel group identification       │   │
│  │ • Testing strategy and risk mitigation                       │   │
│  │ • Present to user for review                                 │   │
│  └───────────┬──────────────────────────────────────────────────┘   │
│              │                                                      │
│              ▼                                                      │
│  ┌──────────────────┐                                               │
│  │   PLAN DELIVERED  │                                               │
│  │  Ready for /orca  │                                               │
│  └──────────────────┘                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0: Document Ingestion & Gap Analysis

**Purpose:** Thoroughly understand ALL input before doing anything else.

### Step 1: Read All Input Documents

Read every provided document completely. Do NOT skim.

**For each document, extract:**
- Key requirements (functional and non-functional)
- Constraints and limitations
- Technical patterns and approaches discovered
- Open questions already identified
- Acceptance criteria
- Out-of-scope items

### Step 1b: Check Prior Decisions

Search `C:\Projects\SharedKnowledge\decisions\` for ADRs relevant to this feature domain. Prior architecture decisions may constrain or inform the current plan. Note any applicable ADRs in findings.

### Step 2: Gap Analysis

After reading everything, identify:

1. **Requirement Gaps** - Things the PRD implies but doesn't specify
   - Missing acceptance criteria
   - Undefined edge cases
   - Unclear user flows
   - Unspecified error handling

2. **Research Gaps** - Areas the research didn't cover
   - Missing technical approach for specific requirements
   - Unresolved tradeoffs
   - Libraries/tools not evaluated
   - Codebase patterns not investigated

3. **Conflicts** - Contradictions between documents
   - PRD requirement vs research finding
   - Research recommendation vs codebase constraint
   - Requirement A vs Requirement B tension
   - Time/scope/quality triangle conflicts

### Step 3: Hidden Complexity Detection

Look for requirements that SEEM simple but are ACTUALLY complex:

```markdown
⚠️ COMPLEXITY ALERTS:

1. "Support real-time updates"
   → Hidden: WebSocket lifecycle, reconnection, conflict resolution, throttling

2. "Add user preferences"
   → Hidden: Storage strategy, migration, defaults, cross-device sync

3. "Make it responsive"
   → Hidden: Layout breakpoints, touch interactions, performance on mobile
```

**Surface these early - they are planning land mines.**

### Journal Entry (Phase 0):

```markdown
### Phase 0: Document Ingestion

Documents Read:
- 00-00_PRD_feature-name.md (requirements: 12 functional, 4 non-functional)
- 10-00_RESEARCH.md (patterns: 6 industry, 4 codebase)
- Previous plan: 20-00_PLANNING_v1.2.md (if re-planning)

Gap Analysis:
- 3 requirement gaps identified (listed below)
- 1 research gap (no codebase analysis of X component)
- 2 conflicts detected (PRD says X, research says Y)

Complexity Alerts:
- Requirement #4 appears simple but involves 3 subsystems
- Integration point with service Z is undocumented

Next: Phase 1 (Scope Alignment)
```

---

## Phase 1: Scope Alignment (Lightweight Governance)

**Purpose:** Align on planning boundaries BEFORE deep technical planning. This is NOT full governance (that happens in the orchestrator). This is agreement on WHAT we're planning.

### Scope Alignment Questions

Use `AskUserQuestion` to align on:

1. **Planning Scope**
   - "Based on the PRD, which requirements are highest priority for this planning round?"
   - "Should we plan for the full feature or a specific phase/subset?"
   - "Are there requirements we should defer to a future plan?"

2. **Technical Constraints**
   - "Are there technology choices already decided? (libraries, frameworks, patterns)"
   - "Are there files/modules that should NOT be modified?"
   - "Any performance budgets or technical limits?"

3. **Integration Boundaries**
   - "How many repos are involved? Which is primary?"
   - "Are there external APIs or services we're depending on?"
   - "Are there team boundaries (who owns what code)?"

4. **Planning Depth**
   - "How detailed should the plan be? (high-level phases vs file-level tasks)"
   - "Should the plan include testing strategy?"
   - "Do you need architecture diagrams or just task breakdown?"

### Scope Alignment Document

Record alignment in the planning document header:

```markdown
## Scope Alignment

### In Scope (This Plan)
- [Agreed items]

### Out of Scope (Deferred)
- [Explicitly deferred items]

### Constraints
- [Technical limitations agreed upon]
- [Libraries/patterns already decided]

### Planning Depth
- [Level of detail agreed upon]

### Repos Involved
- Primary: [path]
- Secondary: [path] (if applicable)
```

---

## Phase 2: Codebase Exploration

**Purpose:** Understand the actual codebase deeply enough to produce file-level plans. Plans without codebase context are fantasies.

### What to Explore

**Spawn sub-agents** (`Task` tool with `Explore` agent) for parallel exploration:

1. **Architecture Discovery**
   - Project structure and key directories
   - State management patterns
   - Component/module organization
   - Service layer architecture
   - Configuration and environment setup

2. **Pattern Discovery**
   - How similar features are currently implemented
   - Naming conventions (files, functions, components)
   - Import patterns and module boundaries
   - Error handling patterns
   - Testing patterns and test structure

3. **Integration Point Analysis**
   - Files that will need modification
   - APIs and services the feature will interact with
   - Shared utilities and helpers available
   - Event systems, stores, and data flow
   - Build/config files that may need changes

4. **SharedKnowledge Check (via Sub-Agent)**

   **Dispatch via `Agent` tool with `subagent_type: "sk-scout"`:**

   ```
   Scan SharedKnowledge for content relevant to: [feature being planned].
   Also check governance/ for applicable governance templates.
   ```

   The `sk-scout` agent definition handles all folder scanning, format, and constraints automatically (haiku, read-only, 8 SK folders, max 30 lines). This protects the main planning context from unnecessary content.

### Exploration Output

Document findings for use in Q&A and plan synthesis:

```markdown
## Codebase Analysis

### Architecture Summary
- [Key patterns discovered]
- [State management approach]
- [Component organization]

### Relevant Existing Code
- [Files/components that will be modified or extended]
- [Utilities/helpers available for reuse]
- [Patterns to follow for consistency]

### Integration Points
- [Where new code connects to existing systems]
- [APIs, events, stores involved]

### SharedKnowledge Findings
- Patterns applicable: [list]
- Lessons relevant: [list]
- Prior ADRs relevant: [list from decisions/]
- Standards to follow: [list]
- Guides referenced: [list from guides/]
- Runbooks with constraints: [list from runbooks/]
- Governance templates: [applicable template from governance/]

### Concerns Discovered
- [Potential technical issues found during exploration]
- [Code areas that may resist the planned changes]
- [Missing infrastructure or utilities]
```

---

## Phase 3: Iterative Q&A with User

**Purpose:** This is the CORE of the planning master. Collaborate with the user through multiple rounds of structured questions to resolve every ambiguity and make every decision needed for a concrete plan.

### Q&A Framework

**Round Structure:**
1. Present findings/concerns from previous phase
2. Ask 2-4 focused questions per round (using `AskUserQuestion`)
3. Process answers
4. If new questions arise → another round
5. If all questions resolved → proceed to synthesis

**Maximum Rounds:** No hard limit, but typically 3-6 rounds. Stop when:
- All requirement gaps are filled
- All conflicts are resolved
- All technical decisions are made
- Plan can be written at file-level specificity
- User explicitly says "enough questions, write the plan"

### Question Categories

#### Category 1: Technical Approach Decisions

Questions about HOW to implement specific requirements:

```markdown
"The PRD requires real-time collaboration. The research identified three approaches:
1. WebSocket with operational transforms
2. WebSocket with CRDT
3. Polling with last-write-wins

Your codebase already uses WebSocket (SpatialWebsocketV2) with 33ms throttling.

Which approach aligns with your vision? Consider:
- Approach 1: Most mature, but complex to implement
- Approach 2: Better conflict resolution, growing ecosystem
- Approach 3: Simplest, but poor user experience for fast editors"
```

#### Category 2: Conflict Resolution

Questions about contradictions between inputs:

```markdown
"I found a conflict between the PRD and the codebase:

PRD says: 'Use a new dedicated store for feature state'
Codebase pattern: Similar features extend existing Vuex store modules

Options:
A) Follow PRD (new store) - cleaner separation but breaks convention
B) Follow codebase convention (extend Vuex) - consistent but couples state
C) Hybrid - new ReactiveStore that syncs with Vuex (matches newer pattern)

Which approach do you prefer?"
```

#### Category 3: Scope Refinement

Questions about what to include/exclude:

```markdown
"The PRD lists 12 requirements. Based on codebase exploration, I estimate:
- Requirements 1-8: Well-scoped, clear implementation path
- Requirement 9: Needs new infrastructure (event bus redesign)
- Requirements 10-12: Depend on requirement 9

Do you want to:
A) Plan all 12 (larger scope, req 9 is foundational work)
B) Plan 1-8 now, defer 9-12 to next planning cycle
C) Plan 1-8 + lightweight version of 9 (minimal infrastructure)"
```

#### Category 4: Architecture Decisions

Questions about structural choices:

```markdown
"This feature touches 3 existing components and needs 2 new ones.

I see two structural approaches:
A) Add to existing component directory (src/components/room/)
   - Pro: Follows current structure
   - Con: Directory already has 45 files

B) Create a feature module (src/features/collaboration/)
   - Pro: Clean separation, easier to test
   - Con: New pattern, some import path changes

Your recent features (e.g., broadcast) used approach B. Prefer to continue that pattern?"
```

#### Category 5: Risk and Edge Cases

Questions about failure modes:

```markdown
"The research identified these edge cases for this feature:
1. User disconnects during sync → data loss risk
2. Concurrent edits by 10+ users → performance degradation
3. Large content (>1MB) → memory pressure on client

How should we handle these?
A) Address all in v1 (more robust, longer timeline)
B) Handle #1 (critical), defer #2 and #3 (acceptable for initial release)
C) Handle #1 and #2, defer #3 (balanced approach)"
```

#### Category 6: Testing Strategy

Questions about quality assurance approach:

```markdown
"What testing approach should the plan include?
A) Unit tests only (fastest, minimum coverage)
B) Unit + integration tests (solid coverage)
C) Unit + integration + E2E tests (comprehensive, longer implementation)

Note: Your codebase uses Vitest for unit tests. Integration/E2E infrastructure may need setup."
```

### Conflict Resolution Protocol

When PRD, research, and codebase reality disagree:

1. **Surface the conflict explicitly** - Show the user exactly what contradicts what
2. **Present options with tradeoffs** - Never pick for the user
3. **Reference research findings** - Use data, not opinions
4. **Respect codebase patterns** - Consistency has value
5. **Document the decision** - Record WHY the user chose their approach

### When to Stop Iterating

**Stop and proceed to synthesis when ALL of these are true:**
- [ ] Every PRD requirement has a clear technical approach
- [ ] All conflicts between inputs are resolved
- [ ] Architecture decisions are made (where new code lives, patterns to use)
- [ ] Scope is agreed (in/out boundaries clear)
- [ ] Risk areas are acknowledged and handling decided
- [ ] Testing strategy is aligned
- [ ] User explicitly approves moving to plan synthesis

**If user says "just write the plan" before all are resolved:**
- Document unresolved items as "OPEN QUESTIONS" in the plan
- Mark affected tasks as "NEEDS CLARIFICATION"
- Proceed with best-guess approach, clearly flagged

---

## Phase 4: Plan Synthesis

**Purpose:** Transform all gathered information into a concrete, versioned implementation plan.

### Version Determination

**If no previous plan exists:**
- Create `20-00_PLANNING_v1.0.md`

**If previous plan exists (re-planning):**

| Scenario | Version Change | Example |
|----------|---------------|---------|
| Minor refinements, clarifications | Increment minor | v1.0 → v1.1 |
| Added/removed tasks, same scope | Increment minor | v1.1 → v1.2 |
| Significant scope change | Increment major | v1.2 → v2.0 |
| Full rewrite / different approach | Increment major | v2.0 → v3.0 |
| User explicitly requests major bump | Increment major | v1.5 → v2.0 |

**Auto-detection heuristics:**
- If >50% of tasks changed → suggest major increment
- If <50% of tasks changed → suggest minor increment
- If scope boundaries changed → suggest major increment
- Always confirm with user before finalizing version

### Plan Document Structure (20-00_PLANNING_v{X.Y}.md)

```markdown
# Implementation Plan: [Feature Name]

**Version:** v{X.Y}
**Created:** [YYYY-MM-DD HH:MM]
**Updated:** [YYYY-MM-DD HH:MM] (if re-planned)
**Planning Skill:** my-planning-master v1.3
**Status:** [Draft / Approved / Superseded by v{X.Y+1}]
**Complexity Tier:** [Quick / Standard / Complex]
**Estimated Total Effort:** [T-shirt size: S/M/L/XL] ([N] hours)

## Input Documents
- PRD: [path to 00-00_PRD*.md]
- Research: [path to 10-00_RESEARCH*.md]
- Previous Plan: [path to previous version, if any]
- Prior ADRs: [relevant decisions from SharedKnowledge/decisions/]
- Guides referenced: [relevant guides from SharedKnowledge/guides/]
- Runbook constraints: [relevant runbooks from SharedKnowledge/runbooks/]
- Additional: [other documents referenced]

## Scope Alignment

### In Scope
- [Agreed items from Phase 1]

### Out of Scope
- [Deferred items]

### Constraints
- [Technical constraints]
- [Timeline constraints]
- [Resource constraints]

## Architecture Decisions

### ADR-001: [Title]
- **Status:** [Accepted / Superseded / Deprecated]
- **Context:** [Why this decision was needed]
- **Options Considered:** [What was evaluated, with tradeoffs]
- **Decision:** [What was chosen]
- **Consequences:** [What this means for implementation]
- **Promote to SharedKnowledge:** [Yes / No]

### ADR-002: [Title]
...

## Codebase Context

### Existing Patterns Applied
- [Pattern name] → [How it applies]
- [SharedKnowledge pattern] → [How it applies]

### Files to Modify
- [file path] - [What changes and why]

### New Files to Create
- [file path] - [Purpose]

### Integration Points
- [System/component] → [How new code connects]

## Implementation Plan

### Phase 1: [Phase Name]
**Estimated Effort:** [time estimate]
**Dependencies:** [what must be done first]

#### Task 1.1: [Task Name]
- **Description:** [What to do]
- **Files:** [Exact files to modify/create]
- **Approach:** [Technical approach, patterns to follow]
- **Acceptance Criteria:** [How to verify completion]
- **Verification Method:** [How orchestrator proves this is done - test name, command, manual check]
- **Estimated Effort:** [time]

#### Task 1.2: [Task Name]
...

### Phase 2: [Phase Name]
**Dependencies:** Phase 1 complete
...

## Parallel Execution Groups

Groups that can be executed simultaneously by the orchestrator:

```
Group A (parallel): Task 1.1, Task 1.2, Task 1.3
Group B (after A):  Task 2.1, Task 2.2
Group C (after B):  Task 3.1
```

## Testing Strategy

### Unit Tests
- [What to test, which files]

### Integration Tests
- [What to test, which flows]

### Regression Scope (Standard + Complex tiers)
- [Existing behavior to re-verify after changes]
- [Existing tests that must still pass]

### Performance Considerations (Complex tier or when applicable)
- [Performance budgets, benchmarks to meet]

### Security Considerations (Complex tier or when applicable)
- [Input validation, auth checks, data exposure risks]

### Manual Verification
- [What to check manually]

## Traceability Matrix (Standard + Complex tiers)

| PRD Req | Plan Task(s) | Test(s) | Verification |
|---------|-------------|---------|--------------|
| REQ-1: [description] | Task 1.1, Task 1.2 | test_feature_x | [pending] |
| REQ-2: [description] | Task 2.1 | test_feature_y | [pending] |

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| [risk] | [H/M/L] | [H/M/L] | [strategy] |

### Dependency Risks (Standard + Complex tiers)
- [External API/service dependencies and their failure modes]
- [Library version constraints]
- [Cross-repo coordination risks]

### Rollback Strategy
- **Feature-level rollback:** [How to fully revert this feature if it fails post-merge]
- **Partial rollback:** [How to revert individual phases if mid-execution issues arise]
- **Data considerations:** [Any schema changes, migrations, or data that complicates rollback]

## Open Questions (if any)
- [Unresolved items that need clarification during execution]

## Version History
| Version | Date | Changes |
|---------|------|---------|
| v{X.Y} | [date] | [what changed from previous version] |

## Orchestrator Execution Config

- **Suggested Mode:** [New System / Feature Integration / Fast Track]
- **Suggested Governance:** [Full / Lightweight / Auto-approve]
- **Estimated Agents:** [N]
- **Critical Path:** [Task X → Task Y → Task Z]
- **Patterns to Apply:** [list with SharedKnowledge paths]
- **Standards to Enforce:** [list with SharedKnowledge paths]
- **Rollback Trigger:** [condition that means "stop and revert"]
- **Known Gotchas:** [things the orchestrator should watch for]

## Definition of Ready (DoR) for Orchestration

### Mandatory (all tiers)
- [ ] Every PRD requirement maps to at least one plan task
- [ ] Every task names specific files to modify/create
- [ ] Every task has acceptance criteria
- [ ] Scope boundaries are explicit (in/out)
- [ ] Architecture decisions are documented with rationale
- [ ] Dependencies between tasks are mapped
- [ ] At least one parallel execution group identified (or "none - serial")
- [ ] Plan reviewed and approved by user

### Standard + Complex tiers
- [ ] Testing strategy defined (unit + integration minimum)
- [ ] Risk register with mitigations
- [ ] Rollback strategy defined
- [ ] Traceability matrix complete
- [ ] Codebase exploration findings documented

### Complex tier only
- [ ] ADRs marked for SharedKnowledge promotion
- [ ] Cross-repo coordination plan (if multi-repo)
- [ ] Performance/security considerations documented
- [ ] Dependency risk analysis complete

### Approval Record
- Approved by: [user name / "user confirmed"]
- Approved at: [YYYY-MM-DD HH:MM]
- Method: [verbal / message / AskUserQuestion response]
- Complexity Tier confirmed: [Quick / Standard / Complex]
```

### Task Breakdown Rules

1. **File-Level Specificity** - Every task must name exact files to modify/create
2. **Testable Completion** - Every task must have acceptance criteria
3. **Right-Sized Tasks** - Each task should be 30min-2hr of work for one agent
4. **Dependency Clarity** - Each task explicitly states what it depends on
5. **Pattern Reference** - Each task notes which patterns/conventions to follow
6. **No Ambiguity** - A developer reading the task should know EXACTLY what to do

### Dependency Mapping

Create explicit dependency graph:

```markdown
Task 1.1 ──→ Task 2.1 ──→ Task 3.1
Task 1.2 ──→ Task 2.1
Task 1.3 ──────────────→ Task 3.1
                Task 2.2 ──→ Task 3.2
```

Identify:
- **Critical path** (longest dependency chain)
- **Parallel opportunities** (independent tasks)
- **Bottlenecks** (tasks with many dependents)

---

## Phase 4b: Plan Approval (Formal Gate)

**Purpose:** Capture explicit user approval before the plan is considered ready for orchestration. This is the formal handoff gate.

### Approval Process

1. **Present the DoR checklist** to the user (show which items are checked)
2. **Highlight the complexity tier** and what it means for execution
3. **Ask for explicit approval** using `AskUserQuestion`:

```markdown
"Plan v{X.Y} is complete. Here's the readiness summary:

Complexity Tier: [Quick / Standard / Complex]
Tasks: [N] across [M] phases
Parallel Groups: [N]
ADRs: [N] decisions documented
DoR: [X/Y] mandatory items checked

Options:
A) Approve - plan is ready for /my-orchestration-master
B) Needs changes - I'll iterate and create v{X.Y+1}
C) Needs peer review - share with team before approving
D) Downgrade/upgrade tier - change complexity tier"
```

4. **Record approval** in the DoR Approval Record section
5. **Write the plan** with approval recorded

**If user says "just approve it" or "looks good":**
- Record as approved with method "verbal"
- Fill in timestamp
- Proceed

**The DoR checklist + approval record IS the handoff contract.** The orchestrator verifies this in its Phase 0 before starting execution.

---

## Version Control

### File Naming Convention

```
20-00_PLANNING_v{major}.{minor}.md
```

**Examples:**
- `20-00_PLANNING_v1.0.md` - First plan
- `20-00_PLANNING_v1.1.md` - Refined first plan
- `20-00_PLANNING_v2.0.md` - Major scope change
- `20-00_PLANNING_v3.0.md` - Complete re-plan

### Location

```
<repo>/docs/master/<timestamp>_<feature>/20-00_PLANNING_v{X.Y}.md
```

**Example:**
```
/mnt/c/Projects/Sparkco/frontend/AAA/docs/master/20260205_0101_rtl-ltr-auto-detection/20-00_PLANNING_v1.0.md
```

### Re-Planning Workflow

When the planner runs again on an existing feature:

1. **Detect existing plans** - Glob for `20-00_PLANNING_v*.md` in the feature folder
2. **Identify latest version** - Sort by version number, find highest
3. **Read previous plan** - Understand what was planned before
4. **Understand what changed** - Compare with current PRD/research (may have been updated)
5. **Determine version increment** - Minor (refinement) or major (scope change)
6. **Confirm with user** - "Previous plan is v1.2. This looks like a [minor/major] change. Creating v1.3 or v2.0?"
7. **Create new version** - Previous version preserved (NOT overwritten)
8. **Mark previous version** - Update status to "Superseded by v{X.Y}"

### Version History in Document

Every plan includes a version history table at the bottom:

```markdown
## Version History
| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-02-05 | Initial plan - 8 tasks, 2 phases |
| v1.1 | 2026-02-06 | Added error handling tasks per user feedback |
| v2.0 | 2026-02-10 | Scope expanded to include multi-language support |
```

---

## SharedKnowledge Integration

### Before Planning (Phase 2) — via Sub-Agent

**All SK reads use the `sk-scout` agent definition** (see Phase 2 above). Dispatch via `Agent` tool with `subagent_type: "sk-scout"`. The agent is haiku, read-only, and returns a concise summary (max 30 lines) to the main planning context.

Check SharedKnowledge for relevant assets:

1. **Patterns** (`C:\Projects\SharedKnowledge\patterns\`)
   - Search for applicable patterns
   - If found: Reference in plan, note for orchestrator to apply
   - If not found: Flag for potential pattern creation post-execution

2. **Lessons** (`C:\Projects\SharedKnowledge\lessons\`)
   - Search INDEX.md for similar past tasks
   - If found: Apply constraints to avoid past mistakes
   - Surface relevant lessons to user during Q&A

3. **Decisions** (`C:\Projects\SharedKnowledge\decisions\`)
   - Search INDEX.md for prior ADRs in this domain
   - If found: Respect prior decisions, note constraints in plan
   - Surface ADR conflicts to user during Q&A

4. **Standards** (`C:\Projects\SharedKnowledge\standards\`)
   - Load CODING_PREFERENCES.md for code style constraints
   - Load UX_STYLE_PROFILE.md for UI tasks
   - Reference in plan for orchestrator compliance

5. **Preferences** (`C:\Projects\SharedKnowledge\preferences\`)
   - ALWAYS load `team/default.md` — contains locked tech stack versions (Vue 2, MongoDB 4.0, etc.)
   - Run `whoami`, load `personal/<username>.md` if exists — contains personal overrides (e.g. git policy)
   - Technology constraints MUST be reflected in plan — never plan upgrades to locked components

5. **Guides** (`C:\Projects\SharedKnowledge\guides\`)
   - Skim for reference guides relevant to the feature domain
   - If found: Reference in plan for team context
   - Useful for onboarding orchestrator agents to domain knowledge

6. **Runbooks** (`C:\Projects\SharedKnowledge\runbooks\`)
   - Skim for operational procedures that may constrain implementation
   - If found: Note constraints in plan (e.g., deployment procedures, rollback steps)
   - Reference in Orchestrator Execution Config

7. **Governance** (`C:\Projects\SharedKnowledge\governance\`)
   - Load relevant templates for scope alignment (Phase 1)
   - Reference in Orchestrator Execution Config for governance selection

### During Planning

- Reference patterns in task descriptions ("Apply dialog_pattern.md")
- Note lessons learned in risk register ("Past lesson: always validate file permissions")
- Respect prior ADRs in architecture decisions ("Constrained by ADR-003: use Redis for caching")
- Embed standards compliance in acceptance criteria
- Reference guides in task context where relevant
- Note runbook constraints in Orchestrator Execution Config

### After Planning (Write-Back)

**If the planning process produced reusable knowledge, write it back to SharedKnowledge.**

**Via sub-agent** (to protect main context):

1. **ADR Promotion** - If plan contains ADRs marked "Promote to SharedKnowledge: Yes":
   - Copy to `C:\Projects\SharedKnowledge\decisions\YYMMDD_ADR-NNN_title.md`
   - Update `decisions/INDEX.md`

2. **Planning Lessons** - If planning revealed insights about the planning process itself:
   - Create entry in `C:\Projects\SharedKnowledge\lessons\` (prefixed with "planning_")
   - Update `lessons/INDEX.md`
   - Examples: "Feature X required 3 Q&A rounds due to ambiguous requirements",
     "Multi-repo features need explicit cross-repo coordination in Phase 1"

**When NOT to write back:**
- Plan is straightforward with no novel insights
- All findings are project-specific

---

## Execution Tools

**For document reading:**
- `Read` for input documents (PRD, research, prior plans)
- `Glob` for finding documents in feature folders

**For codebase exploration:**
- `Task` tool with `Explore` agent for deep multi-file investigation
- `Grep` for finding patterns across repos
- `Read` for understanding specific implementations
- `Glob` for discovering file structure

**For user interaction:**
- `AskUserQuestion` for structured Q&A (2-4 questions per round)

**For research gaps:**
- `WebSearch` for missing technical information
- `WebFetch` for specific documentation
- `mcp__plugin_context7_context7__resolve-library-id` + `query-docs` for library docs

**For SharedKnowledge:**
- `Read` and `Glob` on `C:\Projects\SharedKnowledge\`

**For plan output:**
- `Write` to create the versioned planning document

**Never use (during planning):**
- `Edit` to modify code (that's the orchestrator's job)
- Implementation-focused tools
- Git operations (no commits during planning)

---

## Session Continuity (Progressive Save)

**Problem:** Planning sessions can be long (3-6 Q&A rounds, deep codebase exploration). If context exhausts mid-planning, all decisions, conflicts resolved, and scope alignment are lost.

**Solution:** Write the plan file progressively — after each phase, not just at Phase 4 synthesis.

### Progressive Save Protocol

| After Phase | What to Write to Disk | File |
|-------------|----------------------|------|
| Phase 0 (Ingestion) | Create plan file with metadata + gap analysis | `20-00_PLANNING_v{X.Y}.md` |
| Phase 1 (Scope) | Add scope alignment section | Update same file |
| Phase 2 (Codebase) | Add codebase analysis section | Update same file |
| Each Q&A round | Add decisions made, update open questions | Update same file |
| Phase 4 (Synthesis) | Complete with tasks, dependencies, DoR | Final version |

**The plan file doubles as the resume artifact.** No separate resume file needed.

### Planning Resume State Header

At the **top** of the plan file (updated after every phase), maintain a resume state block:

```markdown
<!-- PLANNING RESUME STATE
planning_skill_version: 1.3.0
current_phase: [Phase N: Name]
phases_completed: [0, 1, 2]
qa_rounds_completed: [N]
decisions_made: [N]
open_questions: [N]
last_updated: [YYYY-MM-DD HH:MM]
context_note: [brief state description for new session]
-->
```

This HTML comment is invisible in rendered markdown but machine-readable by a new session.

### Standalone Resume File: `20-99___RESUME_STATE.md`

In addition to the inline resume header in the plan file, **also maintain a standalone resume file** at:

```
<project_root>/docs/master/<timestamp>_<task>/20-99___RESUME_STATE.md
```

This file follows the `20-xx` prefix convention (planning artifacts = `20-*`). It contains:
- The resume state metadata (same as the HTML comment header)
- A human-readable summary of where planning stands
- Instructions for the new session (which skill to invoke, which phases to skip)

**Why both?** The inline header is for machine parsing. The standalone file is easy to find (`find docs/master/ -name "*RESUME*"`) and gives the user a single predictable file to look for — same pattern across all pipeline skills:

| Skill | Resume File |
|-------|------------|
| Research | `10-99___RESUME_STATE.md` |
| Planning | `20-99___RESUME_STATE.md` |
| Orchestration | `30-99___RESUME_PROMPT.md` |

### How It Works

1. **Phase 0 completes** → Create `20-00_PLANNING_v{X.Y}.md` with resume header + gap analysis. Create `20-99___RESUME_STATE.md`.
2. **Phase 1 completes** → Update plan file: add scope alignment. Update both resume locations.
3. **Phase 2 completes** → Update plan file: add codebase analysis. Update both resume locations.
4. **Each Q&A round** → Update plan file: add decisions under `## Decisions Log`. Update both resume locations.
5. **Phase 4** → Finalize: restructure into clean plan format, fill DoR, keep resume header. Update `20-99___RESUME_STATE.md` to mark planning as complete.

### Decisions Log (Progressive Section)

Between Phase 2 and Phase 4 synthesis, the plan file contains a growing decisions log:

```markdown
## Decisions Log (Progressive - will be restructured in final plan)

### Q&A Round 1 (Phase 3)
- **Scope:** Decided to include requirements 1-8, defer 9-12
- **Architecture:** Will use ReactiveStore pattern (matches codebase convention)
- **Open:** Testing strategy TBD

### Q&A Round 2 (Phase 3)
- **Testing:** Unit + integration, no E2E for v1
- **Risk:** Concurrent edit conflict handled with last-write-wins
- **Open:** None — ready for synthesis
```

### If Context Dies Mid-Planning

**What's on disk:**
- `20-99___RESUME_STATE.md` — standalone resume file (easy to find)
- `20-00_PLANNING_v{X.Y}.md` — partially-complete plan with inline resume header + all decisions so far

**What the user does:**
1. Exit dead session
2. Start new `claude` session
3. Say: **"Continue planning from `[path]/20-99___RESUME_STATE.md`"**
4. New session reads the resume file, then the plan, picks up at the right phase
5. New session invokes `/my-planning-master` and skips completed phases

**What the new session does:**
1. Read `20-99___RESUME_STATE.md` (quick overview of state)
2. Read `20-00_PLANNING_v{X.Y}.md` (full plan with decisions log)
3. Parse the `<!-- PLANNING RESUME STATE -->` header
4. Skip phases listed in `phases_completed`
5. Resume at `current_phase`
6. Continue Q&A from where we left off (decisions already recorded)

### Context Threshold Monitoring

| Context Level | Action |
|--------------|--------|
| ~70% | Ensure plan file + `20-99___RESUME_STATE.md` saved with latest state |
| ~85% | Finalize both files, **print alert message to user** (see below) |
| ~90% | Stop Q&A, save everything, **print emergency message then STOP** |

### User Alert Messages (MUST print to terminal)

**CRITICAL RULE: The alert MUST be the ABSOLUTE LAST output of the conversation.**
When you detect context is at ~85%+, save all files, then print the alert as your FINAL message.
Do NOT output anything after the alert — no "let me continue", no tool calls, no summaries.
The user will scroll up in the dead terminal and the copy-paste instructions must be right there.

**At ~85% — save files, then print this as your LAST message (fill in `<PATH>`):**

```
============================================================
  CONTEXT HIGH (~85%) — PLANNING SESSION CONTINUITY ACTIVATED
============================================================

Resume files saved to:
  <PATH>/20-99___RESUME_STATE.md
  <PATH>/20-00_PLANNING_v{X.Y}.md

When this session can no longer respond:

  1. Exit:  Ctrl+C or close terminal
  2. Start: claude
  3. Paste the following into the new session:

     Continue an in-progress planning session.
     Read: <PATH>/20-99___RESUME_STATE.md
     Read: <PATH>/20-00_PLANNING_v{X.Y}.md
     After reading, invoke /my-planning-master and skip completed phases.
     Resume Q&A from where it left off — don't re-ask decided questions.

Full guide: C:\Projects\SharedKnowledge\guides\session-continuity-guide.md
============================================================
```

**At ~90% — save files, then print this as your ABSOLUTE FINAL output, then STOP:**

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  CONTEXT CRITICAL (~90%) — STOPPING PLANNING SESSION
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

Resume files saved to:
  <PATH>/20-99___RESUME_STATE.md
  <PATH>/20-00_PLANNING_v{X.Y}.md

EXIT NOW and resume in a new session:

  1. Exit:  Ctrl+C
  2. Start: claude
  3. Paste:
     Continue planning from <PATH>/20-99___RESUME_STATE.md

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

**After printing either alert: OUTPUT NOTHING. The alert IS your final message.**

---

## Red Flags - STOP and Correct

These rationalizations mean you're violating planning principles:

- ❌ "Requirements are clear, skip Q&A" → ALWAYS ask at least one round of questions
- ❌ "I'll figure out the details during implementation" → Plans must be file-level specific
- ❌ "The research covers everything" → Research is input, not the plan. Synthesize.
- ❌ "User is busy, I'll decide for them" → Surface decisions, don't make them
- ❌ "This is obvious, no need to explore the codebase" → Explore ALWAYS. Reality surprises.
- ❌ "Previous plan is fine, just add a task" → Version properly, document what changed
- ❌ "Scope alignment is bureaucracy" → It prevents wasted planning effort
- ❌ "I'll start coding a prototype to inform the plan" → NO CODE during planning
- ❌ "User said 'just plan it', skip questions" → Ask at least scope alignment questions
- ❌ "Conflicts will resolve themselves during implementation" → Resolve NOW or flag explicitly
- ❌ "I'll write the plan file at the end" → Save progressively after each phase (Iron Law #11)

**All of these mean: Stop. Follow the planning workflow correctly.**

---

## Planning Checklist

### Phase 0: Document Ingestion
- [ ] All input documents read completely
- [ ] Gap analysis performed (requirement, research, conflict)
- [ ] Hidden complexity identified
- [ ] Feature folder path confirmed

### Phase 1: Scope Alignment
- [ ] Planning scope agreed with user
- [ ] In/out of scope documented
- [ ] Constraints identified
- [ ] Planning depth agreed

### Phase 2: Codebase Exploration
- [ ] Architecture understood
- [ ] Relevant patterns identified
- [ ] Integration points mapped
- [ ] Files to modify listed
- [ ] SharedKnowledge checked via SK Scout sub-agent (patterns, lessons, decisions, standards, guides, runbooks, governance)

### Phase 3: Iterative Q&A
- [ ] At least 1 round of questions asked
- [ ] All requirement gaps filled (or flagged as OPEN)
- [ ] All conflicts resolved (or flagged as OPEN)
- [ ] Technical approach decisions made
- [ ] Architecture decisions made
- [ ] Testing strategy aligned
- [ ] User approved moving to synthesis

### Phase 4: Plan Synthesis
- [ ] Version number determined (and confirmed with user if re-planning)
- [ ] Complexity tier set (Quick / Standard / Complex)
- [ ] All tasks have file-level specificity
- [ ] All tasks have acceptance criteria
- [ ] All tasks have verification method
- [ ] Dependencies mapped
- [ ] Parallel groups identified
- [ ] Architecture decisions in ADR format (Standard + Complex)
- [ ] Traceability matrix complete (Standard + Complex)
- [ ] Risk register complete with rollback strategy (Standard + Complex)
- [ ] Orchestrator Execution Config filled (replaces freeform handoff notes)
- [ ] Version history updated
- [ ] Plan written to `20-00_PLANNING_v{X.Y}.md`

### Phase 4b: Plan Approval
- [ ] DoR checklist filled for appropriate tier
- [ ] DoR presented to user
- [ ] User explicitly approved the plan
- [ ] Approval record filled (who, when, method, tier)

### Session Continuity (every phase)
- [ ] Plan file written/updated to disk after each phase completion
- [ ] Resume state header updated with current phase and decisions count
- [ ] `20-99___RESUME_STATE.md` created/updated alongside plan file
- [ ] Decisions log section kept current with Q&A round outcomes
- [ ] Open questions section reflects remaining items

### Post-Planning
- [ ] Previous plan marked as "Superseded" (if re-planning)
- [ ] ADRs marked "promote" copied to SharedKnowledge/decisions/ (if any)
- [ ] Planning lessons written to SharedKnowledge/lessons/ (if novel insights)
- [ ] User informed of next steps (/my-orchestration-master)

---

## After Planning is Complete

**Tell the user:**

```
Planning complete. Implementation plan created at:
<path-to-planning-file>

This plan covers:
- Complexity Tier: [Quick / Standard / Complex]
- [X] tasks across [Y] phases
- [Z] parallel execution groups identified
- [N] architecture decisions (ADRs) documented
- DoR: [X/Y] checklist items verified

Version: v{X.Y}
Estimated Effort: [T-shirt size] ([N] hours)

Definition of Ready: [Complete / Partial - N items pending]

Next steps:
1. Review the plan and DoR checklist
2. If changes needed: Re-run /my-planning-master (will create v{X.Y+1})
3. If approved: Execute with /my-orchestration-master
   (Orchestrator will verify the DoR before starting)
```

**Don't automatically start execution** - let user decide when to proceed.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02 | Initial planning master skill - extracted and enhanced from orchestration-master v2.0 Phase 0/1 |
| 1.1.0 | 2026-02 | Added: Complexity tiers (Quick/Standard/Complex), ADR-lite format for architecture decisions, traceability matrix, rollback strategy, dependency risks, verification methods per task, Definition of Ready (DoR) handoff gate, structured Orchestrator Execution Config, enhanced testing strategy, Phase 4b plan approval, SharedKnowledge/decisions/ integration |
| 1.2.0 | 2026-02 | Added: Full SharedKnowledge integration via SK Scout sub-agent (guides/, runbooks/, governance/ reads), post-planning write-back (ADR promotion, planning lessons), sub-agent pattern to protect main context from SK content bloat |
| 1.3.0 | 2026-02 | Added: Session Continuity Protocol (Iron Law #11) — progressive save after each phase, resume state header in plan file, decisions log for mid-session recovery, context threshold monitoring. Plan file doubles as resume artifact |

---

## The Bottom Line

**Planning Master v1.3 = Collaborative, iterative, codebase-aware implementation planning with formal handoff contracts, full SharedKnowledge integration, and session continuity.**

Not just "read docs and generate tasks" - this is:
- Deep document ingestion (understand ALL inputs)
- Scope alignment (agree on boundaries first)
- Codebase exploration (ground plans in reality)
- Iterative Q&A (collaborate, don't dictate)
- Conflict resolution (surface and resolve, don't hide)
- File-level specificity (concrete, not vague)
- Architecture decisions as ADRs (numbered, traceable, promotable)
- Traceability (PRD → tasks → tests → verification)
- Complexity-tiered depth (Quick/Standard/Complex - not over-kill for small features)
- DoR handoff gate (formal contract between planner and orchestrator)
- Version control (plans evolve, history preserved)
- Orchestrator-ready output (directly executable by /my-orchestration-master)
- Session continuity (progressive saves mean context death never loses planning decisions)

**Ask questions. Explore code. Resolve conflicts. Write concrete plans. Version everything. Save progressively. Gate the handoff.**

If you skip steps or generate vague plans, the orchestrator will fail, implementation will diverge, and time will be wasted.

**The Iron Laws exist because bad plans create bad code. Plan well.**
