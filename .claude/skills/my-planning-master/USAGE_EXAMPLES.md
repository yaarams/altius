# Planning Master v1.0 - Usage Examples

## Overview

This file shows **exactly** how to invoke the `my-planning-master` skill for different scenarios, including iterative Q&A, re-planning with version control, and multi-repo planning.

---

## Basic Invocation Pattern

```markdown
# User provides:
1. PRD file path (00-00_PRD*.md)
2. Research file path (10-00_RESEARCH*.md)
3. Optional: Previous plan, additional docs
4. Trigger: "plan this", "create a plan", "plan the approach"

# Claude invokes skill:
/skill my-planning-master

# Claude follows phases:
Phase 0: Ingest all documents, gap analysis
Phase 1: Scope alignment with user
Phase 2: Deep codebase exploration
Phase 3: Iterative Q&A (multiple rounds)
Phase 4: Plan synthesis → 20-00_PLANNING_v{X.Y}.md
→ User reviews, approves, then executes with /my-orchestration-master
```

---

## Example 1: First Plan for a New Feature

### User Prompt:

```
I have a PRD and research for adding collaborative cursors to Sparkco.

PRD: /mnt/c/Projects/Sparkco/frontend/AAA/docs/master/20260210_0800_collaborative-cursors/00-00_PRD_collaborative-cursors.md
Research: /mnt/c/Projects/Sparkco/frontend/AAA/docs/master/20260210_0800_collaborative-cursors/10-00_RESEARCH.md

Plan the implementation approach. I want to discuss the technical decisions before we execute.
```

### What Happens:

```markdown
# Phase 0: Document Ingestion & Gap Analysis
→ Reads PRD: 14 functional requirements, 5 non-functional
→ Reads Research: WebSocket patterns, CRDT vs OT analysis, codebase patterns
→ Gap Analysis:
  - Requirement gap: Cursor color assignment not specified
  - Research gap: No performance benchmarks for 50+ concurrent cursors
  - Conflict: PRD says "instant updates", research says "throttle at 33ms"
→ Complexity alerts:
  - "Real-time cursor sync" involves: position encoding, viewport mapping, z-index layering
  - "User presence" involves: join/leave events, timeout detection, reconnection

# Phase 1: Scope Alignment
→ AskUserQuestion:
  Q1: "The PRD lists 14 requirements. Should we plan all 14 for v1, or prioritize?"
  → User: "Plan requirements 1-10 now, defer 11-14 (cursor trails, replay)"

  Q2: "How many repos are involved?"
  → User: "Just the AAA frontend repo"

  Q3: "Planning depth - file-level tasks or high-level phases?"
  → User: "File-level, I want to hand this directly to the orchestrator"

# Phase 2: Codebase Exploration
→ Spawns Explore agent: "Investigate cursor/presence patterns in Sparkco AAA"
  - Found: RemoteMemberCursor.vue in collaboration room
  - Found: CollaborationRoomStore with cursor position tracking
  - Found: SpatialWebsocketV2 handles real-time events at 33ms
  - Found: ReactiveStore pattern for feature stores
→ Spawns Explore agent: "Check SharedKnowledge for relevant patterns"
  - Found: cursor_rendering_pattern.md (partial match)
  - Lesson: 260205_RTL_lessons.md (throttling insights applicable)

# Phase 3: Iterative Q&A (Round 1)
→ AskUserQuestion:
  Q1: "Conflict: PRD says 'instant' cursor updates, but your WebSocket
       throttles at 33ms (~30fps). Options:
       A) Keep 33ms (matches existing pattern, proven stable)
       B) Reduce to 16ms (~60fps, smoother but 2x bandwidth)
       C) Adaptive (33ms default, 16ms for active editor)"
  → User: "Option A, 33ms is fine for cursors"

  Q2: "Cursor rendering approach:
       A) Extend existing RemoteMemberCursor.vue (reuse pattern)
       B) New component CursorOverlay.vue with canvas rendering (better for 50+)
       C) CSS-only approach with absolute positioning (simplest)"
  → User: "Option A, extend existing component for consistency"

  Q3: "State management:
       A) Extend CollaborationRoomStore (similar to existing cursor tracking)
       B) New CursorPresenceStore (clean separation)
       C) Vuex module (legacy pattern)"
  → User: "Option B, new ReactiveStore - matches newer patterns"

# Phase 3: Iterative Q&A (Round 2)
→ AskUserQuestion:
  Q1: "Color assignment for cursors: PRD doesn't specify.
       A) Random from palette (simple, possible collisions)
       B) Deterministic from user ID hash (consistent across sessions)
       C) Server-assigned (guaranteed unique, requires backend change)"
  → User: "Option B, deterministic from user ID"

  Q2: "Error handling for cursor sync:
       A) Silent drop (cursor disappears, reappears on reconnect)
       B) Frozen cursor with 'reconnecting' indicator
       C) Optimistic local + server reconciliation"
  → User: "Option B, frozen with indicator"

# Phase 3: Iterative Q&A (Round 3 - Final)
→ AskUserQuestion:
  Q1: "Testing strategy for real-time cursors:
       A) Unit tests only (cursor rendering, store logic)
       B) Unit + integration (WebSocket mock tests)
       C) Unit + integration + visual regression"
  → User: "Option B, unit + integration"

  Q2: "Ready to synthesize the plan. All decisions made.
       Should I create v1.0?"
  → User: "Yes, write the plan"

# Phase 4: Plan Synthesis
→ Determines version: v1.0 (no previous plan)
→ Creates 20-00_PLANNING_v1.0.md:
  - 12 tasks across 3 phases
  - 3 parallel execution groups
  - 5 architecture decisions documented
  - Risk register with 4 risks
  - Handoff notes for orchestrator
→ Writes to: docs/master/20260210_0800_collaborative-cursors/20-00_PLANNING_v1.0.md

# Final Message:
"Planning complete. Implementation plan created at:
docs/master/20260210_0800_collaborative-cursors/20-00_PLANNING_v1.0.md

This plan covers:
- 12 tasks across 3 phases
- 3 parallel execution groups identified
- 5 architecture decisions documented
- File-level specificity for all tasks

Version: v1.0

Next steps:
1. Review the plan document
2. If changes needed: Re-run /my-planning-master (will create v1.1)
3. If approved: Execute with /my-orchestration-master"
```

