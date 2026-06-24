# Skill — xpander.ai Design System: Tokens, Primitives, Approval Gates

> **Scope:** every UI change in `frontend` and any `xpander-mono` package that ships React.
> The xpander.ai platform already has a mature, opinionated design system — CSS variables,
> shadcn primitives with locked variants, a custom typography scale, and explicit
> do/don't rules in `AGENTS.md`. This skill makes that system **the only source of truth**
> for Gilfoyle, and makes adding anything new an **explicit, user-gated decision**.
>
> **Hard rule:** never invent a color, font size, border style, component variant, or
> token. Either reuse what exists or stop and ask.

---

## Trigger phrases (case-insensitive)

Fire the moment any UI work in `frontend` or `xpander-mono` is requested:

- "add a button / card / modal / page / panel / form / table / dropdown"
- "style this", "theme this", "polish this", "make it look better"
- "new component", "design system", "tokens", "colors", "typography"
- "build a UI for …" / "add a screen for …" inside `frontend` or any `xpander-mono` FE package
- The user pastes a Figma / screenshot / mockup
- Anything that ends up in `src/components/`, `src/modules/*/components/`, or `src/app/**/page.tsx`

**Do NOT trigger** for non-UI work (API routes, hooks without JSX, config, infra).

**Do NOT use the Refero skill on `frontend` or `xpander-mono`.** Refero is for greenfield
projects without a design system. xpander has one. Reuse it.

---

## Why this skill exists

Three recurring failure modes the agent must stop producing:

1. **Inventing tokens** — dropping `#753cff`, `text-purple-500`, or `bg-[rgb(117,60,255)]`
   into a component when `bg-brand-400` already exists. Breaks dark mode, breaks themability.
2. **Inventing variants** — `<Button variant="secondary">` or `<Badge variant="destructive">`
   when those don't exist in `button.tsx` / `badge.tsx`. Compiles fine, falls back to
   default styling silently, ships broken.
3. **Silent extension** — the agent decides on its own to add `--brand-450` or a new
   `text-body-xl2` size because "the design needed it". Tokens proliferate, the system
   rots, reviewers can't tell which values are canonical.

This skill: **read tokens → use tokens → if a real gap exists, ASK the user before extending.**

---

## Token & primitive map (frontend repo)

All paths below are relative to `/agent/data/dev/frontend/`.

### CSS variables — source of truth
- `src/styles/globals.css` — `:root` (light) and `.dark` (dark) blocks. ~123 variables.
  Namespaces:
  - `--background-{page,hover,panel,modal,node-header,node-body,node-footer}`
  - `--border-{primary,secondary,hover}` (used as `border-outline` via Tailwind alias)
  - `--gray-{50,100,200,250,300,350,400,500,600,700,800,900}` (12 stops, theme-aware)
  - `--brand-{100,200,300,400,500,600,700}` (xpander purple — base `#753cff`)
  - `--green-*`, `--red-*`, `--yellow-*`, `--purple-*`, `--orange-*` (status palettes)
  - `--surface-{0,1,2,3,4,6,8,12,16,24,25}` (elevation surfaces)
  - `--text-button`

### Tailwind theme — the only API
- `tailwind.config.ts` — maps every CSS var to a class.
  - **Colors:** use `bg-brand-400`, `text-gray-100`, `border-outline`, `bg-surface-2`,
    etc. Never raw hex, never arbitrary value classes.
  - **Typography:** custom scale, **mandatory**:
    - Headings: `text-h1` (28/36 600), `text-h2` (24/32 600), `text-h3` (20/28 600)
    - Body: `text-body-xs`, `text-body-s`, `text-body-sm`, `text-body-md`, `text-body-lg`
    - Bold variants: `text-body-sb`, `text-body-smb`, `text-body-smbt`, `text-body-mdb`
    - Smallest: `text-body-xxsb` (11px), `text-body-xsb`, `text-body-xsb2` (10px family)
  - **Font:** `font-inter` (only family).
  - **Container:** `2xl: 1440px`.

