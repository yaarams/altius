# Skill: Managing LLM Providers in the Frontend

This skill covers everything needed to add, update, or remove LLM models in the xpander.ai frontend via Supabase migrations.

---

## Overview

LLM providers are stored in the `public.llm_providers` table in Supabase. Each provider row contains a `models` JSONB column holding a list of model objects.

The standard approach: **DELETE** existing row by `internal_identifier`, then **INSERT** full updated model list. This is a full-replacement pattern — every migration rewrites the entire model list for the affected provider(s).

---

## Migration File Conventions

| Field | Convention |
|---|---|
| **Location** | `/supabase/migrations/` |
| **Naming** | `{YYYYMMDDHHMMSS}_{short_description}.sql` |
| **Timestamp** | UTC, strictly increasing — use `date -u +%Y%m%d%H%M%S` |

Generate timestamp: `date -u +%Y%m%d%H%M%S`

---

## Provider `internal_identifier` Reference

| Provider | `internal_identifier` | Logo key |
|---|---|---|
| Anthropic | `anthropic` | `anthropic` |
| Amazon Bedrock | `amazon_bedrock` | `bedrock` |
| OpenAI | `openai` | `openai` |
| Google AI Studio | `google_ai_studio` | `google` |
| Helicone | `helicone` | `helicone` |
| OpenRouter | `open_router` | `open_router` |
| Nebius | `nebius` | `nebius` |
| Tzafon | `tzafon` | `tzafon` |
| ByteDance | `bytedance` | `bytedance` |

---

## Model Object Schema

```json
{
  "model_id": "<provider-specific-id>",
  "description": "<human-readable description>",
  "display_name": "<short display name>",
  "input_tokens": 200000,
  "output_tokens": 4096,
  "tier": 1
}
```

### Tier Meaning
| Tier | Meaning |
|---|---|
| 1 | Most capable / premium (Opus-class, flagship) |
| 2 | Balanced / mid-range (Sonnet-class) |
| 3 | Fast / affordable (Haiku/mini-class) |

---

## OpenAI Model IDs (as of April 2026)

| Display Name | `model_id` | Tier |
|---|---|---|
| GPT-5.5 | `gpt-5.5` | 1 |
| GPT-5.4 | `gpt-5.4` | 1 |
| GPT-5.3 Chat | `gpt-5.3-chat-latest` | 1 |
| GPT-5.2 | `gpt-5.2` | 1 |
| GPT-5.1 | `gpt-5.1` | 2 |
| GPT-5 Nano | `gpt-5-nano` | 3 |
| GPT-5 | `gpt-5` | 2 |
| GPT-5 Mini | `gpt-5-mini` | 3 |
| GPT-4.1 | `gpt-4.1` | 2 |
| GPT-4.1-mini | `gpt-4.1-mini` | 3 |
| GPT-4o | `gpt-4o` | 2 |
| GPT-4o Mini | `gpt-4o-mini` | 3 |
| GPT-4 Turbo | `gpt-4-turbo` | 2 |
| GPT-3.5 Turbo | `gpt-3.5-turbo` | 3 |