**Q&A Rounds:** 3
**Decisions Made:** 8
**Time:** ~30-45 minutes (mostly waiting for user responses)

---

## Example 2: Re-Planning (Version Increment)

### User Prompt:

```
We need to update the collaborative cursors plan. The team decided to add
cursor labels (showing user names). Also, requirement 11 (cursor trails)
is now in scope for v1.

Update the existing plan.

Existing plan: docs/master/20260210_0800_collaborative-cursors/20-00_PLANNING_v1.0.md
```

### What Happens:

```markdown
# Phase 0: Document Ingestion
→ Reads existing plan: 20-00_PLANNING_v1.0.md (12 tasks, 3 phases)
→ Re-reads PRD: Requirement 11 (cursor trails) now in scope
→ Re-reads Research: Trail rendering patterns available

→ Change Analysis:
  - Added: Cursor labels (new requirement, not in PRD)
  - Added: Requirement 11 (cursor trails) moved from out-of-scope
  - Unchanged: Requirements 1-10 approach

→ Version Assessment: Scope expanded (new requirements added)
  → Suggests major increment: v1.0 → v2.0

# Phase 1: Scope Alignment (Quick)
→ AskUserQuestion:
  Q1: "Scope expanded: cursor labels (new) + cursor trails (req 11).
       This looks like a significant scope change.
       Create v2.0 (major) or v1.1 (minor)?"
  → User: "v2.0 - it's a meaningful expansion"

# Phase 2: Codebase Exploration (Targeted)
→ Quick check for cursor label patterns in codebase
  - Found: Tooltip component could be adapted for labels
  - Found: Canvas-based trail rendering not in codebase (new pattern needed)

# Phase 3: Iterative Q&A (1 round - scope is mostly clear)
→ AskUserQuestion:
  Q1: "Cursor labels: always visible or hover-only?
       A) Always visible (like Figma)
       B) Hover to show (less visual clutter)
       C) Configurable per user preference"
  → User: "Option A, always visible"

  Q2: "Cursor trails: rendering approach?
       A) CSS animation (simple, limited shapes)
       B) Canvas overlay (performant, complex)
       C) SVG path (vector, moderate complexity)"
  → User: "Option A, CSS animation - keep it simple for v1"

# Phase 4: Plan Synthesis
→ Version: v2.0 (confirmed with user)
→ Creates 20-00_PLANNING_v2.0.md:
  - 15 tasks across 4 phases (3 new tasks added)
  - 4 parallel execution groups
  - Previous v1.0 decisions preserved
  - New decisions documented
  - Version history updated
→ Updates v1.0 status header to "Superseded by v2.0"

# Final Message:
"Re-planning complete. Updated plan created at:
docs/master/20260210_0800_collaborative-cursors/20-00_PLANNING_v2.0.md

Changes from v1.0:
- Added: 3 new tasks for cursor labels and trails
- Scope expanded from 10 to 12 requirements
- New phase 4 added for trail rendering

Version: v2.0 (v1.0 marked as superseded)

Next steps:
1. Review the updated plan
2. If more changes: Re-run (will create v2.1)
3. If approved: Execute with /my-orchestration-master"
```

