---
name: dev-knowledge
description: Use when working on xpander.ai tasks. Shared engineering playbook — onboarding, PR workflow, security, frontend dev, design system, code conventions, repo map. Read MUST_READ.md first.
---

# dev-knowledge

Synced from `xpander-ai/dev-knowledge` @ `e6bd0a1`. Read the relevant file below before related work.

## Files

- **[agent_export.md](agent_export.md)** — 📦 Agent Export — Replicate This Agent to Another Instance
  - This skill packages everything required to clone the current agent's persistent brain (skills, memory, context, plans) **plus the GitHub + git identity** into a portable zip bundle that can be importe
- **[agent_import.md](agent_import.md)** — 📥 Agent Import — Replicate Another Agent's Brain Into This Workspace
  - Mirror image of `agent_export.md`. Given a single URL pointing to a bundle
- **[agent_onboarding.md](agent_onboarding.md)** — Skill: agent_onboarding
  - Post-import bootstrap. After `agent_import.sh --mode=<merge|...>` finishes
- **[aha_moments.md](aha_moments.md)** — 💡 AHA Moments — Append-Only Capture Protocol
  - This skill defines how every contributor (agent or human) captures point-in-time insights so the rest of the fleet benefits from them. The protocol is **append-only**: each AHA is its own immutable fi
- **[architecture_drawing.md](architecture_drawing.md)** — 🏛️ Architecture Drawing — Mermaid Diagrams to Image
  - Render architecture / flow / sequence / ER / C4 diagrams from **Mermaid** source
- **[browser_use.md](browser_use.md)** — Skill: Browser Use — Headless Browser as a Subprocess
  - Drive a real, JavaScript-capable browser from any xpander.ai agent **without blocking the main agent loop**. The browser runs as an isolated subprocess; the agent talks to it over the **Chrome DevTool
- **[bump_last_updated.md](bump_last_updated.md)** — Skill: Bump Last Updated Timestamps
  - User says: "bump the target in mono" where target is one of:
- **[code_comment_style.md](code_comment_style.md)** — Code comment style
  - **Rule (from user, 2026-04-28):** Comments in code must be **short, precise, and
- **[codex_runner.md](codex_runner.md)** — 🤖 codex_runner — Delegate Code Tasks to OpenAI Codex CLI as a Sandboxed Sub-Agent
  - This skill lets me (Gilfoyle) hand a self-contained coding subtask to **OpenAI
- **[dependabot_pr_auto_merge.md](dependabot_pr_auto_merge.md)** — Skill: Dependabot PR — Quick Review, Approve & Merge
  - When the user asks to handle Dependabot PRs on one or more xpander.ai repos, this skill:
- **[frontend_env_sync.md](frontend_env_sync.md)** — Skill — Sync Repo `.env` Files on User Request
  - **Trigger phrases** (case-insensitive, any of these or close variants):
- **[frontend_local_dev.md](frontend_local_dev.md)** — Skill — Frontend Local Dev + Browser Use + OTP + Screenshots
  - **Trigger phrases** (case-insensitive):
- **[known_repos.md](known_repos.md)** — Known Repositories — `/agent/data/dev`
  - This skill documents all repositories cloned in the local dev directory (`/agent/data/dev`).
- **[llm_providers.md](llm_providers.md)** — Skill: Managing LLM Providers in the Frontend
  - This skill covers everything needed to add, update, or remove LLM models in the xpander.ai frontend via Supabase migrations.
- **[MUST_READ.md](MUST_READ.md)** — MUST_READ — The Dev Knowledge Playbook
  - This repo (`xpander-ai/dev-knowledge`) is the **shared brain** for every xpander.ai engineering contributor — AI coding agents and human developers alike. If you are about to work on an xpander.ai tas
- **[notion_ticket_creation.md](notion_ticket_creation.md)** — 📝 Notion Ticket Creation — Product & Engineering Board
  - This skill defines how to create tickets (tasks, features, bugs, improvements) on the **🏗️ Product and Engineering** board in Notion when the user asks to "create a ticket / task / bug / feature" with
- **[planning_workflow.md](planning_workflow.md)** — Skill: Planning Workflow — Per-Ticket Plan Files
  - Whenever planning a non-trivial change (research, refactor, feature, fix), persist the plan as a **markdown file in the workspace** so it survives session compaction, can be shared with the user, and 
- **[pr_code_review_fix.md](pr_code_review_fix.md)** — AI Agent Skill: PR Code Review — Fix & Resolve Comments
  - When a PR has been reviewed and the user asks to **"fix code review comments"** / **"address review feedback"** / **"resolve review threads"**, systematically:
- **[pr_code_review.md](pr_code_review.md)** — AI Agent Skill: PR Code Review — Perform a Review
  - When the user asks to **"review this PR"** / **"do a code review"** / **"check PR #N"**, perform a thorough, professional code review and post the results back to the PR as inline comments + a single 
- **[pr_title_description.md](pr_title_description.md)** — AI Agent Skill: PR Title & Description Generator
  - Generate a **developer-readable PR title and description** from the diff and commit messages, optimized for code review clarity.
- **[refero_design_styles.md](refero_design_styles.md)** — Skill — Refero Styles: Drop-in DESIGN.md for Any UI Task
  - ---
- **[security_gh_issue_workflow.md](security_gh_issue_workflow.md)** — AI Agent Skill: Security GitHub Issue Workflow
  - When a security CVE / Trivy / IQ Server / Dependabot finding is tracked as a **GitHub issue** (and usually mirrored to a Notion ticket), drive it cleanly from triage through fix → PR → close → board u
- **[security_github_issue_lifecycle.md](security_github_issue_lifecycle.md)** — AI Agent Skill: Security GitHub Issue Lifecycle
  - Keep upstream GitHub security issues (Trivy / Dependabot / Snyk / GHSA / IQ Server tickets that live as `xpander-ai/<repo>` GitHub issues) in sync with the actual fix work — from PR open to verified-a
- **[security_vulnerability_fix.md](security_vulnerability_fix.md)** — AI Agent Skill: Security Vulnerability Fix
  - Resolve dependency security vulnerabilities (CVEs) flagged by IQ Server, Dependabot, Snyk, GitHub Security Advisories, or any other scanner — across **any language, package manager, or service** in an
- **[task_queue.md](task_queue.md)** — Task Queue — Single-Task Execution Discipline
  - **Why this exists:** there is one developer (me) and one shared dev folder where repos are cloned. Switching repos/branches mid-task corrupts working state. This skill enforces **one in-progress task 
- **[xpander_design_system.md](xpander_design_system.md)** — Skill — xpander.ai Design System: Tokens, Primitives, Approval Gates
  - ---
- **[xpander_mono_venv.md](xpander_mono_venv.md)** — xpander-mono — Single Root Virtualenv
  - **Scope**: Any Python work in `/agent/data/dev/xpander-mono` (running services, installing deps, running tests, lint, pre-commit, scripts).
