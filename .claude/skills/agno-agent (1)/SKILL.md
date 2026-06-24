---
name: agno-agent
description: >
  Scaffold a complete agno framework agent using SOLID dependency injection.
  Generates all 5 files (interfaces.py, config.py, providers.py, agent.py, {name}_runner.py)
  wired with the ModelProvider/ToolProvider protocol pattern and frozen dataclass config.
  Use this skill whenever the user wants to create, build, scaffold, or generate an agno agent,
  even if they say "new agent", "build an AI agent with agno", "agno project", or just
  "help me set up an agno agent for X". Always use this skill when agno is mentioned alongside
  agent creation or tool integration.
---

# Agno Agent Scaffold

Generate a production-ready agno agent using SOLID dependency injection. The output is 5 files
that follow the ModelProvider/ToolProvider protocol pattern from the reference codebase.

## Step 1: Gather intent

Ask the user (all at once, not one at a time):

1. **Agent purpose** — what does the agent do? (e.g. "manages GitHub issues", "searches the web")
2. **Agent name** — short PascalCase name (e.g. `GitHubAssistant`). Default: derive from purpose.
3. **Tools** — which agno integrations? Show the categorized list below and let them pick.
4. **Model** — which Claude model? Default: `claude-sonnet-4-6`
5. **Output directory** — where to write files? Default: `.` (current directory)

If the user's original message already answers some of these, skip asking for those.

## Step 2: Tool catalog

Present these grouped options. Each entry shows: tool name → agno class → env var(s) needed (blank = no API key).

### Communication
| Tool | Agno class | Env var |
|------|-----------|---------|
| Slack | `SlackTools` | `SLACK_BOT_TOKEN` |
| Discord | `DiscordTools` | `DISCORD_BOT_TOKEN` |
| Gmail | `GmailTools` | OAuth (see agno docs) |
| Twilio (SMS) | `TwilioTools` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| Telegram | `TelegramTools` | `TELEGRAM_BOT_TOKEN` |

### Development
| Tool | Agno class | Env var |
|------|-----------|---------|
| GitHub | `GithubTools` | `GITHUB_ACCESS_TOKEN` |
| GitLab | `GitlabTools` | `GITLAB_ACCESS_TOKEN` |
| Jira | `JiraTools` | `JIRA_SERVER_URL`, `JIRA_USERNAME`, `JIRA_TOKEN` |
| Linear | `LinearTools` | `LINEAR_API_KEY` |
| Bitbucket | `BitbucketTools` | `BITBUCKET_USERNAME`, `BITBUCKET_APP_PASSWORD` |

### Search & Web
| Tool | Agno class | Env var |
|------|-----------|---------|
| Tavily | `TavilyTools` | `TAVILY_API_KEY` |
| DuckDuckGo | `DuckDuckGoTools` | *(none)* |
| SerpAPI | `SerpApiTools` | `SERPAPI_API_KEY` |
| Exa | `ExaTools` | `EXA_API_KEY` |
| Wikipedia | `WikipediaTools` | *(none)* |
| HackerNews | `HackerNewsTools` | *(none)* |

### Productivity
| Tool | Agno class | Env var |
|------|-----------|---------|
| Notion | `NotionTools` | `NOTION_API_KEY` |
| Google Drive | `GoogleDriveTools` | OAuth (see agno docs) |
| Google Sheets | `GoogleSheetsTools` | OAuth (see agno docs) |
| Confluence | `ConfluenceTools` | `CONFLUENCE_URL`, `CONFLUENCE_USERNAME`, `CONFLUENCE_TOKEN` |
| Trello | `TrelloTools` | `TRELLO_API_KEY`, `TRELLO_TOKEN` |
| Todoist | `TodoistTools` | `TODOIST_API_TOKEN` |

### Data & Analysis
| Tool | Agno class | Env var |
|------|-----------|---------|
| PostgreSQL | `PostgresTools` | `POSTGRES_URL` |
| DuckDB | `DuckDbTools` | *(none)* |
| BigQuery | `BigQueryTools` | GCP credentials |
| Pandas | `PandasTools` | *(none)* |
| CSV | `CsvTools` | *(none)* |
| YFinance | `YFinanceTools` | *(none)* |

### Media & Content
| Tool | Agno class | Env var |
|------|-----------|---------|
| YouTube | `YouTubeTools` | *(none)* |
| Reddit | `RedditTools` | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` |
| Arxiv | `ArxivTools` | *(none)* |
| PubMed | `PubmedTools` | *(none)* |

### Utilities
| Tool | Agno class | Env var |
|------|-----------|---------|
| Shell | `ShellTools` | *(none)* |
| File system | `LocalFileSystemTools` | *(none)* |
| Python | `PythonTools` | *(none)* |
| Calculator | `CalculatorTools` | *(none)* |
| Email (SMTP) | `EmailTools` | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD` |

## Step 3: Generate files

Write all 5 files to the output directory. Use exact filenames: `interfaces.py`, `config.py`,
`providers.py`, `agent.py`, `{snake_name}_runner.py` where `snake_name` is the agent name in
snake_case (e.g. `GitHubAssistant` → `github_assistant_runner.py`).

### interfaces.py

