"""CLI: voly cloud — link this device to a VOLY Cloud org.

Default path is device-code + browser (dashboard session):
``voly cloud login --url https://cloud.voly.codes`` — no password on the laptop.

Legacy ``--email/--password`` remains for scripts/CI only.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Any

import click

_DEFAULT_TTL_DAYS = 30
_POLL_TIMEOUT_SEC = 600


def _post(url: str, body: dict[str, Any], token: str | None = None, timeout: float = 15.0) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return int(resp.status), data if isinstance(data, dict) else {}
    except urllib.error.HTTPError as exc:
        detail_raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail_raw)
            detail = parsed.get("detail", detail_raw) if isinstance(parsed, dict) else detail_raw
        except json.JSONDecodeError:
            detail = detail_raw or str(exc.reason)
        return int(exc.code), {"detail": detail}


def _get(url: str, token: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_error_detail(payload: dict) -> str:
    detail = payload.get("detail", payload)
    if isinstance(detail, dict):
        return str(detail.get("error") or detail)
    return str(detail)


def _default_device_name() -> str:
    try:
        return socket.gethostname()[:100] or "local-agent"
    except OSError:
        return "local-agent"


def _save_link_from_poll(base: str, payload: dict) -> str:
    from voly.cloud_link import save_link_file

    token_obj = payload.get("device_token") or {}
    device = payload.get("device") or {}
    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + _DEFAULT_TTL_DAYS * 86400)
    )
    path = save_link_file(
        {
            "base_url": base,
            "tenant_id": payload.get("tenant_id") or device.get("tenant_id") or "",
            "tenant_slug": payload.get("tenant_slug") or "",
            "token": token_obj.get("access_token") or "",
            "device_id": device.get("id") or "",
            "user_id": payload.get("user_id") or device.get("user_id") or "",
            "user_email": payload.get("user_email") or "",
            "expires_at": expires_at,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    return str(path)


@click.group()
def cloud() -> None:
    """VOLY Cloud device link (shared org run history)."""


@cloud.command("login")
@click.option("--url", "base_url", required=True, help="Control plane URL, e.g. https://cloud.voly.codes")
@click.option("--email", default=None, help="[legacy] Account email — prefer browser device-code flow")
@click.option("--password", default=None, help="[legacy] Account password (prompted if --email set)")
@click.option("--org", "org_slug", default=None, help="[legacy] Org slug when using --email")
@click.option("--ttl-days", default=_DEFAULT_TTL_DAYS, show_default=True, help="[legacy] Token lifetime")
@click.option("--no-browser", is_flag=True, help="Do not open the browser; print the URL only")
@click.option("--device-name", default=None, help="Label for this machine (default: hostname)")
def cloud_login(
    base_url: str,
    email: str | None,
    password: str | None,
    org_slug: str | None,
    ttl_days: int,
    no_browser: bool,
    device_name: str | None,
) -> None:
    """Link this device: local runs will appear in the org's shared history."""
    base = base_url.strip().rstrip("/")
    if email:
        _legacy_password_login(base, email, password, org_slug, ttl_days)
        return
    _device_code_login(base, no_browser=no_browser, device_name=device_name or _default_device_name())


def _device_code_login(base: str, *, no_browser: bool, device_name: str) -> None:
    try:
        status, start = _post(f"{base}/cloud/v1/device-auth/start", {})
    except (urllib.error.URLError, OSError) as exc:
        click.echo(f"Control plane unreachable at {base}: {exc}", err=True)
        raise SystemExit(1) from exc
    if status != 200:
        click.echo(f"Could not start device link: {_http_error_detail(start)}", err=True)
        raise SystemExit(1)

    user_code = start.get("user_code", "")
    device_code = start.get("device_code", "")
    verify = start.get("verification_uri_complete") or start.get("verification_uri") or ""
    interval = max(2, int(start.get("interval") or 5))

    click.echo("Link this device in the browser (dashboard session — no password here).")
    click.echo(f"  Code:  {user_code}")
    click.echo(f"  Open:  {verify}")
    if not no_browser and verify:
        try:
            webbrowser.open(verify)
        except Exception:  # pragma: no cover
            pass

    deadline = time.time() + _POLL_TIMEOUT_SEC
    while time.time() < deadline:
        time.sleep(interval)
        try:
            status, body = _post(
                f"{base}/cloud/v1/device-auth/poll",
                {"device_code": device_code},
            )
        except (urllib.error.URLError, OSError) as exc:
            click.echo(f"Poll failed: {exc}", err=True)
            continue
        detail = body.get("detail")
        if status == 200 and body.get("device_token"):
            # Optional: tell approve the preferred name was already set in browser;
            # device_name from CLI is informational if approve already happened.
            _ = device_name
            path = _save_link_from_poll(base, body)
            slug = body.get("tenant_slug") or body.get("tenant_id")
            email = body.get("user_email") or ""
            click.echo(f"Linked to org '{slug}'{f' as {email}' if email else ''}.")
            click.echo(f"Device token saved to {path}.")
            click.echo("Finished local runs will now appear in the org's shared history.")
            click.echo("Tip: `voly cloud sync` uploads past local runs; heartbeats run with `voly ui`.")
            return
        if detail == "authorization_pending":
            click.echo(".", nl=False)
            continue
        if detail in {"expired_token", "access_denied"}:
            click.echo("")
            click.echo(f"Link failed: {detail}", err=True)
            raise SystemExit(1)
        click.echo("")
        click.echo(f"Unexpected poll response ({status}): {detail or body}", err=True)
        raise SystemExit(1)

    click.echo("")
    click.echo("Timed out waiting for browser confirmation.", err=True)
    raise SystemExit(1)


