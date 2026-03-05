# autonomy_timer

CLI tool that reads recording paths from a Jira ticket, SSHs into vehicles to fetch `drive_info.yaml`, aggregates `duration_ns` across all runs, and updates Jira time tracking.

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
JIRA_API_TOKEN=your_api_token_here  # https://id.atlassian.com/manage-profile/security/api-tokens

# SSH password for all vehicles (optional — requires sshpass: brew install hudochenkov/sshpass/sshpass)
VEHICLE_SSH_PASSWORD=

VEHICLE_RAP107_HOST=
VEHICLE_RAP107_USER=
VEHICLE_RAP107_PORT=22

VEHICLE_KOM101_HOST=
VEHICLE_KOM101_USER=
VEHICLE_KOM101_PORT=22
```

## Usage

```bash
autonomy_timer update --issue EC-xxxx
```

### Dry run (no SSH or Jira calls)

```bash
autonomy_timer update --issue EC-xxxx --dry-run
```

### All options

```
--issue          Jira issue key (required)
--jira-base-url  Jira base URL (env: JIRA_BASE_URL)
--jira-email     Jira account email (env: JIRA_EMAIL)
--jira-api-token Jira API token (env: JIRA_API_TOKEN)
--tt-mode        Time field to update: original|spent|remaining (default: spent)
--dry-run        Print plan without making SSH or Jira calls
--verbose        Print extra detail
```

## How it works

1. Fetches the Jira ticket description and comments
2. Scans for recording paths matching `/media/hotswap[1|2]/<vehicle>/<date>/<run>/`
3. SSHs into each vehicle and cats `drive_info.yaml` from the run directory
4. Aggregates all `duration_ns` values and converts to minutes
5. Checks existing time tracking — skips if already set (double-entry protection)
6. Updates the Jira issue's time tracking field

## Adding a new vehicle

Add its SSH config to `.env`:

```
VEHICLE_<NAME>_HOST=
VEHICLE_<NAME>_USER=
VEHICLE_<NAME>_PORT=22
```

Where `<NAME>` is the vehicle ID uppercased with hyphens removed (e.g. `rap-107` → `RAP107`).
