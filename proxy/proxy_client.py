#!/usr/bin/env python3
"""
HTTP client with integrated proxy management following proxydesign.md

Provides a drop-in replacement for requests.post() with automatic proxy rotation,
retry logic, and error handling according to the design specification.

KEY CHANGE: Proxy hostnames are resolved once at startup and cached as IPs.
This eliminates runtime DNS lookups and prevents curl: (6) Could not resolve proxy errors
under high concurrency (confirmed root cause on OVH vs AWS infrastructure).
"""

import asyncio
import json
import os
import random
import socket
import time
from typing import Dict, List, Optional, Any, Union
import uuid

from curl_cffi import requests as curl_requests
from curl_cffi.requests import AsyncSession

from .proxy_manager import (
    ProxyManager,
    ProxyConfig,
    get_global_manager,
)

from loguru import logger


# ---------------------------------------------------------------------------
# TTL-based DNS cache
# ---------------------------------------------------------------------------
# Resolves proxy hostnames and caches the result for DNS_CACHE_TTL seconds.
# After TTL expires the next request re-resolves, picking up any IP rotation
# done by the proxy provider (BrightData / Oxylabs use rotating DNS).
#
# Why TTL instead of permanent cache:
#   - Permanent cache: eliminates DNS load but silently breaks when provider
#     rotates IPs (connection errors with no curl (6) to warn you).
#   - TTL cache: still eliminates per-request DNS load, but re-resolves
#     periodically so IP changes are picked up automatically.
#
# TTL default: 300s (5 minutes). Tune via DNS_CACHE_TTL env var.
# Most proxy providers rotate IPs on the order of minutes, not seconds.
# ---------------------------------------------------------------------------
DNS_CACHE_TTL = int(os.getenv("DNS_CACHE_TTL", "300"))  # seconds

_DNS_CACHE: Dict[str, tuple] = {}  # hostname -> (ip, resolved_at_timestamp)
_DNS_CACHE_LOCK = None  # initialized lazily (needs running event loop)


def _get_cache_lock() -> asyncio.Lock:
    """Lazily initialize the cache lock (requires a running event loop)."""
    global _DNS_CACHE_LOCK
    if _DNS_CACHE_LOCK is None:
        _DNS_CACHE_LOCK = asyncio.Lock()
    return _DNS_CACHE_LOCK


def _resolve_host(hostname: str) -> str:
    """
    Resolve a hostname to an IP address, with TTL-based cache.

    - Returns cached IP if within TTL window.
    - Re-resolves and updates cache when TTL has expired.
    - Falls back to original hostname if resolution fails (safe degradation).

    This is intentionally synchronous (socket.gethostbyname) because it is
    called from the hot request path. Resolution only happens on cache miss
    or TTL expiry, so the blocking call is infrequent.
    """
    now = time.time()
    cached = _DNS_CACHE.get(hostname)

    if cached:
        ip, resolved_at = cached
        age = now - resolved_at
        if age < DNS_CACHE_TTL:
            logger.debug(
                f"[DNS CACHE] HIT {hostname} -> {ip} (age={age:.0f}s, ttl={DNS_CACHE_TTL}s)"
            )
            return ip
        else:
            logger.info(
                f"[DNS CACHE] EXPIRED {hostname} -> {ip} (age={age:.0f}s), re-resolving"
            )

    try:
        ip = socket.gethostbyname(hostname)
        _DNS_CACHE[hostname] = (ip, now)
        logger.info(f"[DNS CACHE] RESOLVED {hostname} -> {ip}")
        return ip
    except socket.gaierror as e:
        if cached:
            # Serve stale IP rather than failing — provider may be temporarily
            # unreachable but the old IP could still work
            stale_ip, _ = cached
            logger.warning(
                f"[DNS CACHE] Re-resolve failed for {hostname}: {e}. "
                f"Serving stale IP {stale_ip} until next TTL window."
            )
            return stale_ip
        logger.warning(
            f"[DNS CACHE] Failed to resolve {hostname}: {e}. Using hostname directly."
        )
        return hostname


def evict_dns_cache(hostname: str) -> None:
    """
    Immediately evict a hostname from the DNS cache.

    Call this when a connection error suggests the cached IP may be stale,
    so the very next request forces a fresh DNS resolution.
    """
    if hostname in _DNS_CACHE:
        old_ip, _ = _DNS_CACHE.pop(hostname)
        logger.info(f"[DNS CACHE] EVICTED {hostname} (was {old_ip})")


