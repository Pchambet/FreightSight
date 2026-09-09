"""S3-compatible object storage (Scaleway Paris is the intended home), signed by hand over httpx.

No boto3: the whole need is three requests, and Signature Version 4 is a hundred lines that never
change. One dependency fewer to carry, audit and upgrade.

The bucket is never public and no URL is ever handed to a browser: the API streams the bytes, so a
document stays behind the same authentication and the same tenancy checks as its metadata.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from urllib.parse import quote
from uuid import UUID

import httpx

from app.domain.documents.ports import DocumentNotFound, DocumentStoreUnavailable

ALGORITHM = "AWS4-HMAC-SHA256"
SERVICE = "s3"


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode(), hashlib.sha256).digest()


class S3DocumentStore:
    name = "s3"

    def __init__(
        self,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        endpoint: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint.rstrip("/")
        self._client = client

    # ------------------------------------------------------------------ signing

    def _headers(self, method: str, key: str, payload: bytes, content_type: str | None) -> dict[str, str]:
        now = dt.datetime.now(dt.UTC)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        day = now.strftime("%Y%m%d")
        host = self.endpoint.split("://", 1)[-1]
        payload_hash = hashlib.sha256(payload).hexdigest()
        canonical_uri = f"/{self.bucket}/{quote(key, safe='/')}"

        headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": stamp}
        if content_type:
            headers["content-type"] = content_type
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        canonical_request = "\n".join(
            [method, canonical_uri, "", canonical_headers, signed_headers, payload_hash]
        )
        scope = f"{day}/{self.region}/{SERVICE}/aws4_request"
        to_sign = "\n".join([ALGORITHM, stamp, scope, hashlib.sha256(canonical_request.encode()).hexdigest()])
        signing_key = _sign(
            _sign(_sign(_sign(f"AWS4{self.secret_key}".encode(), day), self.region), SERVICE),
            "aws4_request",
        )
        signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
        headers["authorization"] = (
            f"{ALGORITHM} Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return headers

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(base_url=self.endpoint, timeout=30.0)

    def _url(self, key: str) -> str:
        return f"/{self.bucket}/{quote(key, safe='/')}"

    # ------------------------------------------------------------------ the port

    def put(self, org_id: UUID, key: str, content: bytes, content_type: str) -> None:
        headers = self._headers("PUT", key, content, content_type)
        try:
            response = self._http().put(self._url(key), content=content, headers=headers)
        except httpx.HTTPError as exc:
            raise DocumentStoreUnavailable(f"Object storage is unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise DocumentStoreUnavailable(f"Object storage refused the upload: {response.status_code}")

    def get(self, org_id: UUID, key: str) -> bytes:
        headers = self._headers("GET", key, b"", None)
        try:
            response = self._http().get(self._url(key), headers=headers)
        except httpx.HTTPError as exc:
            raise DocumentStoreUnavailable(f"Object storage is unreachable: {exc}") from exc
        if response.status_code == 404:
            raise DocumentNotFound(key)
        if response.status_code >= 400:
            raise DocumentStoreUnavailable(f"Object storage answered {response.status_code}")
        return response.content

    def delete(self, org_id: UUID, key: str) -> None:
        headers = self._headers("DELETE", key, b"", None)
        try:
            response = self._http().delete(self._url(key), headers=headers)
        except httpx.HTTPError as exc:
            raise DocumentStoreUnavailable(f"Object storage is unreachable: {exc}") from exc
        if response.status_code >= 400 and response.status_code != 404:
            raise DocumentStoreUnavailable(f"Object storage answered {response.status_code}")