**Q&A Rounds:** 1 (most decisions were already made in v1.0)
**New Decisions:** 2
**Time:** ~15-20 minutes

---

## Example 3: Multi-Repo Planning

### User Prompt:

```
Plan the STT transcript feature. It spans two repos.

PRD: /mnt/c/Projects/Sparkco/frontend/AAA/docs/master/20260208_1200_stt-transcripts/00-00_PRD_stt-transcripts.md
Research: /mnt/c/Projects/Sparkco/frontend/AAA/docs/master/20260208_1200_stt-transcripts/10-00_RESEARCH.md

Repos:
- Primary: /mnt/c/Projects/Sparkco/frontend/AAA (main UI)
- Secondary: /mnt/c/Projects/_Sparki/frontend (shared components)

Create the plan.
```

### What Happens:

```markdown
# Phase 0: Document Ingestion
→ Reads PRD: Transcript display, speaker identification, search
→ Reads Research: WebSpeech API, STT providers, existing transcript patterns
→ Gap Analysis:
  - Where does transcript logic live? (primary vs secondary repo)
  - How do repos share components?
  - Cross-repo build/deploy dependencies?

# Phase 1: Scope Alignment
→ AskUserQuestion:
  Q1: "Two repos involved. Which repo owns what?
       A) Primary (AAA): UI components, Secondary (Sparki): STT engine
       B) Primary (AAA): Everything, Secondary (Sparki): Reference only
       C) Primary (AAA): Feature logic, Secondary (Sparki): Shared components"
  → User: "Option C - shared components in Sparki"

  Q2: "Should the plan cover both repos or just primary?"
  → User: "Both - I want coordinated tasks"

# Phase 2: Codebase Exploration (Both Repos)
→ Spawns Explore agent #1: "Investigate STT patterns in AAA"
→ Spawns Explore agent #2: "Investigate shared components in Sparki"
  - AAA: Found existing audio handling in LiveKit utils
  - Sparki: Found shared component library pattern with npm linking
  - Cross-repo: Sparki components imported via @sparki/components

# Phase 3: Iterative Q&A (2 rounds)
→ Round 1: Architecture decisions for cross-repo features
→ Round 2: Testing strategy for multi-repo coordination

# Phase 4: Plan Synthesis
→ Creates 20-00_PLANNING_v1.0.md with sections for BOTH repos:
  - Phase 1: Shared components (Sparki repo) - 4 tasks
  - Phase 2: Feature integration (AAA repo) - 6 tasks
  - Phase 3: Cross-repo testing - 3 tasks
  - Dependency: Phase 2 depends on Phase 1

# Plan includes cross-repo coordination notes:
"## Multi-Repo Coordination
- Sparki changes must be committed and linked BEFORE AAA integration
- Orchestrator should process Sparki tasks first (Phase 1)
- AAA tasks reference Sparki components via @sparki/components"
```

---

## Example 4: Planning with Minimal Input (Gap Filling)

### User Prompt:

```
Plan adding dark mode to the app.

PRD: docs/master/20260211_0900_dark-mode/00-00_PRD_dark-mode.md

No research doc yet - we're skipping research for this one.
Just use your knowledge and the codebase.
```

### What Happens:

```markdown
# Phase 0: Document Ingestion
→ Reads PRD
→ No research document available
→ Gap Analysis:
  - MAJOR GAP: No research on industry patterns for dark mode
  - Note: Will compensate with deeper codebase exploration + built-in knowledge

# Phase 1: Scope Alignment
→ AskUserQuestion:
  Q1: "No research document provided. I can compensate with:
       A) Deep codebase exploration + my knowledge of dark mode patterns
       B) Quick web research + codebase exploration (10 min)
       C) Full research first using /my-research-master (recommended for best results)"
  → User: "Option A, skip research - I know what I want"

# Phase 2: Codebase Exploration (DEEPER than usual to compensate)
→ Explores CSS/theme infrastructure extensively
→ Discovers existing theme variables, color palette, style patterns
→ Maps all color references across components
→ Identifies theme switching infrastructure (or lack thereof)

# Phase 3: Iterative Q&A (More rounds to compensate for missing research)
→ Round 1: Theme approach (CSS variables vs class-based vs media query)
→ Round 2: Component-by-component scope (which components first?)
→ Round 3: Edge cases (images, third-party components, user preference storage)
→ Round 4: Testing approach for visual changes

# Phase 4: Plan Synthesis
→ Creates 20-00_PLANNING_v1.0.md with research gap noted:
  "Note: This plan was created without a formal 10-00_RESEARCH.md document.
   Codebase exploration and built-in knowledge were used to inform decisions.
   Consider running /my-research-master if approach needs validation."
```