def _build_proxy_url_with_ip(proxy_url: str) -> str:
    """
    Replace the hostname in a proxy URL with its pre-resolved IP address.

    Example:
        http://user:pass@isp.oxylabs.io:8059  ->  http://user:pass@149.88.x.x:8059

    This eliminates per-request DNS lookups entirely.
    """
    try:
        # Parse scheme
        scheme_end = proxy_url.index("://")
        scheme = proxy_url[:scheme_end]
        rest = proxy_url[scheme_end + 3 :]

        # Split auth from host:port
        if "@" in rest:
            auth, hostport = rest.rsplit("@", 1)
        else:
            auth = None
            hostport = rest

        # Split host from port
        if ":" in hostport:
            host, port = hostport.rsplit(":", 1)
        else:
            host = hostport
            port = None

        # Resolve host to IP
        ip = _resolve_host(host)

        # Reconstruct URL
        if auth:
            new_url = f"{scheme}://{auth}@{ip}"
        else:
            new_url = f"{scheme}://{ip}"

        if port:
            new_url += f":{port}"

        return new_url

    except Exception as e:
        logger.warning(
            f"[DNS CACHE] Could not parse proxy URL for IP substitution: {e}. Using original URL."
        )
        return proxy_url


class ProxyHTTPError(Exception):
    """Custom exception for proxy-related HTTP errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        proxy_id: Optional[str] = None,
        attempt: int = 0,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.proxy_id = proxy_id
        self.attempt = attempt


class ProxyClient:
    """
    HTTP client with automatic proxy management.

    Implements the worker behavior from proxydesign.md:
    - Reserves proxies before requests
    - Handles timeouts and rate limits
    - Automatic retries with different proxies
    - Marks success/cooldown appropriately
    - Dynamic impersonation with session pooling (OPTIMIZED)
    - DNS pre-resolution to eliminate curl (6) errors (OVH fix)
    """

    def __init__(
        self,
        config: Optional[ProxyConfig] = None,
        proxy_manager: Optional[ProxyManager] = None,
        keys=None,
    ):
        self.config = config or ProxyConfig()
        self.manager = proxy_manager or get_global_manager()

        # OPTIMIZATION: Session pooling to avoid repeated TCP/TLS handshakes
        self._session_pools: Dict[str, List[AsyncSession]] = {}
        self._pool_locks: Dict[str, asyncio.Lock] = {}
        self._max_sessions_per_impersonate = int(os.getenv("LISTING_SEMAPHORE", "150"))
        self._session_counter = 0

    def _get_retry_after_delay(self, response: curl_requests.Response) -> int:
        """Extract Retry-After header value if present."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                if retry_after.isdigit():
                    return int(retry_after)
                else:
                    return int(self.config.proxy_cooldown_on_429)
            except ValueError:
                pass
        return 0

    async def _get_session(
        self, impersonate: str, curl_options: Optional[dict] = None
    ) -> AsyncSession:
        """
        Get or create a session from the pool (OPTIMIZED).

        curl_options is intentionally NOT pooled — sessions with CURLOPT_RESOLVE
        are bound to a specific proxy IP. Pooling them across different proxies
        would cause the wrong resolve hint to be used. So:
          - Sessions with curl_options: always created fresh, never pooled.
          - Sessions without curl_options: normal pool behaviour.
        """
        if curl_options:
            # Never pool sessions that carry proxy-specific resolve hints
            logger.debug(
                f"[SESSION CREATED] New session with RESOLVE hint for {impersonate}"
            )
            self._session_counter += 1
            return AsyncSession(
                impersonate=impersonate,
                timeout=self.config.timeout,
                curl_options=curl_options,
            )

        if impersonate not in self._session_pools:
            self._session_pools[impersonate] = []
            self._pool_locks[impersonate] = asyncio.Lock()

        async with self._pool_locks[impersonate]:
            if self._session_pools[impersonate]:
                session = self._session_pools[impersonate].pop()
                logger.debug(
                    f"Reusing session for {impersonate}, pool size: {len(self._session_pools[impersonate])}"
                )
                return session

        logger.debug(
            f"[SESSION CREATED] New session for {impersonate}, total={self._session_counter}"
        )
        self._session_counter += 1
        return AsyncSession(
            impersonate=impersonate,
            timeout=self.config.timeout,
        )

    async def _return_session(
        self, session: AsyncSession, impersonate: str, has_curl_options: bool = False
    ):
        """Return a session to the pool for reuse (OPTIMIZED).

        Sessions created with curl_options (proxy-specific RESOLVE hints) are
        always closed rather than pooled, since their hints are not reusable
        across different proxies.
        """
        if has_curl_options:
            await session.close()
            logger.debug(f"[SESSION CLOSED] Closed RESOLVE-hint session (not poolable)")
            return

        if impersonate not in self._session_pools:
            self._session_pools[impersonate] = []
            self._pool_locks[impersonate] = asyncio.Lock()

        async with self._pool_locks[impersonate]:
            if (
                len(self._session_pools[impersonate])
                < self._max_sessions_per_impersonate
            ):
                self._session_pools[impersonate].append(session)
                logger.debug(
                    f"Returned session to pool, size: {len(self._session_pools[impersonate])}"
                )
            else:
                await session.close()
                logger.debug(f"Session pool full, closing session")

    async def close_all_sessions(self):
        """Close all pooled sessions. Call this when shutting down the client."""
        for impersonate, sessions in self._session_pools.items():
            for session in sessions:
                try:
                    await session.close()
                except Exception as e:
                    logger.warning(f"Error closing session for {impersonate}: {e}")
        self._session_pools.clear()
        logger.info(f"Closed all sessions, total created: {self._session_counter}")

    def _get_proxies_dict(self, proxy) -> Dict[str, str]:
        """
        Build the proxies dict for a request, using pre-resolved IPs.

        Instead of:  http://user:pass@isp.oxylabs.io:8059
        Returns:     http://user:pass@149.88.x.x:8059

        This is the core fix for curl (6) Could not resolve proxy errors.
        """
        resolved_url = _build_proxy_url_with_ip(proxy.url)
        return {
            "http": resolved_url,
            "https": resolved_url,
        }

    def _get_curl_resolve_options(self, proxy) -> dict:
        """
        Build curl_options with CURLOPT_RESOLVE to bypass libcurl's internal
        DNS resolution for the proxy host entirely.

        Even when an IP is passed in the proxy URL, some libcurl versions still
        attempt DNS resolution internally. CURLOPT_RESOLVE short-circuits this
        by telling libcurl exactly which IP to use for hostname:port, making
        DNS completely irrelevant for proxy connections.

        Format: ["hostname:port:ip"]
        Example: ["isp.oxylabs.io:8059:149.88.107.136"]
        """
        try:
            from curl_cffi import CurlOpt

            if not hasattr(CurlOpt, "RESOLVE"):
                return {}

            ip = _resolve_host(proxy.host)
            if ip == proxy.host:
                # Resolution failed or returned hostname, skip
                return {}

            resolve_entry = f"{proxy.host}:{proxy.port}:{ip}"
            logger.debug(f"[CURL RESOLVE] {resolve_entry}")
            return {CurlOpt.RESOLVE: [resolve_entry]}

        except Exception as e:
            logger.debug(f"[CURL RESOLVE] Could not build resolve options: {e}")
            return {}

    async def post(
        self,
        url: str,
        data: Optional[Union[Dict, str, bytes]] = None,
        json_data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        impersonate: Optional[str] = None,
        **kwargs,
    ):
        """
        Perform POST request with automatic proxy management.

        Args:
            url: Target URL
            data: Request body data
            json_data: JSON request body (sets Content-Type to application/json)
            headers: Additional headers
            **kwargs: Additional requests.post parameters

        Returns:
            Response object

        Raises:
            ProxyHTTPError: If all attempts fail
        """
        logger.info(f"Starting proxy POST request to {url}")
        owner_id = f"client-{uuid.uuid4().hex[:8]}"
        last_exception = None

        for attempt in range(self.config.max_attempts_per_request):
            proxy = None
            session = None
            impersonate_type = impersonate or self.config.browser_impersonation

            try:
                # Reserve a proxy with retry logic (3 attempts)
                for proxy_attempt in range(3):
                    proxy = self.manager.reserve_proxy(owner_id)
                    if proxy:
                        break

                    wait_time = (2**proxy_attempt) * 0.5
                    logger.warning(
                        f"No proxy available for {owner_id}, waiting {wait_time:.1f}s (proxy attempt {proxy_attempt + 1}/3)"
                    )
                    await asyncio.sleep(wait_time)

                if not proxy:
                    status = self.manager.get_status()
                    logger.error(
                        f"Proxy exhaustion: {status['available_proxies']}/{status['total_proxies']} available, "
                        f"{status['active_cooldowns']} in cooldown, {status['active_reservations']} reserved"
                    )
                    if attempt < self.config.max_attempts_per_request - 1:
                        delay = min(5 + (2**attempt), 15) + random.uniform(0, 2)
                        logger.warning(
                            f"Waiting {delay:.1f}s before retry attempt {attempt + 2}"
                        )
                        await asyncio.sleep(delay)
                    continue

                logger.debug(
                    f"Using proxy {proxy.id} for attempt {attempt + 1}: {proxy.host}:{proxy.port}"
                )

                # Build proxies dict using pre-resolved IP (eliminates DNS lookups)
                proxies = self._get_proxies_dict(proxy)

                # CURLOPT_RESOLVE is the nuclear option: tells libcurl the exact
                # IP for this proxy host:port so it never touches DNS at all.
                curl_opts = self._get_curl_resolve_options(proxy)

                # Sessions with RESOLVE hints are never pooled (proxy-specific)
                session = await self._get_session(
                    impersonate_type, curl_options=curl_opts
                )

                if headers:
                    session.headers.update(headers)
                    logger.debug(
                        f"Merged custom headers with {impersonate_type} impersonation"
                    )

                request_kwargs = {
                    "proxies": proxies,
                    "timeout": self.config.timeout,
                    **kwargs,
                }

                if json_data:
                    request_kwargs["json"] = json_data
                elif data is not None:
                    request_kwargs["data"] = data

                response = await session.post(url, **request_kwargs)
                logger.info(f"[REQUEST>>DATA]>> {url} >> {request_kwargs}")

                if 200 <= response.status_code < 300:
                    logger.info(
                        f"Request successful via proxy {proxy.id}, status {response.status_code}"
                    )
                    self.manager.mark_success(proxy.id)
                    return response

                elif response.status_code == 429:
                    retry_delay = self._get_retry_after_delay(response)
                    cooldown_seconds = retry_delay or self.config.proxy_cooldown_on_429
                    logger.warning(
                        f"Rate limited via proxy {proxy.id}, cooldown {cooldown_seconds}s"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, cooldown_seconds, f"429_rate_limit"
                    )
                    continue

                elif response.status_code == 403:
                    logger.warning(
                        f"Forbidden error {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, self.config.cooldown_on_403, f"403_forbidden"
                    )
                    continue

                elif 400 <= response.status_code < 500:
                    logger.warning(
                        f"Client error {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.release_proxy(proxy.id)
                    return response

                elif 500 <= response.status_code < 600:
                    logger.warning(
                        f"Server error {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, self.config.cooldown_on_5xx, f"5xx_server_error"
                    )
                    continue

                else:
                    logger.warning(
                        f"Unexpected status {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, self.config.default_cooldown, f"unexpected_status"
                    )
                    continue

            except asyncio.TimeoutError as e:
                logger.warning(
                    f"Timeout via proxy {proxy.id if proxy else 'unknown'}: {e}"
                )
                if proxy:
                    self.manager.mark_cooldown(
                        proxy.id, self.config.proxy_cooldown_on_timeout, "timeout"
                    )
                last_exception = ProxyHTTPError(
                    f"Request timeout: {e}",
                    proxy_id=proxy.id if proxy else None,
                    attempt=attempt,
                )

            except Exception as e:
                error_str = str(e).lower()

                is_dns_or_tls_error = any(
                    [
                        "could not resolve proxy" in error_str,
                        "could not resolve host" in error_str,
                        "name resolution failed" in error_str,
                        "error setting certificate verify locations" in error_str,
                    ]
                )

                is_connection_error = any(
                    [
                        "proxy connect aborted" in error_str,
                        "failed to connect" in error_str,
                        "empty reply from server" in error_str,
                        "connection refused" in error_str,
                        "connection reset" in error_str,
                        "could not connect" in error_str,
                        "ssl" in error_str and "error" in error_str,
                        "certificate" in error_str and "error" in error_str,
                    ]
                )

                if is_dns_or_tls_error:
                    logger.error(
                        f"[SESSION_ERROR>>SESSION RESET] DNS/TLS error via proxy {proxy.id if proxy else 'unknown'} "
                        f"on attempt {attempt + 1}: {e}"
                    )

                    # Evict cached IP so next attempt re-resolves fresh
                    if proxy:
                        evict_dns_cache(proxy.host)

                    if session:
                        try:
                            logger.warning(
                                f"[SESSION_ERROR>>SESSION CLOSED] Closing broken session due to DNS/TLS error "
                                f"(proxy={proxy.id if proxy else 'unknown'})"
                            )
                            await session.close()
                        except Exception as close_err:
                            logger.warning(
                                f"[SESSION_ERROR>>SESSION CLOSE FAILED] {close_err}"
                            )
                        session = None

                    if proxy:
                        self.manager.mark_cooldown(
                            proxy.id,
                            self.config.proxy_cooldown_on_connection_error,
                            "dns_or_tls_resolution_error",
                        )

                    logger.info(
                        f"[SESSION_ERROR>>SESSION RETRY] A fresh session will be created on next retry (attempt {attempt + 2})"
                    )

                    last_exception = ProxyHTTPError(
                        f"DNS/TLS resolution error: {e}",
                        proxy_id=proxy.id if proxy else None,
                        attempt=attempt,
                    )

                elif is_connection_error:
                    logger.error(
                        f"[SESSION_ERROR>>CONNECTION ERROR] Proxy {proxy.id if proxy else 'unknown'} "
                        f"failed on attempt {attempt + 1}: {e}"
                    )
                    if proxy:
                        self.manager.mark_cooldown(
                            proxy.id,
                            self.config.proxy_cooldown_on_connection_error,
                            f"connection_error: {type(e).__name__}",
                        )
                    last_exception = ProxyHTTPError(
                        f"Connection error: {e}",
                        proxy_id=proxy.id if proxy else None,
                        attempt=attempt,
                    )

                else:
                    logger.error(
                        f"[SESSION_ERROR>>UNEXPECTED ERROR] Proxy {proxy.id if proxy else 'unknown'}: {e}"
                    )
                    if proxy:
                        self.manager.release_proxy(proxy.id)
                    last_exception = ProxyHTTPError(
                        f"Unexpected error: {e}", attempt=attempt
                    )

            finally:
                if session:
                    logger.debug(
                        f"[SESSION_ERROR>>SESSION RETURN] Returning session to pool "
                        f"(proxy={proxy.id if proxy else 'unknown'})"
                    )
                    await self._return_session(
                        session, impersonate_type, has_curl_options=bool(curl_opts)
                    )
                else:
                    logger.debug(
                        f"[SESSION_ERROR>>SESSION DISCARDED] Broken session was closed and will not be reused"
                    )

        error_msg = f"All {self.config.max_attempts_per_request} attempts failed"
        if last_exception:
            error_msg += f". Last error: {last_exception}"

        logger.error(error_msg)
        raise ProxyHTTPError(error_msg, attempt=attempt)

    async def get(
        self,
        url: str,
        headers: Optional[Dict] = None,
        impersonate: Optional[str] = None,
        **kwargs,
    ):
        """
        Perform GET request with automatic proxy management.

        Args:
            url: Target URL
            headers: Additional headers
            **kwargs: Additional requests.get parameters

        Returns:
            Response object
        """
        logger.info(f"Starting proxy GET request to {url}")
        owner_id = f"client-{uuid.uuid4().hex[:8]}"
        last_exception = None

        for attempt in range(self.config.max_attempts_per_request):
            proxy = None
            session = None
            impersonate_type = impersonate or self.config.browser_impersonation

            try:
                proxy = self.manager.reserve_proxy(owner_id)
                if not proxy:
                    logger.warning(
                        f"No proxy available for {owner_id}, attempt {attempt + 1}"
                    )
                    if attempt < self.config.max_attempts_per_request - 1:
                        delay = min(2**attempt, 10) + random.uniform(0, 1)
                        await asyncio.sleep(delay)
                    continue

                logger.debug(
                    f"Using proxy {proxy.id} for attempt {attempt + 1}: {proxy.host}:{proxy.port}"
                )

                # Build proxies dict using pre-resolved IP (eliminates DNS lookups)
                proxies = self._get_proxies_dict(proxy)

                # CURLOPT_RESOLVE bypasses libcurl DNS for the proxy host
                curl_opts = self._get_curl_resolve_options(proxy)

                session = await self._get_session(
                    impersonate_type, curl_options=curl_opts
                )

                if headers:
                    session.headers.update(headers)
                    logger.debug(
                        f"Merged custom headers with {impersonate_type} impersonation"
                    )

                request_kwargs = {
                    "proxies": proxies,
                    "timeout": self.config.timeout,
                    **kwargs,
                }

                response = await session.get(url, **request_kwargs)

                if 200 <= response.status_code < 300:
                    logger.info(
                        f"GET request successful via proxy {proxy.id}, status {response.status_code}"
                    )
                    self.manager.mark_success(proxy.id)
                    return response

                elif response.status_code == 429:
                    retry_delay = self._get_retry_after_delay(response)
                    cooldown_seconds = retry_delay or self.config.proxy_cooldown_on_429
                    logger.warning(
                        f"Rate limited via proxy {proxy.id}, cooldown {cooldown_seconds}s"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, cooldown_seconds, f"429_rate_limit"
                    )
                    continue

                elif response.status_code == 403:
                    logger.warning(
                        f"Forbidden error {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, self.config.cooldown_on_403, f"403_forbidden"
                    )
                    continue

                elif 400 <= response.status_code < 500:
                    logger.warning(
                        f"Client error {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.release_proxy(proxy.id)
                    return response

                elif 500 <= response.status_code < 600:
                    logger.warning(
                        f"Server error {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, self.config.cooldown_on_5xx, f"5xx_server_error"
                    )
                    continue

                else:
                    logger.warning(
                        f"Unexpected status {response.status_code} via proxy {proxy.id}"
                    )
                    self.manager.mark_cooldown(
                        proxy.id, self.config.default_cooldown, f"unexpected_status"
                    )
                    continue

            except asyncio.TimeoutError as e:
                logger.warning(
                    f"Timeout via proxy {proxy.id if proxy else 'unknown'}: {e}"
                )
                if proxy:
                    self.manager.mark_cooldown(
                        proxy.id, self.config.proxy_cooldown_on_timeout, "timeout"
                    )
                last_exception = ProxyHTTPError(
                    f"GET timeout: {e}",
                    proxy_id=proxy.id if proxy else None,
                    attempt=attempt,
                )

            except Exception as e:
                error_str = str(e).lower()

                is_dns_or_tls_error = any(
                    [
                        "could not resolve proxy" in error_str,
                        "could not resolve host" in error_str,
                        "name resolution failed" in error_str,
                        "error setting certificate verify locations" in error_str,
                    ]
                )

                is_connection_error = any(
                    [
                        "proxy connect aborted" in error_str,
                        "failed to connect" in error_str,
                        "empty reply from server" in error_str,
                        "connection refused" in error_str,
                        "connection reset" in error_str,
                        "could not connect" in error_str,
                        "ssl" in error_str and "error" in error_str,
                        "certificate" in error_str and "error" in error_str,
                    ]
                )

                if is_dns_or_tls_error:
                    logger.error(
                        f"[SESSION_ERROR>>SESSION RESET] DNS/TLS error via proxy {proxy.id if proxy else 'unknown'} "
                        f"on attempt {attempt + 1}: {e}"
                    )

                    if proxy:
                        evict_dns_cache(proxy.host)

                    if session:
                        try:
                            await session.close()
                        except Exception:
                            pass
                        session = None

                    if proxy:
                        self.manager.mark_cooldown(
                            proxy.id,
                            self.config.proxy_cooldown_on_connection_error,
                            "dns_or_tls_resolution_error",
                        )

                    last_exception = ProxyHTTPError(
                        f"DNS/TLS resolution error: {e}",
                        proxy_id=proxy.id if proxy else None,
                        attempt=attempt,
                    )

                elif is_connection_error:
                    logger.error(
                        f"Connection error via proxy {proxy.id if proxy else 'unknown'}: {e}"
                    )
                    if proxy:
                        self.manager.mark_cooldown(
                            proxy.id,
                            self.config.proxy_cooldown_on_connection_error,
                            f"connection_error: {type(e).__name__}",
                        )
                    last_exception = ProxyHTTPError(
                        f"Connection error: {e}",
                        proxy_id=proxy.id if proxy else None,
                        attempt=attempt,
                    )

                else:
                    logger.error(f"Unexpected GET error: {e}")
                    if proxy:
                        self.manager.release_proxy(proxy.id)
                    last_exception = ProxyHTTPError(
                        f"GET unexpected error: {e}", attempt=attempt
                    )

            finally:
                if session:
                    await self._return_session(
                        session, impersonate_type, has_curl_options=bool(curl_opts)
                    )

        error_msg = f"All {self.config.max_attempts_per_request} GET attempts failed"
        if last_exception:
            error_msg += f". Last error: {last_exception}"

        logger.error(error_msg)
        raise ProxyHTTPError(error_msg, attempt=attempt)
