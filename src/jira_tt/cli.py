"""autonomy_timer CLI — update Jira time tracking via SSH-fetched YAML files."""
import os
import subprocess
from datetime import datetime, timezone
from typing import List, Optional

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.status import Status
from rich.table import Table

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


def _stamp_comment(paths: list[str], seconds: int, formatted: str) -> str:
    """Build the [autonomy-timer] comment body used as a processed-paths log."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path_lines = "\n".join(paths)
    return f"[autonomy-timer] {ts}\n{path_lines}\nlogged: {seconds}s ({formatted})"


def _process_issue(
    client: JiraClient,
    issue: str,
    dry_run: bool,
    verbose: bool,
) -> tuple[bool, str]:
    """Run the full pipeline for a single issue. Returns (success, message)."""

    # --- Fetch ticket text + already-processed paths ---
    with Status(f"Fetching ticket [bold]{issue}[/bold]...", console=console):
        try:
            ticket_text = client.fetch_issue_text(issue)
            processed_paths = client.fetch_processed_paths(issue)
        except Exception as exc:
            return False, f"Error fetching ticket: {exc}"

    if verbose:
        console.print(f"Ticket text ({len(ticket_text)} chars):\n{ticket_text[:1000]}")
        if processed_paths:
            console.print(f"Already processed ({len(processed_paths)} path(s)): {processed_paths}")

    # --- Extract recording paths ---
    all_recordings = extract_recording_paths(ticket_text)
    if not all_recordings:
        return False, "No recording paths found on ticket."

    # --- Filter to only new (unprocessed) paths ---
    new_recordings = [r for r in all_recordings if r.path not in processed_paths]
    skipped = len(all_recordings) - len(new_recordings)

    if skipped:
        console.print(f"[dim]Skipping {skipped} already-logged path(s).[/dim]")

    if not new_recordings:
        return True, "nothing new — all paths already logged"

    console.print(f"[green]✓[/green] Found [bold]{len(new_recordings)}[/bold] new recording path(s):")
    for r in new_recordings:
        console.print(f"  [dim][{r.vehicle}][/dim] {r.path}")

    # --- SSH cat drive_info.yaml for each new path ---
    durations: list[int] = []
    failed_recordings: list[str] = []
    successful_recordings: list[str] = []

    for recording in new_recordings:
        try:
            config = load_vehicle_config(recording.vehicle)
        except EnvironmentError as exc:
            console.print(f"[red]✗[/red] {recording.vehicle}: {exc}")
            failed_recordings.append(recording.path)
            continue

        yaml_content = None
        resolved_path = None
        for candidate in recording.candidates:
            remote_yaml = candidate + "/drive_info.yaml"
            use_spinner = bool(os.environ.get("VEHICLE_SSH_PASSWORD")) and is_sshpass_available()
            ctx = Status(f"Reading [dim]{remote_yaml}[/dim]...", console=console) if use_spinner else None
            if ctx:
                ctx.start()
            else:
                console.print(f"Reading [dim]{remote_yaml}[/dim]...")
            try:
                yaml_content = ssh_cat_file(remote_yaml, config, dry_run=False, verbose=verbose)
                resolved_path = candidate
                if ctx:
                    ctx.stop()
                break
            except subprocess.CalledProcessError:
                if ctx:
                    ctx.stop()
                if len(recording.candidates) > 1:
                    console.print(f"[dim]  {remote_yaml} not found, trying next mount...[/dim]")

        if yaml_content is None:
            console.print(f"[red]✗[/red] SSH/cat failed for all candidates of {recording.path}")
            failed_recordings.append(recording.path)
            continue

        try:
            parsed = yaml.safe_load(yaml_content)
        except yaml.YAMLError as exc:
            console.print(f"[red]✗[/red] Failed to parse YAML from {remote_yaml}: {exc}")
            failed_recordings.append(recording.path)
            continue

        if not isinstance(parsed, dict) or "duration_ns" not in parsed:
            keys = list(parsed.keys()) if isinstance(parsed, dict) else []
            console.print(f"[red]✗[/red] 'duration_ns' not found in {remote_yaml}. Available keys: {keys}")
            failed_recordings.append(recording.path)
            continue

        duration_ns = parsed["duration_ns"]
        durations.append(duration_ns)
        successful_recordings.append(resolved_path)
        fmt, _ = format_minutes(duration_ns)
        console.print(f"[green]✓[/green] [dim]{recording.vehicle}[/dim] duration_ns: {duration_ns} ({fmt})")

    if not durations:
        return False, f"all {len(failed_recordings)} recording(s) failed to read"

    # --- Aggregate and format ---
    total_duration_ns = sum(durations)
    formatted, total_seconds = format_minutes(total_duration_ns)

    console.print(f"\n[bold]Total:[/bold] {formatted} ({total_seconds}s)")

    if dry_run:
        return True, f"dry-run — would log {formatted}"

    # --- Log worklog entry + stamp comment ---
    if failed_recordings:
        console.print(f"[yellow]Warning:[/yellow] {len(failed_recordings)} recording(s) skipped due to errors — only successful recordings will be stamped.")
    stamp = _stamp_comment(successful_recordings, total_seconds, formatted)

    with Status(f"Logging worklog for [bold]{issue}[/bold]...", console=console):
        try:
            client.add_worklog(issue, total_seconds)
        except Exception as exc:
            return False, f"Jira worklog failed: {exc}"

    with Status("Posting processed-paths stamp...", console=console):
        try:
            client.add_comment(issue, stamp)
        except Exception as exc:
            return False, f"Failed to post stamp comment: {exc}"

    return True, formatted


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def update(
    ctx: typer.Context,
    issue: Optional[str] = typer.Option(None, "--issue", help="Single Jira issue key (e.g. RAP-123)"),
    issues_raw: Optional[List[str]] = typer.Option(None, "--issues", help="Jira issue key(s); repeat or comma/space-separate: --issues EC-1 EC-2 EC-3"),
    jira_base_url: Optional[str] = typer.Option(None, "--jira-base-url", envvar="JIRA_BASE_URL", help="Jira base URL"),
    jira_email: Optional[str] = typer.Option(None, "--jira-email", envvar="JIRA_EMAIL", help="Jira account email"),
    jira_api_token: Optional[str] = typer.Option(None, "--jira-api-token", envvar="JIRA_API_TOKEN", help="Jira API token"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print plan without making SSH or Jira calls"),
    verbose: bool = typer.Option(False, "--verbose", help="Print extra detail"),
) -> None:
    """Fetch recording paths from a Jira ticket, SSH to read drive_info.yaml, and update time tracking."""

    # --- Resolve issue list (exactly one of --issue / --issues required) ---
    # ctx.args captures any extra positional tokens the shell passed (e.g. the space-separated
    # values after --issues EC-15455, EC-15466 that click couldn't bind to a flag).
    if issue and (issues_raw or ctx.args):
        console.print("[red]Error:[/red] Use either --issue or --issues, not both.")
        raise typer.Exit(1)
    if not issue and not issues_raw and not ctx.args:
        console.print("[red]Error:[/red] Provide --issue KEY or --issues KEY1 KEY2 (space/comma-separated).")
        raise typer.Exit(1)

    if issue:
        issues: list[str] = [issue]
    else:
        raw_tokens = list(issues_raw or []) + list(ctx.args or [])
        issues = []
        for item in raw_tokens:
            issues.extend(i.strip() for i in item.replace(",", " ").split() if i.strip())
        if not issues:
            console.print("[red]Error:[/red] --issues contained no valid keys.")
            raise typer.Exit(1)

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

    # --- Process each issue ---
    results: list[tuple[str, bool, str]] = []  # (issue_key, success, message)
    any_failed = False

    for issue_key in issues:
        if len(issues) > 1:
            console.rule(f"[bold]{issue_key}[/bold]")
        success, message = _process_issue(client, issue_key, dry_run, verbose)
        results.append((issue_key, success, message))
        if not success:
            any_failed = True
            console.print(f"[red]✗[/red] {issue_key}: {message}")
        elif len(issues) == 1:
            # Single-ticket path: clean success output
            if dry_run:
                console.print("\n[yellow]Dry-run complete[/yellow] — no SSH or Jira calls made.")
            elif message.startswith("nothing new"):
                console.print(f"[yellow]Nothing to log:[/yellow] {message}")
            else:
                console.print(
                    f"[green]✓[/green] Worklog updated: [bold]{message}[/bold] logged to [bold]{issue_key}[/bold]"
                )

    # --- Summary table (multi-ticket only) ---
    if len(issues) > 1:
        console.print()
        table = Table(show_header=True, header_style="bold")
        table.add_column("Issue")
        table.add_column("Result")
        table.add_column("Duration / Note")

        for issue_key, success, message in results:
            if not success:
                result_cell = "[red]✗[/red]"
            elif message.startswith("nothing new"):
                result_cell = "[yellow]skipped[/yellow]"
            else:
                result_cell = "[green]✓[/green]"
            table.add_row(issue_key, result_cell, message)

        console.print(table)

        if dry_run:
            console.print("\n[yellow]Dry-run complete[/yellow] — no SSH or Jira calls made.")

    if any_failed:
        raise typer.Exit(1)