### shadcn primitives — the only components for primitives
- Location: `src/components/ui/`
- **Always import from `src/components/ui/<name>`. Never write a fresh button/card/badge.**
- Locked variants — read the source before using:
  - **Button** (`button.tsx`): `default | destructive | outline | secondaryButton | ghost | link`
  - **Badge** (`badge.tsx`): `gray | yellow | red | green | default | newGreen | newGray |
    newYellow | newRed | newPurple | darkGray | darkGreen | disabled | brand | darkBrand |
    brightRed | brandSmall | neonGreen | neonRed | newGreen2 | newRed2`
  - Other primitives present: `accordion`, `alert-dialog`, `avatar`, `breadcrumb`, `card`,
    `checkbox`, `dialog`, `divider`, `dropdown-menu`, `dropdown`, `fieldset`, `input`,
    `label`, `popover`, `passwordInput`, `chart`, `gauge`, `loader*`, plus xpander-specific
    composites (`activityCard`, `agentAvatarWithIcon`, `pluginIcon`, `CustomTable`, etc.).
  - For any primitive, **open the file first** and read the `cva` definition before picking a
    variant. If the variant you want isn't there, that's an extension request — see below.

### shadcn config
- `components.json` — alias map: `@/src/components`, `@/src/components/ui`,
  `@/src/utils/styleUtils`. `cssVariables: false` (theme is already in Tailwind).

### Project-specific guidance
- `AGENTS.md` — § Design System Usage and § UI/UX have explicit rules. Re-read before
  big UI changes. Highlights enforced by this skill:
  - **Never** inline styles with hex (`<span style={{color:"#F1FA8C"}}>` is forbidden).
  - **Always** `text-body-*` for text (not `text-sm`/`text-lg` etc.).
  - **Always** `border-outline` for borders (not `border-gray-300`).
  - **Never** `text-white` — use `text-gray-100` (brightest) or `text-gray-200` (labels).
  - **Always** `flex gap-*` not `space-y-*` / `space-x-*`.
  - **Always** `prefixIcon` / `suffixIcon` props on Button — never icon-as-child + flex.

### Module-specific token files (don't override blindly)
- `src/modules/workflows/utils/nodeStyles.ts` — centralized node icon/color mapping.
  Pull from here before hard-coding a graph node color.

---

## Token & primitive map (xpander-mono)

The mono houses multiple FE packages. Behavior:

1. Locate the package — typically under `services/<svc>/frontend/` or
   `packages/<pkg>-ui/`. Run:
   ```bash
   find /agent/data/dev/xpander-mono \
     -maxdepth 4 -name 'tailwind.config.*' -not -path '*/node_modules/*'
   ```
2. **If a package has its own tokens (Tailwind config + globals)** — those are the source
   of truth for *that* package. Same skill rules apply (reuse, ask before extending).
3. **If a package consumes the main `frontend` design system** — use the rules above.
4. **If no Tailwind config exists** — stop and ask which package's tokens to follow.
   Don't guess.

Always read the package's `AGENTS.md` / `CLAUDE.md` first.

---

## Workflow — every UI task

### Step 0. Confirm the system before touching anything
```bash
cd /agent/data/dev/frontend   # or the relevant mono package
grep -E '^\s*--' src/styles/globals.css | wc -l   # var count sanity check
ls src/components/ui                              # available primitives
grep -nE 'variants:' src/components/ui/{button,badge}.tsx | head -20
```
If the file layout differs from this skill's map (e.g. `globals.css` moved, primitives
missing), **stop and ask** before proceeding — the system has changed and the skill
needs an update.

### Step 1. Identify what you need
List the visual elements your change requires:
- colors (background / text / border / status)
- typography (heading / body / weight)
- spacing & layout
- primitive components (button, badge, card, modal, …)
- variants of those primitives

### Step 2. Match each item to an existing token / primitive
For each, the answer must be one of three:

