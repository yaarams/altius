# Skill — Refero Styles: Drop-in DESIGN.md for Any UI Task

> **Source:** [styles.refero.design](https://styles.refero.design) — a curated library of design systems
> serialized as `DESIGN.md` files (colors, typography, spacing, surfaces, components, do/don'ts,
> imagery, motion). Built specifically as **drop-in context for AI coding agents**.
>
> **Why this skill exists:** Without an explicit design source, generated UIs drift to generic
> Tailwind defaults — gray cards, default Inter, indigo-500 buttons. With a Refero `DESIGN.md`
> in context, the agent emits brand-grade output (Stripe-violet, Linear-midnight, Vercel-mono,
> etc.) on the first pass instead of after three rounds of "make it look more like X".

---

## Trigger phrases (case-insensitive)

Use this skill the moment any of the following show up:

- "design a … like **{brand}**" / "in the style of **{brand}**" / "feel like **{brand}**"
- "build a landing page / hero / pricing / dashboard / marketing site"
- "style this component" / "make this look polished / branded / production-ready"
- "pick a design system" / "give it a vibe" / "theme this"
- "clone the look of …" / "match {company}'s aesthetic"
- The user pastes a `styles.refero.design/style/<uuid>` URL
- The user mentions DESIGN.md, design tokens, or a Refero link

If the user only asks for *functionality* ("add an endpoint", "fix this bug") **don't trigger**.
This skill is for *visual / UI* asks.

> ⚠️ **Do NOT use this skill on `frontend` or `xpander-mono`.** Those repos already have a
> mature design system — follow `workspace/dev-knowledge/skills/xpander_design_system.md` instead.
> Refero is for greenfield projects with no existing tokens. Mixing them produces drift
> and rejected reviews.

---

## What Refero gives you

For every catalogued site, three layers:

1. **`designSystem` JSON** — structured tokens: `colors`, `typography`, `typeScale`, `spacing`,
   `surfaces`, `elevation`, `components`, `layout`, `imagery`, `dos`, `donts`, `northStar`,
   `description`, plus 20 `similar` brands. This is the source of truth.
2. **Rendered DESIGN.md** — the same JSON formatted as a single Markdown brief, ready to paste
   into any AI coding tool's context window.
3. **Preview assets** — screenshot, thumbnail, short looping MP4, favicon. Useful evidence
   in PRs.

---

## API endpoints (verified 2026-05)

All JSON, no auth, no rate-limit headers observed. **Always prefer the API over scraping HTML —
the site is a Next.js SPA, `curl <page>` returns app shell only.**

| Purpose | Endpoint | Notes |
|---|---|---|
| List catalog | `GET https://styles.refero.design/api/styles` | Paginated list; ~30 KB per page |
| **Search by brand name** | `GET https://styles.refero.design/api/styles/search?q={name}` | Case-insensitive; returns `{styles:[{id,siteName,url,...}]}` |
| **Brand detail** | `GET https://styles.refero.design/api/styles/{uuid}` | Returns `{style:{fullResult:{designSystem,raw,meta,screenshot}}, similar:[20 brands]}` |
| Page (humans) | `https://styles.refero.design/style/{uuid}` | SPA — don't scrape, use API |

> ⚠️ Endpoints to **avoid**: `/api/search` (404), `/style/<id>.md` (returns SPA HTML, not Markdown),
> `/style/<id>/raw` (404). The `.md` suffix looks tempting; it isn't real.

---

## Workflow — Standard UI Task

### 1. Identify the reference brand

- **User named one** ("like Stripe") → go to step 2.
- **User pasted a Refero URL** → extract `<uuid>` from `/style/<uuid>` → step 3.
- **No reference given** → ask via `xpask_for_information` (after `xpstart_execution_plan`)
  or directly (before plan starts):
  > "Got it. Want me to base the look on a specific brand from
  > [styles.refero.design](https://styles.refero.design) — e.g. Stripe, Linear, Vercel,
  > Cursor, ElevenLabs, Notion, Mercury? Or paste a Refero URL."

### 2. Resolve brand → UUID

```bash
BRAND="stripe"
curl -sL "https://styles.refero.design/api/styles/search?q=${BRAND}" \
  | jq -r '.styles[0] | "\(.id)\t\(.siteName)\t\(.url)"'
# 48e5de76-05d5-4c4e-a269-c7c245b291ec  Stripe  https://stripe.com
```

If >1 plausible match, show the top 3 `siteName + url` to the user and let them pick.
**Do not silently pick #1 when the match is ambiguous.**

### 3. Fetch the design system

```bash
UUID="48e5de76-05d5-4c4e-a269-c7c245b291ec"
mkdir -p workspace/local/design
curl -sL "https://styles.refero.design/api/styles/${UUID}" \
     -o "workspace/local/design/${UUID}.json"
```

### 4. Render to `DESIGN.md`

The JSON has a stable shape. Use the renderer at `workspace/dev-knowledge/skills/code/refero_render.py`
(co-located with this skill). Idempotent and deterministic:

```bash
UUID="$UUID" python3 workspace/dev-knowledge/skills/code/refero_render.py
# -> workspace/local/design/<uuid>.DESIGN.md
```

The rendered file is the canonical artifact. Cache it — don't re-render every prompt.

### 5. Wire it into the actual code change

When the UI work lives in a repo (the usual case), copy the rendered file into the project so
future sessions / CI / reviewers see it too:

```bash
cp "workspace/local/design/${UUID}.DESIGN.md" "<repo>/DESIGN.md"
# or, if the repo already has its own DESIGN.md, append under a clearly-marked section:
#   ## Reference: <Brand> (Refero {uuid})
```

Commit it on the same feature branch as the UI work — reviewers need to see the source.

### 6. Generate the UI **strictly** from the DESIGN.md

- Pull color hexes, font families, radii, spacing scale, and component specs **verbatim**
  from the DESIGN.md. Do **not** invent values or substitute close-by Tailwind defaults.
- If a value is missing (e.g. no explicit shadow tokens), say so in the PR description — do
  not silently pick one.
- Tailwind: extend `theme` in `tailwind.config.{js,ts}` with the exact tokens, then use them.
- shadcn / Radix: map each `Components` entry to the matching primitive; preserve radius and
  padding from the spec.
- For motion / `imagery` (gradients, hero shots): replicate intent, not pixels — don't copy
  the brand's actual marketing imagery.

### 7. Verify before opening the PR

- Run `pnpm lint` / `pnpm typecheck` / project-specific gates (see `frontend_local_dev.md`).
- Take 1920x1080 screenshots via `bu screenshot` (`browser_use.md`).
- PR description must include:
  - Refero source URL: `https://styles.refero.design/style/<uuid>`
  - One-line "north star" quote from the DESIGN.md
  - Before / after screenshots

---

## Multiple references

If the user mixes brands ("Stripe colors but Linear's density"), do not merge silently.
Produce a single combined `DESIGN.md` with explicit precedence:

```markdown
## Sources & precedence
1. Colors, gradients → Stripe (refero/<uuidA>)
2. Density, type scale, components → Linear (refero/<uuidB>)
3. Tie-breaker → Stripe
```

This keeps regeneration deterministic.

---

## Brand not in catalog

The catalog is curated, not exhaustive. If `search?q=<name>` returns empty:

1. Use `similar` from a nearby brand's detail response — Refero's own clustering is good.
2. If still nothing, ask the user for: 1) the brand's marketing site URL, 2) primary color,
   3) font family. Build a minimal DESIGN.md by hand from those three plus an inspection of
   the live site (`bu screenshot` + DOM dump). Save under
   `workspace/local/design/manual-<slug>.DESIGN.md` and clearly mark it as agent-authored,
   not from Refero.