Always identical — copy exactly:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class ModelProvider(Protocol):
    def get_model(self): ...


@runtime_checkable
class ToolProvider(Protocol):
    def get_tools(self) -> list: ...
```

### config.py

One frozen dataclass named `{AgentName}Config`. Include:
- `anthropic_api_key: str`
- One field per tool env var (e.g. `slack_bot_token: str` for Slack)
- `model_id: str = "{chosen_model}"`
- `agent_name: str = "{AgentName}"`
- `max_tokens: int = 4096`
- `markdown: bool = True`
- `show_tool_calls: bool = True`
- `instructions: list[str]` — 3-5 instructions tailored to what the agent does
- `from_env()` classmethod that reads all required env vars, collects missing ones, raises `EnvironmentError` with a clear message listing all missing vars

Tools with no API key (DuckDuckGo, HackerNews, etc.) need no config field.

### providers.py

One `ClaudeModelProvider` class plus one `{ToolName}ToolProvider` per chosen tool. Each:
- Takes the config dataclass in `__init__`
- Implements `get_model()` or `get_tools() -> list`
- Uses the correct import path: `from agno.tools.{module} import {ClassName}`
- Passes the API key/token from config to the tool constructor

End with protocol verification assertions (copy pattern from reference):
```python
_: ModelProvider = ClaudeModelProvider.__new__(ClaudeModelProvider)
_: ToolProvider = {ToolName}ToolProvider.__new__({ToolName}ToolProvider)
```

For tools that take no API key, the ToolProvider `__init__` still takes the config for consistency
but ignores the fields it doesn't need.

Correct agno model import: `from agno.models.anthropic import Claude`

### agent.py

Always identical to the reference — copy exactly:

```python
from agno.agent import Agent

from interfaces import ModelProvider, ToolProvider


class AgentBuilder:
    def __init__(
        self,
        config,
        model_provider: ModelProvider,
        tool_provider: ToolProvider,
    ) -> None:
        self._config = config
        self._model_provider = model_provider
        self._tool_provider = tool_provider

    def build(self) -> Agent:
        return Agent(
            name=self._config.agent_name,
            model=self._model_provider.get_model(),
            tools=self._tool_provider.get_tools(),
            instructions=self._config.instructions,
            markdown=self._config.markdown,
            show_tool_calls=self._config.show_tool_calls,
        )
```

### {snake_name}_runner.py

```python
"""Entry point — {AgentName} agent."""

import sys
from dotenv import load_dotenv

from agent import AgentBuilder
from config import {AgentName}Config
from providers import ClaudeModelProvider, {ToolName}ToolProvider


def build_agent():
    load_dotenv()
    config = {AgentName}Config.from_env()
    return AgentBuilder(
        config=config,
        model_provider=ClaudeModelProvider(config),
        tool_provider={ToolName}ToolProvider(config),
    ).build()


def run_interactive() -> None:
    agent = build_agent()
    print(f"Agent '{agent.name}' ready. Type 'exit' to quit.\n")
    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not prompt:
            continue
        if prompt.lower() in {"exit", "quit"}:
            break
        agent.print_response(prompt, stream=True)


def run_once(prompt: str) -> None:
    build_agent().print_response(prompt)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_once(" ".join(sys.argv[1:]))
    else:
        run_interactive()
```

**Multiple tools**: if the user picked more than one tool, use a `MultiToolProvider` that
combines them:

```python
class MultiToolProvider:
    def __init__(self, config) -> None:
        self._providers = [
            {Tool1}ToolProvider(config),
            {Tool2}ToolProvider(config),
        ]

    def get_tools(self) -> list:
        tools = []
        for p in self._providers:
            tools.extend(p.get_tools())
        return tools
```

Add protocol verification: `_: ToolProvider = MultiToolProvider.__new__(MultiToolProvider)`

## Step 4: .env.example

Write a `.env.example` file listing all required env vars with blank values and a comment
describing each one. Always include `ANTHROPIC_API_KEY`. Only include env vars actually needed
by the chosen tools.

Example format:
```
ANTHROPIC_API_KEY=        # Anthropic API key — get from console.anthropic.com
SLACK_BOT_TOKEN=          # Slack bot OAuth token — starts with xoxb-
```

## Step 5: Confirm and summarize

After writing files, print a summary table:

```
Files written to {output_dir}:
  interfaces.py
  config.py
  providers.py
  agent.py
  {snake_name}_runner.py
  .env.example

Required env vars:
  ANTHROPIC_API_KEY
  {any tool-specific vars}

Run:
  python -m venv .venv && source .venv/bin/activate
  pip install agno anthropic python-dotenv
  cp .env.example .env   # fill in your keys
  python {snake_name}_runner.py
```

If `agno` and `python-dotenv` are already in a `requirements.txt` in the output directory,
skip mentioning the pip install step.

## Notes

- If the user later wants to add a tool: implement a new `ToolProvider` in `providers.py` and
  inject it in the runner. Never edit `agent.py` or `interfaces.py`.
- If the user wants a different model provider (OpenAI, Gemini, etc.): implement a new
  `ModelProvider` in `providers.py`. The `agent.py` and runner stay unchanged.
- `AgentConfig` is frozen — add fields only by constructing a new instance or subclassing.