**GPT-5.5 notes**: API identifier `gpt-5.5`, announced April 23 2026 (https://openai.com/index/introducing-gpt-5-5/), codename "Spud". Default model in OpenAI Codex. Context: 1M tokens, output: 128K tokens, Tier 1 flagship.

---

## Anthropic Direct Model IDs (as of April 2026)

| Display Name | `model_id` | Tier |
|---|---|---|
| Claude Opus 4.7 | `claude-opus-4-7` | 1 |
| Claude Sonnet 4.6 | `claude-sonnet-4-6` | 1 |
| Claude Opus 4.6 | `claude-opus-4-6` | 1 |
| Claude Sonnet 4.5 | `claude-sonnet-4-5` | 1 |
| Claude Opus 4.5 | `claude-opus-4-5` | 1 |
| Claude Opus 4 | `claude-opus-4` | 1 |
| Claude Sonnet 4 | `claude-sonnet-4` | 2 |
| Claude Sonnet 3.7 | `claude-3-7-sonnet-20250219` | 2 |
| Claude Sonnet 3.5 | `claude-3-5-sonnet-20241022` | 2 |

---

## Amazon Bedrock Model IDs (as of April 2026)

Bedrock uses different ID formats for Anthropic models:
- Cross-region inference profiles: `global.anthropic.{model-id}` or `us.anthropic.{model-id}-v1:0`
- Direct model IDs: `anthropic.{model-id}`

| Display Name | `model_id` | Tier |
|---|---|---|
| Claude Opus 4.7 | `global.anthropic.claude-opus-4-7` | 1 |
| Claude Sonnet 4.6 | `global.anthropic.claude-sonnet-4-6` | 1 |
| Claude Opus 4.6 | `global.anthropic.claude-opus-4-6-v1` | 1 |
| Claude Sonnet 4.5 | `global.anthropic.claude-sonnet-4-5-v1:0` | 1 |
| Claude Opus 4 | `anthropic.claude-opus-4-20250514` | 1 |
| Claude Sonnet 4 | `anthropic.claude-sonnet-4-20250514` | 2 |
| Claude Sonnet 3.7 | `us.anthropic.claude-3-7-sonnet-20250219-v1:0` | 2 |
| Claude Sonnet 3.5 | `anthropic.claude-3-5-sonnet-20241022` | 2 |
| Claude Haiku 3.5 | `anthropic.claude-3-5-haiku-20241022` | 3 |
| Amazon Titan Text Express | `amazon.titan-text-express-v1` | 3 |

---

## Migration SQL Pattern

```sql
-- {Provider Name}
DELETE FROM public.llm_providers WHERE internal_identifier = '{internal_identifier}';
INSERT INTO public.llm_providers (id, name, internal_identifier, logo, models)
VALUES (
    gen_random_uuid(),
    '{Display Name}',
    '{internal_identifier}',
    '{logo_key}',
    $$[
  {
    "model_id": "...",
    "description": "...",
    "display_name": "...",
    "input_tokens": 200000,
    "output_tokens": 4096,
    "tier": 1
  }
]$$::jsonb
);
```

Always use dollar-quoting (`$$...$$`) for multi-line JSON arrays.

---

## Step-by-Step: Adding a New Model

1. Identify the provider(s) to update
2. Find correct model ID from official docs
3. For Bedrock: determine inference profile ID format (global.anthropic.* pattern for newer models)
4. Find latest migration for those providers:
```bash
ls supabase/migrations/ | sort | grep -E '(anthropic|bedrock|llm|model)' | tail -5
cat supabase/migrations/{latest_relevant}.sql
```
5. Generate timestamp: `date -u +%Y%m%d%H%M%S`
6. Create migration file and write DELETE + INSERT for each provider
7. Place new models at the **TOP** of each model list (newest first)
8. Commit with co-author trailer and open PR to develop

---

## Checklist Before Committing

- [ ] Timestamp is unique and greater than all existing migration timestamps
- [ ] Full model list preserved (no models accidentally dropped)
- [ ] New model placed at top of list (most recent first ordering)
- [ ] Correct model_id format per provider (Anthropic format differs from Bedrock format)
- [ ] `tier` set correctly (1=flagship, 2=balanced, 3=fast)
- [ ] `input_tokens` / `output_tokens` match official specs
- [ ] Dollar-quoting used for multi-line JSON
- [ ] PR targets `develop` branch

---

## Branch and Commit Format

```
Branch:  feature/develop/{TICKET-NUMBER}
Commit:  feat({TICKET-NUMBER}): add {model-name} to anthropic and bedrock llm providers

Co-authored-by: xpander.ai <dev@xpander.ai>
```