---

## Caching & re-use

- One `DESIGN.md` per (brand, uuid) under `workspace/local/design/`.
- Re-resolve only when the user explicitly asks for a different brand or `--refresh`.
- Across sessions: `workspace/local/` is persistent — assume cached files are still valid
  unless older than ~30 days (Refero updates entries occasionally).

---

## Quick reference — common UUIDs

(Verify with `search?q=` before relying — IDs are stable but not guaranteed.)

| Brand | UUID |
|---|---|
| Stripe | `48e5de76-05d5-4c4e-a269-c7c245b291ec` |
| Linear | `90ce5883-bb24-4466-93f7-801cd617b0d1` |
| Cursor | `4e3b4717-84c8-4599-baaf-a343c3d619b6` |
| ElevenLabs | `031056ff-7af1-46db-8daa-115f731c5d26` |
| Mercury | `3172cd4d-118a-4a16-a259-6b634d32322e` |

---

## Anti-patterns

- ❌ Scraping `https://styles.refero.design/style/<uuid>` with `curl` and trying to parse the
  HTML — it's a Next.js SPA, the body is empty until JS runs. Use the API.
- ❌ Pasting the entire `fullResult` JSON (~78 KB) into the model context. Render the
  `DESIGN.md` first — it's 5–10× smaller and far more readable.
- ❌ "Approximating" colors / fonts because the exact value feels off. Ship the brand's value;
  if the user wants a tweak, they'll say so.
- ❌ Forgetting to commit `DESIGN.md` to the repo. Without it, the next agent regenerates from
  scratch and drifts.
- ❌ Using this skill for non-visual tasks (API design, infra, data modelling). It's UI-only.

---

## Cross-references

- `workspace/dev-knowledge/skills/browser_use.md` — for screenshots and live-site inspection when a brand
  is missing from Refero.
- `workspace/dev-knowledge/skills/frontend_local_dev.md` — for running `xpander-mono/frontend` and capturing
  before/after evidence.
- `workspace/dev-knowledge/skills/pr_title_description.md` — Screenshots section is **mandatory** for PRs
  that touch React components; this skill always produces screenshots.

---

## Maintenance

- If the API shape changes (`fullResult.designSystem` keys move), update the renderer at
  `workspace/dev-knowledge/skills/code/refero_render.py` in one place — every downstream task picks it up
  automatically.
- If Refero ever ships an official `DESIGN.md` endpoint, swap steps 3+4 for a single `curl`
  and delete the renderer. Until then, render locally.
