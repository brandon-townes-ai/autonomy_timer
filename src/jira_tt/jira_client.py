"""Jira Cloud REST API client."""
import requests
from requests.auth import HTTPBasicAuth


def _adf_to_text(node: dict) -> str:
    """Recursively extract plain text from an Atlassian Document Format (ADF) node."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = []
    for child in node.get("content", []):
        parts.append(_adf_to_text(child))
    return "\n".join(p for p in parts if p)


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str, verbose: bool = False):
        self._base = base_url.rstrip("/")
        self._auth = HTTPBasicAuth(email, api_token)
        self._verbose = verbose
        self._email = email
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        return f"{self._base}/rest/api/3/{path.lstrip('/')}"

    def _log(self, msg: str):
        if self._verbose:
            print(f"[jira] {msg}")

    def fetch_issue_text(self, issue_key: str) -> str:
        """Fetch Jira issue description and comments as plain text."""
        url = self._url(f"issue/{issue_key}")
        self._log(f"GET {url} (description+comments)")
        resp = self._session.get(url, params={"fields": "description,comment"})
        resp.raise_for_status()
        data = resp.json()
        fields = data.get("fields", {})

        parts: list[str] = []

        description = fields.get("description")
        if description:
            parts.append(_adf_to_text(description))

        for comment in fields.get("comment", {}).get("comments", []):
            body = comment.get("body")
            if body:
                parts.append(_adf_to_text(body))

        return "\n".join(p for p in parts if p)

    def fetch_processed_paths(self, issue_key: str) -> set:
        """Return the set of recording paths already stamped by a previous autonomy-timer run."""
        url = self._url(f"issue/{issue_key}")
        resp = self._session.get(url, params={"fields": "comment"})
        resp.raise_for_status()
        comments = resp.json().get("fields", {}).get("comment", {}).get("comments", [])
        processed: set = set()
        for comment in comments:
            body = comment.get("body")
            if not body:
                continue
            text = _adf_to_text(body)
            if "[autonomy-timer]" not in text:
                continue
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("/media/hotswap"):
                    processed.add(line)
        return processed

    def validate_issue(self, issue_key: str) -> dict:
        """Raise if the issue doesn't exist; return basic issue metadata."""
        url = self._url(f"issue/{issue_key}")
        self._log(f"GET {url}")
        self._log(f"auth email: {self._email}")
        resp = self._session.get(url, params={"fields": "summary"})
        self._log(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            self._log(f"response body: {resp.text[:500]}")
        if resp.status_code == 404:
            raise ValueError(f"Jira issue not found: {issue_key}")
        if resp.status_code == 401:
            raise ValueError(f"Jira auth failed (401) — check JIRA_EMAIL and JIRA_API_TOKEN")
        if resp.status_code == 403:
            raise ValueError(f"Jira permission denied (403) — your account may not have access to {issue_key}")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _to_jira_duration(seconds: int) -> str:
        """Convert seconds to Jira duration string (e.g. '1h 30m'). Minimum 1m."""
        total_minutes = max(1, round(seconds / 60))
        hours, minutes = divmod(total_minutes, 60)
        if hours and minutes:
            return f"{hours}h {minutes}m"
        elif hours:
            return f"{hours}h"
        else:
            return f"{minutes}m"

    def add_worklog(self, issue_key: str, seconds: int) -> None:
        """Add a worklog entry to *issue_key* for *seconds* of time spent."""
        duration = self._to_jira_duration(seconds)
        self._log(f"duration string: {duration}")
        payload = {"timeSpent": duration}
        url = self._url(f"issue/{issue_key}/worklog")
        self._log(f"POST {url} payload={payload}")
        resp = self._session.post(url, json=payload)
        self._log(f"HTTP {resp.status_code} — {resp.text[:500]}")
        resp.raise_for_status()

    def add_comment(self, issue_key: str, body: str) -> None:
        """Post a plain-text comment on *issue_key*."""
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        resp = self._session.post(self._url(f"issue/{issue_key}/comment"), json=payload)
        resp.raise_for_status()

    def update_custom_field(self, issue_key: str, field_id: str, value: str) -> None:
        """Write *value* to a custom field on *issue_key*."""
        payload = {"fields": {field_id: value}}
        resp = self._session.put(self._url(f"issue/{issue_key}"), json=payload)
        resp.raise_for_status()
