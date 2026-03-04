"""autonomy_timer CLI — update Jira time tracking from a YAML duration_ns value."""
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from jira_tt.formatter import format_minutes
from jira_tt.yaml_parser import extract_value, find_yaml_file
from jira_tt.jira_client import JiraClient

load_dotenv()

app = typer.Typer(help="Update Jira time tracking from a YAML file containing duration_ns.")


@app.callback()
def _main():
    """autonomy_timer — Jira time tracking from YAML."""


@app.command()
def update(
    issue: str = typer.Option(..., "--issue", help="Jira issue key (e.g. PROJ-123)"),
    yaml_dir: str = typer.Option(..., "--yaml-dir", help="Directory to search for YAML files"),
    yaml_file: Optional[str] = typer.Option(None, "--yaml-file", help="Explicit YAML file path (overrides --yaml-dir search)"),
    yaml_key: str = typer.Option("duration_ns", "--yaml-key", help="Key to read from the YAML file"),
    jira_base_url: Optional[str] = typer.Option(None, "--jira-base-url", envvar="JIRA_BASE_URL", help="Jira base URL"),
    jira_email: Optional[str] = typer.Option(None, "--jira-email", envvar="JIRA_EMAIL", help="Jira account email"),
    jira_api_token: Optional[str] = typer.Option(None, "--jira-api-token", envvar="JIRA_API_TOKEN", help="Jira API token"),
    mode: str = typer.Option("spent", "--mode", help="Time field to update: original|spent|remaining"),
    also_write_display: bool = typer.Option(True, "--also-write-display/--no-also-write-display", help="Write formatted duration to Jira"),
    display_target: str = typer.Option("comment", "--display-target", help="Where to write the display: comment|customfield:<id>"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without calling Jira API"),
    verbose: bool = typer.Option(False, "--verbose", help="Print extra detail"),
) -> None:
    """Read duration_ns from a YAML file and update Jira time tracking."""

    # --- Resolve YAML file ---
    if yaml_file:
        resolved_yaml = Path(yaml_file)
        if not resolved_yaml.is_file():
            typer.echo(f"Error: YAML file not found: {yaml_file}", err=True)
            raise typer.Exit(1)
    else:
        try:
            resolved_yaml = find_yaml_file(yaml_dir)
        except Exception as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1)

    # --- Extract value ---
    try:
        duration_ns = extract_value(resolved_yaml, yaml_key)
    except (KeyError, TypeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    # --- Format ---
    formatted, total_seconds = format_minutes(duration_ns)

    # --- Output header ---
    typer.echo(f"Issue:       {issue}")
    typer.echo(f"YAML file:   {resolved_yaml}")
    typer.echo(f"{yaml_key}: {duration_ns}")
    typer.echo(f"Formatted:   {formatted}")

    if dry_run:
        typer.echo("Jira update: (dry-run — no API calls made)")
        return

    # --- Validate auth ---
    missing = [name for name, val in [
        ("JIRA_BASE_URL", jira_base_url),
        ("JIRA_EMAIL", jira_email),
        ("JIRA_API_TOKEN", jira_api_token),
    ] if not val]
    if missing:
        typer.echo(f"Error: Missing required Jira credentials: {', '.join(missing)}", err=True)
        raise typer.Exit(1)

    client = JiraClient(jira_base_url, jira_email, jira_api_token, verbose=verbose)

    # --- Validate issue ---
    try:
        issue_data = client.validate_issue(issue)
        if verbose:
            summary = issue_data.get("fields", {}).get("summary", "")
            typer.echo(f"Issue title: {summary}")
    except Exception as exc:
        typer.echo(f"Error validating issue: {exc}", err=True)
        raise typer.Exit(1)

    # --- Update time tracking ---
    try:
        client.update_time_tracking(issue, mode, total_seconds)
    except Exception as exc:
        typer.echo(f"Jira update: ✗ failed — {exc}", err=True)
        raise typer.Exit(1)

    typer.echo("Jira update: ✓ success")

    # --- Optionally write display ---
    if also_write_display:
        comment_body = f"Autonomy timer logged {formatted} ({total_seconds}s) to {issue} [mode={mode}]"
        try:
            if display_target == "comment":
                client.add_comment(issue, comment_body)
                if verbose:
                    typer.echo("Comment:     ✓ added")
            elif display_target.startswith("customfield:"):
                field_id = display_target.split(":", 1)[1]
                client.update_custom_field(issue, field_id, formatted)
                if verbose:
                    typer.echo(f"Custom field {field_id}: ✓ updated")
            else:
                typer.echo(f"Warning: unknown display-target '{display_target}', skipping.", err=True)
        except Exception as exc:
            typer.echo(f"Warning: display write failed — {exc}", err=True)