---

## Example 5: When Plan is Unclear - Asking Hard Questions

### User Prompt:

```
Plan this: docs/master/20260211_1400_feature-x/00-00_PRD_feature-x.md

The PRD is pretty rough but let's work with it.
```

### What Happens:

```markdown
# Phase 0: Document Ingestion
→ Reads PRD: Vague requirements, inconsistent language
→ Gap Analysis: SIGNIFICANT GAPS
  - 6 out of 10 requirements are ambiguous
  - No acceptance criteria
  - Conflicting statements in sections 3 and 7
  - No technical constraints specified

# Phase 1: Scope Alignment
→ AskUserQuestion:
  Q1: "The PRD has significant gaps. I found:
       - 6 ambiguous requirements
       - No acceptance criteria
       - 2 conflicting statements

       Should I:
       A) Work through each gap with you now (thorough, ~20 min)
       B) Make reasonable assumptions and flag them (faster, may need re-planning)
       C) Go back to PRD refinement first (recommended if PRD needs major work)"
  → User: "Option A, let's work through them"

# Phase 3: Extended Iterative Q&A (6 rounds)
→ Round 1: "Requirement 3 says 'support multiple formats'. Which formats exactly?"
→ Round 2: "Section 3 says 'real-time' but section 7 says 'batch processing'. Which is it?"
→ Round 3: "No error handling specified. How should failures be handled?"
→ Round 4: "Who is the target user? PRD mentions both 'admin' and 'end user' without distinction."
→ Round 5: "What 'done' looks like? I need acceptance criteria for each requirement."
→ Round 6: "Testing expectations? The PRD is silent on quality requirements."

# After 6 rounds, all gaps filled.

# Phase 4: Plan Synthesis
→ Plan includes enhanced PRD summary:
  "## PRD Clarifications (from Planning Session)
  The following clarifications were made during planning:
  - Requirement 3: Supports JSON, CSV, Markdown (user clarified)
  - Conflict resolution: Real-time for UI, batch for exports (user decided)
  - Error handling: Show toast notification, log to console (user specified)
  ..."
```

---

## Directory Structure After Planning

```
<repo>/
└── docs/
    └── master/
        └── 20260210_0800_collaborative-cursors/
            ├── 00-00_PRD_collaborative-cursors.md      # Input (from research or user)
            ├── 10-00_RESEARCH.md                        # Input (from /my-research-master)
            ├── 20-00_PLANNING_v1.0.md                   # First plan (now superseded)
            ├── 20-00_PLANNING_v2.0.md                   # Updated plan (current)
            └── ... (orchestrator creates more files during execution)
```

After orchestration executes:
```
            ├── 30-00_IMPLEMENTATION-SUMMARY_v1.0.md     # Orchestrator output
            ├── GOVERNANCE.md                          # Orchestrator Phase -1
            ├── JOURNAL_*.md                           # Orchestrator journal
            ├── CHECKPOINT_BARRIER_*.json              # Orchestrator checkpoints
            ├── SUMMARY_*.md                           # Orchestrator final summary
            ├── TECH_DEBT_*.md                         # Orchestrator tech debt
            └── LESSONS_LEARNED_*.md                   # Orchestrator post-mortem
```

---

## When NOT to Use Planning Master

**Don't use for:**
- Trivial changes (< 30 min, obvious approach)
- Already detailed plans from another source
- Research tasks → use `/my-research-master`
- Brainstorming ideas → use `/brainstorming`
- Code review → use `/code-review`
- Debugging → use `/systematic-debugging`

**The planning master is for turning requirements + research INTO detailed plans.**

If you already HAVE a detailed plan → go directly to `/my-orchestration-master`.

---

## Bottom Line

**Planning Master v1.0 = Collaborative, iterative planning that produces orchestrator-ready implementation plans.**

- Read all inputs deeply
- Explore the codebase for reality
- Ask questions iteratively (don't guess)
- Resolve conflicts explicitly
- Write file-level specific plans
- Version control everything
- Hand off to orchestrator when approved

**Good plans prevent bad implementations. Plan well.**