| Answer | Action |
|---|---|
| **Exact match exists** | Use it. No discussion needed. |
| **Close match exists** (±10% off, near color, similar size) | Use the existing token. Don't add a near-duplicate. |
| **No reasonable match** | Stop. Go to Step 4 (approval gate). |

When in doubt, **always pick "close match exists"**. The cost of a 5% color difference
is far lower than the cost of a redundant token.

### Step 3. Implement using existing tokens only
- Tailwind classes only. No raw hex, no arbitrary values (`bg-[#abc]`), no inline styles.
- Body text: `text-body-*`. Headings: `text-h1`/`h2`/`h3`. Never `text-sm`/`text-lg`.
- Borders: `border-outline`. Never `border-gray-*` for outlines.
- Text color: `text-gray-100` (primary) or `text-gray-200` (secondary). Never `text-white`.
- Layout: `flex` + `gap-*`. Never `space-x-*` / `space-y-*`.
- Buttons: `<Button variant="..." prefixIcon={<Icon/>} />`. Never icon-as-child.
- Conditional styling: `cn(...)` helper from `src/utils/styleUtils`, classes only.

### Step 4. Approval gate — when an extension is genuinely needed

If Step 2 produced a "no reasonable match" answer, **do not silently extend**. Stop the
implementation and ask the user before proceeding. Use `xpask_for_information` once the
plan has started; otherwise ask in the response.

The ask must be concrete and actionable:

