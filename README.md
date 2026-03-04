# autonomy_timer

CLI tool that reads `duration_ns` from a YAML file and updates Jira time tracking.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your_api_token_here
```

## Usage

```bash
autonomy_timer update --issue PROJ-123 --yaml-dir ./runs/latest
```

### Dry run (no Jira API calls)

```bash
autonomy_timer update --issue PROJ-123 --yaml-dir ./runs/latest --dry-run
```

### All options

```
--issue               Jira issue key (required)
--yaml-dir            Directory to search for YAML files (required)
--yaml-file           Explicit YAML file path (skips directory search)
--yaml-key            Key to read from YAML (default: duration_ns)
--jira-base-url       Jira base URL (env: JIRA_BASE_URL)
--jira-email          Jira account email (env: JIRA_EMAIL)
--jira-api-token      Jira API token (env: JIRA_API_TOKEN)
--mode                Time field to update: original|spent|remaining (default: spent)
--also-write-display  Write formatted duration to Jira (default: true)
--display-target      comment|customfield:<id> (default: comment)
--dry-run             Print output without calling Jira API
--verbose             Print extra detail
```

## How it works

1. Finds the most recently modified `.yaml`/`.yml` file in `--yaml-dir`
2. Extracts the value at `--yaml-key` (default: `duration_ns`, in nanoseconds)
3. Converts to minutes and formats:
   - `< 1,000` → `2.00 minutes`
   - `1,000–999,999` → `12.34K minutes`
   - `≥ 1,000,000` → `29.54M minutes`
4. Updates the Jira issue's time tracking field
5. Optionally posts the formatted string as a comment
