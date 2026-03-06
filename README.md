# autonomy_timer

CLI tool that reads recording durations from vehicles via SSH and logs time to Jira worklogs.

## Setup

**1. Clone the repo**

```bash
git clone https://github.com/brandon-townes-ai/autonomy_timer.git
cd autonomy_timer
```

**2. Create a virtual environment and install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**3. Configure credentials**

Copy `.env.example` to `.env` and fill in your Jira credentials:

```bash
cp .env.example .env
```

```
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your_api_token_here
```

> Generate a Jira API token at: https://id.atlassian.com/manage-profile/security/api-tokens

## Usage

### Single ticket

```bash
autonomy_timer update --issue EC-123
```

### Multiple tickets

```bash
# Space-separated
autonomy_timer update --issues EC-123 EC-456

# Comma-separated
autonomy_timer update --issues EC-123,EC-456

# Repeated flag
autonomy_timer update --issues EC-123 --issues EC-456
```

### Dry run (SSHes and reads durations, skips Jira calls)

```bash
autonomy_timer update --issues EC-123 EC-456 --dry-run
```

### All options

```
--issue       Single Jira issue key
--issues      One or more issue keys (space/comma-separated, or repeat the flag)
--dry-run     SSH and read durations but skip Jira worklog/comment calls
--verbose     Print extra detail (ticket text, processed paths, etc.)
--jira-base-url   Jira base URL (env: JIRA_BASE_URL)
--jira-email      Jira account email (env: JIRA_EMAIL)
--jira-api-token  Jira API token (env: JIRA_API_TOKEN)
```

## How it works

1. Fetches the Jira ticket (description + comments) and extracts recording paths
2. Checks existing `[autonomy-timer]` stamp comments to skip already-processed paths
3. SSHes to each vehicle and reads `drive_info.yaml` for `duration_ns`
4. Aggregates durations and posts a worklog entry to Jira ("Time Spent")
5. Posts an `[autonomy-timer]` stamp comment listing the processed paths

Recording failures are per-path — if one vehicle's file is missing, the rest still process.

### Multi-run / multiple testers

Each run only processes paths not yet stamped. A second tester adding new recordings to the
same ticket will only log their new paths — previously logged paths are skipped automatically.
Jira accumulates the worklog entries, so "Time Spent" reflects the total across all runs.

### Bare bag names

If a ticket contains a bare bag name (e.g. `dev_kom-101_rockwell_haul_20260305_...`) without a
full path, the tool auto-resolves it using the vehicle → hotswap mount mapping:

| Vehicle | Mount |
|---|---|
| `kom-101` | `/media/hotswap2` |
| `rap-107` | `/media/hotswap1` |