def _legacy_password_login(
    base: str,
    email: str,
    password: str | None,
    org_slug: str | None,
    ttl_days: int,
) -> None:
    """Deprecated password path — prefer device-code. Still links via /devices."""
    from voly.cloud_link import save_link_file

    if not password:
        password = click.prompt("Password", hide_input=True)
    click.echo("Warning: --email/--password is legacy; prefer `voly cloud login --url ...` (browser).", err=True)
    try:
        status, auth = _post(f"{base}/cloud/v1/users/login", {"email": email, "password": password})
    except (urllib.error.URLError, OSError) as exc:
        click.echo(f"Control plane unreachable at {base}: {exc}", err=True)
        raise SystemExit(1) from exc
    if status != 200:
        click.echo(f"Login failed: {_http_error_detail(auth)}", err=True)
        raise SystemExit(1)
    user_token = auth.get("access_token") or ""
    try:
        me = _get(f"{base}/cloud/v1/users/me", user_token)
    except (urllib.error.URLError, OSError, urllib.error.HTTPError) as exc:
        click.echo(f"Login failed: {exc}", err=True)
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

    status, minted = _post(
        f"{base}/cloud/v1/tenants/{org['tenant_id']}/devices",
        {"name": _default_device_name(), "version": ""},
        token=user_token,
    )
    if status not in {200, 201}:
        click.echo(f"Could not mint device token: {_http_error_detail(minted)}", err=True)
        raise SystemExit(1)

    device = minted.get("device") or {}
    token_obj = minted.get("device_token") or {}
    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + int(ttl_days) * 86400)
    )
    path = save_link_file(
        {
            "base_url": base,
            "tenant_id": org["tenant_id"],
            "tenant_slug": org.get("slug", ""),
            "token": token_obj.get("access_token") or "",
            "device_id": device.get("id") or "",
            "user_id": me.get("user", {}).get("id", ""),
            "user_email": email,
            "expires_at": expires_at,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    click.echo(f"Linked to org '{org.get('slug', org['tenant_id'])}' as {email}.")
    click.echo(f"Device token valid until {expires_at} — saved to {path}.")


@cloud.command("status")
def cloud_status() -> None:
    """Show the current device link."""
    from voly.cloud_link import link_file_path, read_link_file

    link = read_link_file()
    if not link:
        click.echo(
            f"Not linked ({link_file_path()} missing). Run: voly cloud login --url <control-plane>"
        )
        raise SystemExit(1)
    click.echo(f"Control plane: {link.get('base_url', '?')}")
    click.echo(f"Org: {link.get('tenant_slug') or link.get('tenant_id', '?')}")
    click.echo(f"User: {link.get('user_email') or link.get('user_id', '?')}")
    click.echo(f"Device: {link.get('device_id') or '(missing — re-run voly cloud login)'}")
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


@cloud.command("heartbeat")
@click.option("--once", is_flag=True, help="Send one heartbeat and exit")
@click.option("--interval", default=30, show_default=True, help="Seconds between heartbeats")
def cloud_heartbeat(once: bool, interval: int) -> None:
    """Keep this device marked online in the org dashboard."""
    from voly.cloud_link import send_heartbeat

    if once:
        ok = send_heartbeat()
        click.echo("ok" if ok else "failed")
        raise SystemExit(0 if ok else 1)
    click.echo(f"Heartbeating every {interval}s (Ctrl+C to stop)…")
    while True:
        send_heartbeat()
        time.sleep(max(5, interval))


@cloud.command("sync")
@click.option("--since", "since_days", default=30, show_default=True, help="Only events newer than N days")
@click.option("--limit", default=200, show_default=True, help="Max events to upload")
@click.option("--dry-run", is_flag=True, help="List what would be uploaded without POSTing")
def cloud_sync(since_days: int, limit: int, dry_run: bool) -> None:
    """Upload past local runs from .voly/events to the linked org history."""
    from voly.cloud_link import resolve_cloud_link, sync_local_events
    from voly.config import load_config

    config = load_config()
    if resolve_cloud_link(config) is None:
        click.echo("Not linked. Run: voly cloud login --url <control-plane>", err=True)
        raise SystemExit(1)
    result = sync_local_events(config, since_days=since_days, limit=limit, dry_run=dry_run)
    click.echo(
        f"{'Would sync' if dry_run else 'Synced'}: {result['synced']}  "
        f"skipped={result['skipped']}  failed={result['failed']}"
    )
    if result["failed"]:
        raise SystemExit(1)
