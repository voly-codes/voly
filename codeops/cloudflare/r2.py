"""
R2Client — Cloudflare R2 object storage via S3-compatible API + AWS SigV4.

Uses only stdlib (no boto3/s3transfer). Credentials from env:
    CF_R2_ACCESS_KEY_ID
    CF_R2_SECRET_ACCESS_KEY
    CF_R2_ENDPOINT   (e.g. https://<account_id>.r2.cloudflarestorage.com)

Usage:
    r2 = R2Client.from_env()
    r2.put("codeops-telemetry", "events/abc.json", b"...", "application/json")
    data = r2.get("codeops-skills", "index.json")
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

_log = logging.getLogger("codeops.cloudflare.r2")


def _sign_key(secret: str, date: str, region: str, service: str) -> bytes:
    """Derive the AWS SigV4 signing key."""
    def _mac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    return _mac(
        _mac(_mac(_mac(f"AWS4{secret}".encode(), date), region), service),
        "aws4_request",
    )


def _sigv4_headers(
    method: str,
    url: str,
    host: str,
    body: bytes,
    access_key: str,
    secret_key: str,
    content_type: str = "application/octet-stream",
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return Authorization + required headers for an S3/R2 request."""
    now = datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    region = "auto"
    service = "s3"

    # Strip scheme from URL to get the path
    path = url.split(host, 1)[-1] or "/"

    body_hash = hashlib.sha256(body).hexdigest()

    # Build canonical headers (must be sorted; each ends with \n)
    header_map: dict[str, str] = {
        "content-type": content_type,
        "host": host,
        "x-amz-content-sha256": body_hash,
        "x-amz-date": amz_date,
    }
    if extra_headers:
        header_map.update({k.lower(): v for k, v in extra_headers.items()})

    sorted_keys = sorted(header_map)
    canonical_headers = "".join(f"{k}:{header_map[k]}\n" for k in sorted_keys)
    signed_headers = ";".join(sorted_keys)

    canonical_request = "\n".join([
        method,
        path,
        "",  # empty query string
        canonical_headers,
        signed_headers,
        body_hash,
    ])

    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256",
        amz_date,
        credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    sig_key = _sign_key(secret_key, date_stamp, region, service)
    signature = hmac.new(sig_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    auth = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": auth,
        "Content-Type": content_type,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": body_hash,
    }


class R2Error(Exception):
    pass


class R2Client:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        timeout: float = 10.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.timeout = timeout
        self._host = self.endpoint.removeprefix("https://").removeprefix("http://")

    @classmethod
    def from_env(cls, timeout: float = 10.0) -> "R2Client | None":
        endpoint = os.environ.get("CF_R2_ENDPOINT", "")
        key_id = os.environ.get("CF_R2_ACCESS_KEY_ID", "")
        secret = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "")
        if not (endpoint and key_id and secret):
            return None
        return cls(endpoint, key_id, secret, timeout=timeout)

    def _url(self, bucket: str, key: str) -> str:
        return f"{self.endpoint}/{bucket}/{key}"

    def put(
        self,
        bucket: str,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload bytes to R2. Raises R2Error on failure."""
        url = self._url(bucket, key)
        hdrs = _sigv4_headers("PUT", url, self._host, body, self.access_key, self.secret_key, content_type)
        req = urllib.request.Request(url, data=body, headers=hdrs, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise R2Error(f"R2 PUT {bucket}/{key}: HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise R2Error(f"R2 PUT {bucket}/{key}: {e.reason}") from e

    def put_json(self, bucket: str, key: str, obj: Any) -> None:
        self.put(bucket, key, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def get(self, bucket: str, key: str) -> bytes:
        """Download bytes from R2. Raises R2Error on failure."""
        url = self._url(bucket, key)
        hdrs = _sigv4_headers("GET", url, self._host, b"", self.access_key, self.secret_key)
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise R2Error(f"R2 GET {bucket}/{key}: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise R2Error(f"R2 GET {bucket}/{key}: {e.reason}") from e

    def get_json(self, bucket: str, key: str) -> Any:
        return json.loads(self.get(bucket, key))

    def delete(self, bucket: str, key: str) -> None:
        url = self._url(bucket, key)
        hdrs = _sigv4_headers("DELETE", url, self._host, b"", self.access_key, self.secret_key)
        req = urllib.request.Request(url, headers=hdrs, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            raise R2Error(f"R2 DELETE {bucket}/{key}: HTTP {e.code}") from e

    def exists(self, bucket: str, key: str) -> bool:
        url = self._url(bucket, key)
        hdrs = _sigv4_headers("HEAD", url, self._host, b"", self.access_key, self.secret_key)
        req = urllib.request.Request(url, headers=hdrs, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
            return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            raise R2Error(f"R2 HEAD {bucket}/{key}: HTTP {e.code}") from e
        except urllib.error.URLError:
            return False
