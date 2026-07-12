"""CLI: voly cloud — link this device to a VOLY Cloud org.

``voly cloud login`` is the onboarding path for the shared org history:
authenticate against the control plane, pick an org, mint a long-lived
tenant edge JWT and store it in ``.voly/cloud.json`` (git-ignored, 0600).
After that every finished local run is reported automatically
(voly/cloud_link.py hook in telemetry).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

import click

_DEFAULT_TTL_DAYS = 30


def _post(url: str, body: dict[str, Any], token: str | None = None, timeout: float = 15.0) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(url: str, token: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    detail = exc.read().decode("utf-8", errors="replace")
    try:
        return str(json.loads(detail).get("detail") or detail)
    except json.JSONDecodeError:
        return detail or str(exc.reason)


@click.group()
def cloud() -> None:
    """VOLY Cloud device link (shared org run history)."""


@cloud.command("login")
@click.option("--url", "base_url", required=True, help="Control plane URL, e.g. http://127.0.0.1:7790")
@click.option("--email", required=True, help="VOLY Cloud account email")
@click.option("--password", prompt=True, hide_input=True, help="Account password (prompted if omitted)")
@click.option("--org", "org_slug", default=None, help="Org slug (needed when you belong to several)")
@click.option("--ttl-days", default=_DEFAULT_TTL_DAYS, show_default=True, help="Device token lifetime")
def cloud_login(base_url: str, email: str, password: str, org_slug: str | None, ttl_days: int) -> None:
    """Link this device: local runs will appear in the org's shared history."""
    from voly.cloud_link import link_file_path, save_link_file

    base = base_url.strip().rstrip("/")
    try:
        auth = _post(f"{base}/cloud/v1/users/login", {"email": email, "password": password})
        user_token = auth["access_token"]
        me = _get(f"{base}/cloud/v1/users/me", user_token)
    except urllib.error.HTTPError as exc:
        click.echo(f"Login failed: {_http_error_detail(exc)}", err=True)
        raise SystemExit(1) from exc
    except (urllib.error.URLError, OSError) as exc:
        click.echo(f"Control plane unreachable at {base}: {exc}", err=True)
        raise SystemExit(1) from exc

    orgs = me.get("organizations", [])
    if not orgs:
        click.echo("This account has no organizations — create one in the dashboard first.", err=True)
        raise SystemExit(1)
    if org_slug:
        matches = [o for o in orgs if o.get("slug") == org_slug]
        if not matches:
            known = ", ".join(o.get("slug", "?") for o in orgs)
            click.echo(f"Org '{org_slug}' not found. Your orgs: {known}", err=True)
            raise SystemExit(1)
        org = matches[0]
    elif len(orgs) == 1:
        org = orgs[0]
    else:
        known = ", ".join(o.get("slug", "?") for o in orgs)
        click.echo(f"Multiple orgs — pass --org <slug>. Your orgs: {known}", err=True)
        raise SystemExit(1)

    try:
        minted = _post(
            f"{base}/cloud/v1/tenants/{org['tenant_id']}/tokens",
            {"ttl_sec": int(ttl_days) * 86400},
            token=user_token,
        )
    except urllib.error.HTTPError as exc:
        click.echo(f"Could not mint device token: {_http_error_detail(exc)}", err=True)
        raise SystemExit(1) from exc

    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + int(ttl_days) * 86400)
    )
    path = save_link_file(
        {
            "base_url": base,
            "tenant_id": org["tenant_id"],
            "tenant_slug": org.get("slug", ""),
            "token": minted["access_token"],
            "user_id": me.get("user", {}).get("id", ""),
            "user_email": email,
            "expires_at": expires_at,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    click.echo(f"Linked to org '{org.get('slug', org['tenant_id'])}' as {email}.")
    click.echo(f"Device token valid until {expires_at} — saved to {path}.")
    click.echo("Finished local runs will now appear in the org's shared history.")
    if path != link_file_path():  # pragma: no cover — defensive
        click.echo(f"note: active link file is {link_file_path()}")


@cloud.command("status")
def cloud_status() -> None:
    """Show the current device link."""
    from voly.cloud_link import link_file_path, read_link_file

    link = read_link_file()
    if not link:
        click.echo(f"Not linked ({link_file_path()} missing). Run: voly cloud login --url <control-plane> --email <you>")
        raise SystemExit(1)
    click.echo(f"Control plane: {link.get('base_url', '?')}")
    click.echo(f"Org: {link.get('tenant_slug') or link.get('tenant_id', '?')}")
    click.echo(f"User: {link.get('user_email') or link.get('user_id', '?')}")
    expires = str(link.get("expires_at") or "")
    if expires:
        expired = expires < time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        click.echo(f"Token expires: {expires}{' (EXPIRED — re-run voly cloud login)' if expired else ''}")


@cloud.command("logout")
def cloud_logout() -> None:
    """Unlink this device (delete the stored token)."""
    from voly.cloud_link import delete_link_file, link_file_path

    if delete_link_file():
        click.echo(f"Unlinked — removed {link_file_path()}.")
    else:
        click.echo("Already unlinked.")
