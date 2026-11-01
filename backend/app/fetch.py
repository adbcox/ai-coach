"""Fetching web pages, PDFs and citation records for the Library.

Safety: only http/https, and every address a host resolves to (also after each redirect) must be a public
internet address, so a pasted link cannot be used to reach the server's own network. The check happens
before connecting; it does not stop a hostile DNS server that changes its answer between the check and the
connection, which is why the Library is behind the app's login and only the signed-in owner can use it.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = 60 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = "ai-endurance-coach/0.6 (self-hosted; personal research library)"
Resolver = Callable[[str], list[str]]


class FetchError(Exception):
    """A problem with a link that is safe to show to the user."""


def system_resolver(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror as e:
        raise FetchError(f"Could not look up {host}.") from e


def check_public_url(url: str, resolve: Resolver = system_resolver) -> str:
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("Enter a full web address starting with http:// or https://.")
    host = p.hostname
    if host.lower() in ("localhost",) or host.lower().endswith((".local", ".internal", ".localhost")):
        raise FetchError("That address points at this machine or your local network, which is not allowed.")
    addrs = [host] if re.fullmatch(r"[0-9.]+|[0-9a-fA-F:]+", host) and (":" in host or host.count(".") == 3) else resolve(host)
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError as e:
            raise FetchError("Could not check that address.") from e
        if not ip.is_global or ip.is_multicast:
            raise FetchError("That address points at this machine or your local network, which is not allowed.")
    return p.geturl()


def fetch(url: str, *, transport: httpx.BaseTransport | None = None, resolve: Resolver = system_resolver,
          max_bytes: int = MAX_BYTES) -> tuple[bytes, str, str]:
    """Download a page or file. Returns (body, content_type, final_url)."""
    current = check_public_url(url, resolve)
    with httpx.Client(transport=transport, follow_redirects=False, timeout=httpx.Timeout(20.0, connect=10.0),
                      headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                with client.stream("GET", current) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        current = check_public_url(urljoin(current, r.headers["location"]), resolve)
                        continue
                    if r.status_code in (401, 402, 403):
                        raise FetchError(f"The site refused access (HTTP {r.status_code}); it may need a login or block "
                                         "automated downloads. Download the PDF yourself and upload it.")
                    if r.status_code >= 400:
                        raise FetchError(f"The site answered with an error (HTTP {r.status_code}).")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in r.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise FetchError(f"That file is larger than {max_bytes // (1024 * 1024)} MB.")
                        chunks.append(chunk)
                    return b"".join(chunks), r.headers.get("content-type", "").split(";")[0].strip().lower(), current
            except httpx.HTTPError as e:
                raise FetchError(f"Could not download that address ({type(e).__name__}).") from e
    raise FetchError("Too many redirects.")


def crossref_record(doi: str, *, transport: httpx.BaseTransport | None = None) -> dict[str, Any] | None:
    """Citation details for a DOI from Crossref (only the DOI is sent). None if unavailable."""
    try:
        with httpx.Client(transport=transport, timeout=httpx.Timeout(10.0, connect=5.0),
                          headers={"User-Agent": USER_AGENT}) as client:
            r = client.get(f"https://api.crossref.org/works/{doi}")
        if r.status_code != 200:
            return None
        m = r.json().get("message", {})
    except (httpx.HTTPError, ValueError):
        return None
    authors = []
    for a in m.get("author", []) or []:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name")
        if name:
            authors.append(name)
    year = None
    for key in ("issued", "published-print", "published-online", "created"):
        parts = (m.get(key) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = int(parts[0][0])
            break
    title = (m.get("title") or [None])[0]
    if not title:
        return None
    return {"title": re.sub(r"<[^>]+>", "", title).strip(), "authors": authors, "year": year,
            "venue": (m.get("container-title") or [None])[0], "doi": (m.get("DOI") or doi).lower(),
            "url": m.get("URL"), "type": m.get("type")}