> ⚠️ Design-system extension request — needs your approval before I proceed.
>
> **What I need:** a 4th tier of brand color between `--brand-300` (#a37cff) and `--brand-400`
> (#753cff). The Figma uses #8c5fff, ~7% brighter than brand-400. I can:
>
> 1. **Use `--brand-300`** (closest existing) — +0 tokens, slightly more lavender than spec.
> 2. **Use `--brand-400`** (also close) — +0 tokens, slightly more saturated than spec.
> 3. **Add `--brand-350: #8c5fff`** — +1 token, exact match. Requires updating both
>    `:root` and `.dark` blocks in `src/styles/globals.css` and adding `350: "var(--brand-350)"`
>    to `tailwind.config.ts`.
>
> Recommendation: option 1 (no token churn). Which do you want?

Never pick option 3 unilaterally. Always present 1 and 2 first.

Also gate via approval:
- New shadcn primitive variant (new `cva` entry in `button.tsx` etc.).
- New typography size (`text-body-xl`, etc.).
- New `--surface-*` level.
- New status color family.
- Switching base color (`baseColor: slate` in `components.json`).
- Anything that touches `tailwind.config.ts` `extend` block.
- Pulling a primitive from shadcn CLI (`pnpm dlx shadcn@latest add <x>`).

### Step 5. After approval — land the extension cleanly
When the user says yes:
1. Update `src/styles/globals.css` — **both `:root` and `.dark` blocks**. Missing the dark
   half is the #1 review-rejection cause for token PRs.
2. Update `tailwind.config.ts` `theme.extend.colors` (or `fontSize`, etc.).
3. Restart dev server (`pnpm dev` HMR doesn't pick up Tailwind config changes reliably).
4. Commit the token addition as a **separate commit** from the feature using it:
   - `chore({ticket}): add brand-350 token (#8c5fff) for <reason>`
   - `feat({ticket}): use brand-350 in <component>`
   This makes review trivial and lets reviewers revert the feature without losing the token.
5. PR description — list every new token under a `## Design tokens added` heading with
   light + dark hex pairs. Reviewers should never have to grep the diff for this.

### Step 6. Verify
- `pnpm compile` (typecheck — see `frontend_local_dev.md` § Compile vs build vs dev).
- `pnpm dev` + `bu screenshot` at 1920×1080, **light AND dark theme**. Both shots in the PR.
- Visually diff against any pre-existing component using the same primitive (e.g. if you
  used `<Button variant="secondaryButton">`, also screenshot an existing
  `secondaryButton` so the reviewer sees consistency).

---

## Quick checklist before opening any UI PR

- [ ] Zero raw hex codes in JSX or CSS files I touched (`grep -nE '#[0-9a-fA-F]{3,8}'`).
- [ ] Zero `text-sm` / `text-lg` / `text-xl` — only `text-body-*` and `text-h*`.
- [ ] Zero `text-white`, zero `border-gray-*` outlines, zero `space-{x,y}-*`.
- [ ] Every Button/Badge variant verified to exist in the primitive's `cva`.
- [ ] If `tailwind.config.ts` or `globals.css` was touched: separate commit, both themes
      updated, listed in PR description.
- [ ] Light + dark screenshots at 1920×1080.

One-shot grep:
```bash
cd /agent/data/dev/frontend
FILES=$(git diff --name-only develop...HEAD -- 'src/**/*.tsx' 'src/**/*.ts' 'src/**/*.css')
echo "$FILES" | xargs -r grep -nE '#[0-9a-fA-F]{3,8}|text-(sm|lg|xl|white)|border-gray|space-[xy]-' || echo OK
```

---

## Anti-patterns (will be rejected in review)

- ❌ `<div style={{ backgroundColor: "#753cff" }} />` — always Tailwind class.
- ❌ `className="bg-[#753cff]"` — arbitrary values bypass tokens.
- ❌ `<Button variant="secondary">` — variant doesn't exist; use `secondaryButton`.
- ❌ `<Badge variant="destructive">` — variant doesn't exist; use `newRed` / `brightRed`.
- ❌ `text-white` / `text-gray-300 (primary)` / `text-gray-400 (primary)` — too dim.
- ❌ `border-gray-400` for outlines — use `border-outline`.
- ❌ `space-y-4` between siblings — use `flex flex-col gap-4`.
- ❌ Adding `--brand-450` to `globals.css` without asking.
- ❌ Adding a new variant to `button.tsx` `cva` block without asking.
- ❌ Adding `text-body-xl` to `tailwind.config.ts` because "the design needed it".
- ❌ Running `pnpm dlx shadcn@latest add tooltip` and committing without asking — it
   pulls a fresh primitive that doesn't match xpander styling defaults.
- ❌ Using the **Refero skill** on `frontend` or `xpander-mono`. Refero = greenfield only.

---

## Cross-references

- `workspace/dev-knowledge/skills/known_repos.md` — paths, branches, integration branch rules.
- `workspace/dev-knowledge/skills/frontend_local_dev.md` — `pnpm compile` vs `dev` vs (never) `build`,
  OTP login, screenshots, the renderer-crash font fix.
- `workspace/dev-knowledge/skills/browser_use.md` — 1920×1080 screenshots in light + dark.
- `workspace/dev-knowledge/skills/pr_title_description.md` — mandatory Screenshots section for any
  React-touching PR; this skill always produces screenshots.
- `workspace/dev-knowledge/skills/refero_design_styles.md` — only for greenfield projects without a
  system. **Not** for `frontend` or `xpander-mono`.
- `frontend/AGENTS.md` § Design System Usage — the canonical project rules. This skill is
  the agent-side enforcement layer for them.

---

## Maintenance

If the design system shifts — new namespace, new primitive directory, base color change,
dark theme overhaul — update this skill **before** the next UI task. Specifically:

- Token namespaces: re-run `grep -E '^\s*--[a-z]+-' globals.css | sed 's/:.*//' | sort -u`
  and refresh the namespace list above.
- Primitive variants: re-grep `cva({` blocks under `src/components/ui/` and refresh the
  Button/Badge tables.
- Typography: re-read `tailwind.config.ts` `fontSize` block.

Auto-detect drift:
```bash
cd /agent/data/dev/frontend
current=$(grep -cE '^\s*--' src/styles/globals.css)
echo "globals.css vars: $current (skill says ~123)"
```
If the count is significantly different, the system has moved — update this skill first.
