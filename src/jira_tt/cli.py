"""autonomy_timer CLI — update Jira time tracking via SSH-fetched YAML files."""
import os
import subprocess
from typing import Optional

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.status import Status

from jira_tt.formatter import format_minutes
from jira_tt.jira_client import JiraClient
from jira_tt.path_extractor import extract_recording_paths
from jira_tt.remote_reader import load_vehicle_config, ssh_cat_file, is_sshpass_available

load_dotenv()

app = typer.Typer(help="Update Jira time tracking from SSH-fetched drive_info.yaml files.")
console = Console()


@app.callback()
def _main():
    """autonomy_timer — Jira time tracking from YAML."""


@app.command()
def update(
    issue: str = typer.Option(..., "--issue", help="Jira issue key (e.g. RAP-123)"),
    jira_base_url: Optional[str] = typer.Option(None, "--jira-base-url", envvar="JIRA_BASE_URL", help="Jira base URL"),
    jira_email: Optional[str] = typer.Option(None, "--jira-email", envvar="JIRA_EMAIL", help="Jira account email"),
    jira_api_token: Optional[str] = typer.Option(None, "--jira-api-token", envvar="JIRA_API_TOKEN", help="Jira API token"),
    tt_mode: str = typer.Option("spent", "--tt-mode", help="Time field to update: original|spent|remaining"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print plan without making SSH or Jira calls"),
    verbose: bool = typer.Option(False, "--verbose", help="Print extra detail"),
) -> None:
    """Fetch recording paths from a Jira ticket, SSH to read drive_info.yaml, and update time tracking."""

    # --- Validate Jira credentials (fail fast) ---
    missing = [name for name, val in [
        ("JIRA_BASE_URL", jira_base_url),
        ("JIRA_EMAIL", jira_email),
        ("JIRA_API_TOKEN", jira_api_token),
    ] if not val]
    if missing:
        console.print(f"[red]Error:[/red] Missing required Jira credentials: {', '.join(missing)}")
        raise typer.Exit(1)

    client = JiraClient(jira_base_url, jira_email, jira_api_token, verbose=verbose)

    # --- Fetch ticket text ---
    with Status(f"Fetching ticket [bold]{issue}[/bold]...", console=console):
        try:
            ticket_text = client.fetch_issue_text(issue)
        except Exception as exc:
            console.print(f"[red]Error fetching ticket:[/red] {exc}")
            raise typer.Exit(1)

    if verbose:
        console.print(f"Ticket text ({len(ticket_text)} chars):\n{ticket_text[:1000]}")

    # --- Extract recording paths ---
    recordings = extract_recording_paths(ticket_text)
    if not recordings:
        console.print("[red]Error:[/red] No recording paths found on ticket.")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] Found [bold]{len(recordings)}[/bold] recording path(s):")
    for r in recordings:
        console.print(f"  [dim][{r.vehicle}][/dim] {r.path}")

    # --- SSH cat drive_info.yaml for each path ---
    durations: list[int] = []

    for recording in recordings:
        remote_yaml = recording.path + "/drive_info.yaml"

        try:
            config = load_vehicle_config(recording.vehicle)
        except EnvironmentError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1)

        if dry_run:
            console.print(f"\n[dim]Reading:[/dim] {remote_yaml}")
            ssh_cat_file(remote_yaml, config, dry_run=True, verbose=verbose)
            continue

        use_spinner = bool(os.environ.get("VEHICLE_SSH_PASSWORD")) and is_sshpass_available()
        ctx = Status(f"Reading [dim]{remote_yaml}[/dim]...", console=console) if use_spinner else None
        if ctx:
            ctx.start()
        else:
            console.print(f"Reading [dim]{remote_yaml}[/dim]...")
        try:
            yaml_content = ssh_cat_file(remote_yaml, config, dry_run=False, verbose=verbose)
        except subprocess.CalledProcessError:
            if ctx:
                ctx.stop()
            console.print(f"[red]Error:[/red] SSH/cat failed for {remote_yaml}")
            raise typer.Exit(1)
        finally:
            if ctx:
                ctx.stop()

        try:
            parsed = yaml.safe_load(yaml_content)
        except yaml.YAMLError as exc:
            console.print(f"[red]Error:[/red] Failed to parse YAML from {remote_yaml}: {exc}")
            raise typer.Exit(1)

        if not isinstance(parsed, dict) or "duration_ns" not in parsed:
            keys = list(parsed.keys()) if isinstance(parsed, dict) else []
            console.print(f"[red]Error:[/red] 'duration_ns' not found in {remote_yaml}. Available keys: {keys}")
            raise typer.Exit(1)

        duration_ns = parsed["duration_ns"]
        durations.append(duration_ns)
        console.print(f"[green]✓[/green] [dim]{recording.vehicle}[/dim] duration_ns: {duration_ns}")

    if dry_run:
        console.print("\n[yellow]Dry-run complete[/yellow] — no SSH or Jira calls made.")
        return

    # --- Aggregate and format ---
    total_duration_ns = sum(durations)
    formatted, total_seconds = format_minutes(total_duration_ns)

    console.print(f"\n[bold]Total:[/bold] {formatted} ({total_seconds}s)")

    # --- Guard against double-entry ---
    with Status("Checking existing time tracking...", console=console):
        try:
            tt = client.fetch_time_tracking(issue)
        except Exception as exc:
            console.print(f"[red]Error fetching time tracking:[/red] {exc}")
            raise typer.Exit(1)

    field_map = {
        "spent": "timeSpentSeconds",
        "original": "originalEstimateSeconds",
        "remaining": "remainingEstimateSeconds",
    }
    existing_seconds = tt.get(field_map.get(tt_mode, "timeSpentSeconds"), 0) or 0
    if existing_seconds > 0:
        console.print(
            f"[yellow]Skipping:[/yellow] time tracking already set ({existing_seconds}s logged). "
            "Use --tt-mode or clear the field in Jira first."
        )
        return

    # --- Update Jira time tracking ---
    with Status(f"Updating Jira time tracking for [bold]{issue}[/bold]...", console=console):
        try:
            client.update_time_tracking(issue, tt_mode, total_seconds)
        except Exception as exc:
            console.print(f"[red]Jira update failed:[/red] {exc}")
            raise typer.Exit(1)

    console.print(f"[green]✓[/green] Jira time tracking updated: [bold]{formatted}[/bold] logged to [bold]{issue}[/bold]")
