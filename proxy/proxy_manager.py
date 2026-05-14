#!/usr/bin/env python3
"""
Production-ready Proxy Manager

Implements atomic proxy reservation, cooldown management, and watchdog cleanup.
Supports both single-node in-memory and Redis-based distributed operation.

Redis mode (default when REDIS_URL is set):
  - All containers share a single proxy pool state
  - A proxy in cooldown in container-1 is immediately unavailable in all others
  - Reservations auto-expire via Redis TTL — no deadlocks from crashed workers
  - Cooldowns auto-expire via Redis TTL — no cleanup needed

InMemory mode (fallback when Redis is unavailable):
  - Single-process only, suitable for local dev
  - Each container has its own independent proxy state

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GREP CHEATSHEET  (docker compose logs blinkit --since 10m 2>&1 | ...)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# --- Counters ---
grep -c "[PROXY] SUCCESS"                        # total successful requests
grep -c "[PROXY] COOLDOWN"                       # total cooldowns triggered
grep -c "[PROXY] COOLDOWN reason=429_rate_limit" # 429-specific cooldowns
grep -c "[PROXY] COOLDOWN reason=403_forbidden"  # 403-specific cooldowns
grep -c "[PROXY] RESERVED"                       # total reservations made
grep -c "[PROXY] RELEASED"                       # total reservations released
grep -c "[PROXY] EXHAUSTED"                      # times no proxy was available
grep -c "[PROXY] PROGRESSIVE"                    # progressive backoff triggers
grep -c "[PROXY] ORPHANED"                       # orphaned reservation cleanups

# --- Pool health (every 30s) ---
grep "[PROXY] POOL"                              # periodic snapshot lines
grep "[PROXY] POOL" | tail -1                    # latest snapshot
grep "[PROXY] POOL" | grep -oP "available=\K[0-9]+" | tail -1
grep "[PROXY] POOL" | grep -oP "in_cooldown=\K[0-9]+" | tail -1
grep "[PROXY] POOL" | grep -oP "utilization=\K[0-9.]+"

# --- Cooldown breakdown ---
grep "[PROXY] COOLDOWN" | grep -oP "reason=\K\S+" | sort | uniq -c | sort -rn
grep "[PROXY] COOLDOWN" | grep -oP "seconds=\K[0-9]+" | sort -n | uniq -c
grep "[PROXY] POOL" | tail -1 | grep -oP "cooldown_reasons=\K\[.*?\]"

# --- Progressive backoff ---
grep "[PROXY] PROGRESSIVE" | grep -oP "failed_count=\K[0-9]+" | sort -n | uniq -c
grep "[PROXY] PROGRESSIVE" | grep -oP "cooldown_seconds=\K[0-9]+" | sort -n | uniq -c

# --- Redis / startup ---
grep "[PROXYMGR]"                                # all manager lifecycle events
grep "[PROXYMGR] Redis"                          # Redis connection status
grep "[PROXYMGR] Ready"                          # startup confirmation

# --- Success rate over time ---
grep "[PROXY] SUCCESS" | grep -oP "proxy_success_rate=\K[0-9.]+" | awk '{s+=$1;n++} END {print s/n "%"}'
grep "[PROXY] SUCCESS" | grep -oP "lifetime_successes=\K[0-9]+" | tail -1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import atexit
import logging
import os
import random
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote

import requests

# ---------------------------------------------------------------------------
# Logging — use loguru if available (matches proxy_client.py), else stdlib
# ---------------------------------------------------------------------------
try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger("ProxyManager")

# Redis key namespace
_PREFIX = os.getenv("PROXY_REDIS_PREFIX", "proxymgr:")

# How often the watchdog emits a pool health snapshot (seconds)
_POOL_LOG_INTERVAL = int(os.getenv("PROXY_POOL_LOG_INTERVAL", "30"))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class ProxyStatus(Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    COOLDOWN = "cooldown"


@dataclass
class ProxyInfo:
    id: str
    host: str
    port: int
    username: str
    password: str
    failed_count: int = 0
    last_used: Optional[datetime] = None
    last_success: Optional[datetime] = None
    total_requests: int = 0
    successful_requests: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def url(self) -> str:
        u = quote(self.username, safe="")
        p = quote(self.password, safe="")
        return f"http://{u}:{p}@{self.host}:{self.port}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "failed_count": self.failed_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "last_success": self.last_success.isoformat()
            if self.last_success
            else None,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "success_rate": round(self.success_rate, 1),
        }


@dataclass
class ProxyReservation:
    proxy_id: str
    owner_id: str
    reserved_at: datetime
    reserved_until: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.reserved_until

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proxy_id": self.proxy_id,
            "owner_id": self.owner_id,
            "reserved_at": self.reserved_at.isoformat(),
            "reserved_until": self.reserved_until.isoformat(),
            "is_expired": self.is_expired,
        }


@dataclass
class ProxyCooldown:
    proxy_id: str
    cooldown_until: datetime
    reason: str

    @property
    def is_active(self) -> bool:
        return datetime.now() < self.cooldown_until

    @property
    def remaining_seconds(self) -> int:
        if not self.is_active:
            return 0
        return int((self.cooldown_until - datetime.now()).total_seconds())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proxy_id": self.proxy_id,
            "cooldown_until": self.cooldown_until.isoformat(),
            "reason": self.reason,
            "is_active": self.is_active,
            "remaining_seconds": self.remaining_seconds,
        }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ProxyConfig:
    def __init__(self):
        self.connect_timeout = 5.0
        self.read_timeout = 15.0
        self.timeout = 60.0

        self.reservation_ttl = 90.0  # seconds

        self.proxy_cooldown_on_429 = 20.0
        self.cooldown_on_403 = 30.0
        self.proxy_cooldown_on_timeout = 20.0
        self.cooldown_on_5xx = 10.0
        self.default_cooldown = 15.0
        self.proxy_cooldown_on_connection_error = 30.0

        self.max_attempts_per_request = 5
        self.progressive_failure_threshold = 3

        self.watchdog_interval = 5.0

        self.browser_impersonation = "chrome120"


# ---------------------------------------------------------------------------
# InMemory storage (single-node fallback)
# ---------------------------------------------------------------------------


class InMemoryStorage:
    """Thread-safe in-memory storage. Suitable for local dev or single-container."""

    def __init__(self):
        self._proxies: Dict[str, ProxyInfo] = {}
        self._reservations: Dict[str, ProxyReservation] = {}
        self._cooldowns: Dict[str, ProxyCooldown] = {}
        self._lock = threading.RLock()

    def add_proxy(self, proxy: ProxyInfo) -> None:
        with self._lock:
            self._proxies[proxy.id] = proxy

    def get_proxy(self, proxy_id: str) -> Optional[ProxyInfo]:
        with self._lock:
            return self._proxies.get(proxy_id)

    def get_all_proxies(self) -> List[ProxyInfo]:
        with self._lock:
            return list(self._proxies.values())

    def reserve_proxy(self, reservation: ProxyReservation) -> bool:
        with self._lock:
            if reservation.proxy_id not in self._proxies:
                return False
            if reservation.proxy_id in self._reservations:
                return False
            cd = self._cooldowns.get(reservation.proxy_id)
            if cd and cd.is_active:
                return False
            self._reservations[reservation.proxy_id] = reservation
            return True

    def release_reservation(self, proxy_id: str) -> bool:
        with self._lock:
            return self._reservations.pop(proxy_id, None) is not None

    def add_cooldown(self, cooldown: ProxyCooldown) -> None:
        with self._lock:
            self._cooldowns[cooldown.proxy_id] = cooldown
            self._reservations.pop(cooldown.proxy_id, None)

    def get_available_proxy_ids(self) -> Set[str]:
        with self._lock:
            reserved = set(self._reservations)
            cooled = {pid for pid, cd in self._cooldowns.items() if cd.is_active}
            return set(self._proxies) - reserved - cooled

    def get_expired_reservations(self) -> List[ProxyReservation]:
        with self._lock:
            return [r for r in self._reservations.values() if r.is_expired]

    def cleanup_expired_cooldowns(self) -> None:
        with self._lock:
            expired = [pid for pid, cd in self._cooldowns.items() if not cd.is_active]
            for pid in expired:
                self._cooldowns.pop(pid, None)

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            active_reservations = {
                pid: r.to_dict()
                for pid, r in self._reservations.items()
                if not r.is_expired
            }
            active_cooldowns = {
                pid: cd.to_dict() for pid, cd in self._cooldowns.items() if cd.is_active
            }
            proxy_stats = []
            for proxy in self._proxies.values():
                r = self._reservations.get(proxy.id)
                cd = self._cooldowns.get(proxy.id)
                if r and not r.is_expired:
                    status = ProxyStatus.RESERVED.value
                elif cd and cd.is_active:
                    status = ProxyStatus.COOLDOWN.value
                else:
                    status = ProxyStatus.AVAILABLE.value
                proxy_stats.append(
                    {
                        **proxy.to_dict(),
                        "status": status,
                        "reserved_by": r.owner_id if r else None,
                        "reserved_until": r.reserved_until.isoformat() if r else None,
                        "cooldown_until": cd.cooldown_until.isoformat() if cd else None,
                        "cooldown_reason": cd.reason if cd else None,
                    }
                )
            return {
                "total_proxies": len(self._proxies),
                "available_proxies": len(self.get_available_proxy_ids()),
                "active_reservations": len(active_reservations),
                "active_cooldowns": len(active_cooldowns),
                "reservations": active_reservations,
                "cooldowns": active_cooldowns,
                "proxies": proxy_stats,
                "timestamp": datetime.now().isoformat(),
            }


# ---------------------------------------------------------------------------
# Redis storage (multi-container shared state)
# ---------------------------------------------------------------------------


class RedisStorage:
    """
    Redis-backed storage. Shares proxy state across all containers.

    Key design:
      {prefix}proxy:{id}         Hash   — proxy metadata (written once at startup)
      {prefix}reservation:{id}   String — owner_id; TTL = reservation TTL
      {prefix}cooldown:{id}      String — reason; TTL = cooldown duration
      {prefix}proxy_ids          Set    — all registered proxy IDs

    Atomicity:
      - reserve_proxy uses SET NX (set-if-not-exists) — exactly one container wins
      - add_cooldown uses a pipeline — cooldown + reservation delete are atomic
      - TTL expiry auto-releases reservations from crashed workers
    """

    def __init__(self, redis_client, platform):
        self._redis = redis_client
        self.platform = platform
        self._proxies: Dict[str, ProxyInfo] = {}
        self._lock = threading.RLock()
        logger.info(f"[PROXYMGR] RedisStorage initialised prefix={_PREFIX!r}")

    @classmethod
    def from_env(cls, platform) -> "RedisStorage":
        import redis as redis_lib

        url = os.environ.get("REDIS_URL")
        if not url:
            raise RuntimeError("REDIS_URL is not set")
        client = redis_lib.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        client.ping()
        host = url.split("@")[-1]
        logger.info(f"[PROXYMGR] Redis connected host={host}")
        return cls(client, platform)

    @staticmethod
    def _pk(proxy_id: str) -> str:
        return f"{_PREFIX}proxy:{proxy_id}"

    def _rk(self, proxy_id: str) -> str:
        return f"{_PREFIX}{self.platform}:reservation:{proxy_id}"

    def _ck(self, proxy_id: str) -> str:
        return f"{_PREFIX}{self.platform}:cooldown:{proxy_id}"

    @staticmethod
    def _ids_key() -> str:
        return f"{_PREFIX}proxy_ids"

    def add_proxy(self, proxy: ProxyInfo) -> None:
        with self._lock:
            self._proxies[proxy.id] = proxy
        pipe = self._redis.pipeline()
        pipe.hset(
            self._pk(proxy.id),
            mapping={
                "id": proxy.id,
                "host": proxy.host,
                "port": str(proxy.port),
                "username": proxy.username,
                "password": proxy.password,
            },
        )
        pipe.sadd(self._ids_key(), proxy.id)
        pipe.execute()

    def get_proxy(self, proxy_id: str) -> Optional[ProxyInfo]:
        with self._lock:
            return self._proxies.get(proxy_id)

    def get_all_proxies(self) -> List[ProxyInfo]:
        with self._lock:
            return list(self._proxies.values())

    def reserve_proxy(self, reservation: ProxyReservation) -> bool:
        proxy_id = reservation.proxy_id
        with self._lock:
            if proxy_id not in self._proxies:
                return False
        if self._redis.exists(self._ck(proxy_id)):
            return False
        ttl = max(1, int((reservation.reserved_until - datetime.now()).total_seconds()))
        reserved = self._redis.set(
            self._rk(proxy_id),
            reservation.owner_id,
            nx=True,
            ex=ttl,
        )
        return bool(reserved)

    def release_reservation(self, proxy_id: str) -> bool:
        return self._redis.delete(self._rk(proxy_id)) > 0

    def add_cooldown(self, cooldown: ProxyCooldown) -> None:
        ttl = max(1, int((cooldown.cooldown_until - datetime.now()).total_seconds()))
        pipe = self._redis.pipeline()
        pipe.set(self._ck(cooldown.proxy_id), cooldown.reason or "unknown", ex=ttl)
        pipe.delete(self._rk(cooldown.proxy_id))
        pipe.execute()

    def get_available_proxy_ids(self) -> Set[str]:
        with self._lock:
            all_ids = list(self._proxies.keys())
        if not all_ids:
            return set()
        pipe = self._redis.pipeline()
        for proxy_id in all_ids:
            pipe.exists(self._rk(proxy_id))
            pipe.exists(self._ck(proxy_id))
        results = pipe.execute()
        available = set()
        for i, proxy_id in enumerate(all_ids):
            if not results[i * 2] and not results[i * 2 + 1]:
                available.add(proxy_id)
        return available

    def get_expired_reservations(self) -> List[ProxyReservation]:
        # Redis TTL handles expiry automatically
        return []

    def cleanup_expired_cooldowns(self) -> None:
        # Redis TTL handles expiry automatically
        pass

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            all_ids = list(self._proxies.keys())
        if not all_ids:
            return {
                "total_proxies": 0,
                "available_proxies": 0,
                "active_reservations": 0,
                "active_cooldowns": 0,
                "reservations": {},
                "cooldowns": {},
                "proxies": [],
            }
        pipe = self._redis.pipeline()
        for proxy_id in all_ids:
            pipe.get(self._rk(proxy_id))  # owner or None
            pipe.get(self._ck(proxy_id))  # cooldown reason or None
            pipe.ttl(self._ck(proxy_id))  # cooldown TTL remaining
        results = pipe.execute()

        active_reservations: Dict[str, Any] = {}
        active_cooldowns: Dict[str, Any] = {}
        proxy_stats = []

        for i, proxy_id in enumerate(all_ids):
            owner = results[i * 3]
            cd_reason = results[i * 3 + 1]
            cd_ttl = results[i * 3 + 2]
            with self._lock:
                proxy = self._proxies.get(proxy_id)
            if not proxy:
                continue
            if owner:
                status = ProxyStatus.RESERVED.value
                cd_until = None
                active_reservations[proxy_id] = {"owner": owner}
            elif cd_reason:
                status = ProxyStatus.COOLDOWN.value
                cd_until = (
                    datetime.now() + timedelta(seconds=max(0, cd_ttl))
                ).isoformat()
                active_cooldowns[proxy_id] = {
                    "reason": cd_reason,
                    "cooldown_until": cd_until,
                    "ttl_seconds": cd_ttl,
                }
            else:
                status = ProxyStatus.AVAILABLE.value
                cd_until = None
            proxy_stats.append(
                {
                    **proxy.to_dict(),
                    "status": status,
                    "reserved_by": owner,
                    "reserved_until": None,
                    "cooldown_until": cd_until,
                    "cooldown_reason": cd_reason,
                }
            )

        available = sum(
            1 for p in proxy_stats if p["status"] == ProxyStatus.AVAILABLE.value
        )
        return {
            "total_proxies": len(all_ids),
            "available_proxies": available,
            "active_reservations": len(active_reservations),
            "active_cooldowns": len(active_cooldowns),
            "reservations": active_reservations,
            "cooldowns": active_cooldowns,
            "proxies": proxy_stats,
            "timestamp": datetime.now().isoformat(),
        }


# ---------------------------------------------------------------------------
# ProxyManager
# ---------------------------------------------------------------------------


class ProxyManager:
    """
    Proxy Manager with pluggable storage backend.

    All public operations emit structured [PROXY] log lines that are
    individually grep-able from docker logs for monitoring/alerting.
    """

    def __init__(
        self,
        config: Optional[ProxyConfig] = None,
        storage_backend=None,
        platform: str = "blinkit",
    ):
        self.platform = platform
        self.config = config or ProxyConfig()
        self.storage = storage_backend or InMemoryStorage()
        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._last_pool_log = 0.0

        # In-process lifetime counters (reset on container restart)
        self._counter_lock = threading.Lock()
        self._cnt_reserved = 0
        self._cnt_released = 0
        self._cnt_success = 0
        self._cnt_cooldown = 0
        self._cnt_exhausted = 0

        self._start_watchdog()
        atexit.register(self.shutdown)
        logger.info("[PROXYMGR] ProxyManager initialized")

    # -- proxy loading -------------------------------------------------------

    def load_proxies_from_url_list(self, proxy_url_list: List[str]) -> int:
        """
        Load proxies from a list of strings.
        Accepted: "user:pass:host:port" or "http://user:pass@host:port"
        """
        loaded = 0
        failed = 0
        for raw in proxy_url_list:
            try:
                raw = raw.strip()
                if not raw:
                    continue
                if raw.startswith("http://"):
                    raw = raw[7:]
                elif raw.startswith("https://"):
                    raw = raw[8:]

                if "@" in raw:
                    auth, hostport = raw.rsplit("@", 1)
                    username, password = auth.split(":", 1)
                    host, port_str = hostport.rsplit(":", 1)
                else:
                    parts = raw.split(":")
                    if len(parts) != 4:
                        logger.warning(
                            f"[PROXYMGR] Invalid proxy format skipped: {raw}"
                        )
                        failed += 1
                        continue
                    username, password, host, port_str = parts

                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError(f"Port out of range: {port}")
                if not host.strip():
                    raise ValueError("Empty host")

                proxy = ProxyInfo(
                    id=str(uuid.uuid4()),
                    host=host.strip(),
                    port=port,
                    username=username.strip(),
                    password=password.strip(),
                )
                self.storage.add_proxy(proxy)
                loaded += 1

            except Exception as e:
                logger.error(f"[PROXYMGR] Failed to load proxy '{raw}': {e}")
                failed += 1

        logger.info(
            f"[PROXYMGR] Proxy load complete "
            f"loaded={loaded} failed={failed} total={loaded + failed}"
        )
        return loaded

    # -- core operations -----------------------------------------------------

    def reserve_proxy(self, owner_id: str) -> Optional[ProxyInfo]:
        """
        Atomically reserve an available proxy.
        Shuffles candidates so containers don't race for the same proxy.

        Grep: [PROXY] RESERVED   — successful reservation
              [PROXY] EXHAUSTED  — no proxies available
        """
        available_ids = list(self.storage.get_available_proxy_ids())
        total = len(self.storage.get_all_proxies())

        if not available_ids:
            with self._counter_lock:
                self._cnt_exhausted += 1
                exhausted_total = self._cnt_exhausted
            status = self.storage.get_status()
            logger.warning(
                f"[PROXY] EXHAUSTED "
                f"available=0 "
                f"total={total} "
                f"reserved={status['active_reservations']} "
                f"in_cooldown={status['active_cooldowns']} "
                f"owner={owner_id} "
                f"lifetime_exhaustions={exhausted_total}"
            )
            return None

        random.shuffle(available_ids)

        for proxy_id in available_ids:
            reservation = ProxyReservation(
                proxy_id=proxy_id,
                owner_id=owner_id,
                reserved_at=datetime.now(),
                reserved_until=datetime.now()
                + timedelta(seconds=self.config.reservation_ttl),
            )
            if self.storage.reserve_proxy(reservation):
                proxy = self.storage.get_proxy(proxy_id)
                if proxy:
                    proxy.last_used = datetime.now()
                    with self._counter_lock:
                        self._cnt_reserved += 1
                        reserved_total = self._cnt_reserved
                    logger.info(
                        f"[PROXY] RESERVED "
                        f"proxy_id={proxy_id[:8]} "
                        f"host={proxy.host}:{proxy.port} "
                        f"owner={owner_id} "
                        f"pool_available={len(available_ids) - 1} "
                        f"pool_total={total} "
                        f"lifetime_reserved={reserved_total}"
                    )
                    return proxy

        logger.warning(
            f"[PROXY] RESERVE_RACE_FAILED "
            f"tried={len(available_ids)} "
            f"owner={owner_id} "
            f"(all candidates became unavailable between check and reserve)"
        )
        return None

    def release_proxy(self, proxy_id: str) -> bool:
        """
        Release a proxy reservation.
        Grep: [PROXY] RELEASED
        """
        success = self.storage.release_reservation(proxy_id)
        if success:
            with self._counter_lock:
                self._cnt_released += 1
                released_total = self._cnt_released
            logger.info(
                f"[PROXY] RELEASED "
                f"proxy_id={proxy_id[:8]} "
                f"lifetime_released={released_total}"
            )
        return success

    def mark_success(self, proxy_id: str) -> bool:
        """
        Mark a proxy request as successful.
        Grep: [PROXY] SUCCESS
        """
        proxy = self.storage.get_proxy(proxy_id)
        if not proxy:
            logger.warning(
                f"[PROXY] MARK_SUCCESS_FAILED "
                f"proxy_id={proxy_id[:8]} reason=proxy_not_found"
            )
            return False

        proxy.last_success = datetime.now()
        proxy.successful_requests += 1
        proxy.total_requests += 1
        proxy.failed_count = 0
        self.release_proxy(proxy_id)

        with self._counter_lock:
            self._cnt_success += 1
            success_total = self._cnt_success

        logger.info(
            f"[PROXY] SUCCESS "
            f"proxy_id={proxy_id[:8]} "
            f"host={proxy.host}:{proxy.port} "
            f"proxy_requests={proxy.total_requests} "
            f"proxy_successes={proxy.successful_requests} "
            f"proxy_success_rate={proxy.success_rate:.1f}% "
            f"proxy_failed_count={proxy.failed_count} "
            f"lifetime_successes={success_total}"
        )
        return True

    def mark_cooldown(
        self, proxy_id: str, seconds: float, reason: str = "manual"
    ) -> bool:
        """
        Put a proxy into cooldown with optional progressive backoff.
        Grep: [PROXY] COOLDOWN          — all cooldowns
              [PROXY] PROGRESSIVE       — when backoff multiplier kicks in
        """
        proxy = self.storage.get_proxy(proxy_id)
        if not proxy:
            logger.warning(
                f"[PROXY] MARK_COOLDOWN_FAILED "
                f"proxy_id={proxy_id[:8]} reason=proxy_not_found"
            )
            return False

        proxy.failed_count += 1
        proxy.total_requests += 1
        original_seconds = seconds
        is_progressive = False
        multiplier = 1

        if proxy.failed_count >= self.config.progressive_failure_threshold:
            multiplier = 2 ** (
                proxy.failed_count - self.config.progressive_failure_threshold
            )
            seconds = int(seconds * multiplier)
            is_progressive = True
            logger.warning(
                f"[PROXY] PROGRESSIVE "
                f"proxy_id={proxy_id[:8]} "
                f"host={proxy.host}:{proxy.port} "
                f"failed_count={proxy.failed_count} "
                f"base_seconds={original_seconds} "
                f"multiplier={multiplier}x "
                f"cooldown_seconds={seconds} "
                f"reason={reason}"
            )

        cooldown = ProxyCooldown(
            proxy_id=proxy_id,
            cooldown_until=datetime.now() + timedelta(seconds=seconds),
            reason=reason,
        )
        self.storage.add_cooldown(cooldown)

        with self._counter_lock:
            self._cnt_cooldown += 1
            cooldown_total = self._cnt_cooldown

        status = self.storage.get_status()
        logger.warning(
            f"[PROXY] COOLDOWN "
            f"proxy_id={proxy_id[:8]} "
            f"host={proxy.host}:{proxy.port} "
            f"reason={reason} "
            f"seconds={seconds} "
            f"proxy_failed_count={proxy.failed_count} "
            f"progressive={is_progressive} "
            f"pool_available={status['available_proxies']} "
            f"pool_total={status['total_proxies']} "
            f"pool_in_cooldown={status['active_cooldowns']} "
            f"lifetime_cooldowns={cooldown_total}"
        )
        return True

    def get_status(self) -> Dict[str, Any]:
        status = self.storage.get_status()
        with self._counter_lock:
            status["lifetime_counters"] = {
                "reserved": self._cnt_reserved,
                "released": self._cnt_released,
                "success": self._cnt_success,
                "cooldown": self._cnt_cooldown,
                "exhausted": self._cnt_exhausted,
            }
        return status

    # -- watchdog ------------------------------------------------------------

    def _start_watchdog(self) -> None:
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="ProxyManager-Watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()
        logger.info("[PROXYMGR] Watchdog started")

    def _watchdog_loop(self) -> None:
        import time as _time

        while not self._stop_event.is_set():
            try:
                # Handle orphaned reservations (InMemory only — Redis uses TTL)
                for reservation in self.storage.get_expired_reservations():
                    logger.warning(
                        f"[PROXY] ORPHANED "
                        f"proxy_id={reservation.proxy_id[:8]} "
                        f"owner={reservation.owner_id} "
                        f"expired_at={reservation.reserved_until.isoformat()}"
                    )
                    self.mark_cooldown(
                        reservation.proxy_id,
                        int(self.config.default_cooldown),
                        "orphaned_reservation",
                    )

                self.storage.cleanup_expired_cooldowns()

                # Periodic pool snapshot
                now = _time.time()
                if now - self._last_pool_log >= _POOL_LOG_INTERVAL:
                    self._last_pool_log = now
                    self._log_pool_snapshot()

            except Exception as e:
                logger.error(f"[PROXYMGR] Watchdog error: {e}")

            self._stop_event.wait(self.config.watchdog_interval)

    def _log_pool_snapshot(self) -> None:
        """
        Emit a single-line pool health snapshot.

        Grep: [PROXY] POOL
        Example output:
          [PROXY] POOL total=400 available=312 reserved=28 in_cooldown=60
                       utilization=22.0% cooldown_reasons=[429_rate_limit=58 timeout=2]
                       lifetime_success=37658 lifetime_cooldown=12423 lifetime_exhausted=0
                       lifetime_reserved=50081
        """
        try:
            status = self.storage.get_status()
            total = status["total_proxies"]
            available = status["available_proxies"]
            reserved = status["active_reservations"]
            in_cooldown = status["active_cooldowns"]

            # Cooldown breakdown by reason
            reason_counts: Dict[str, int] = {}
            for cd in status.get("cooldowns", {}).values():
                r = cd.get("reason", "unknown")
                reason_counts[r] = reason_counts.get(r, 0) + 1
            reasons_str = (
                " ".join(
                    f"{r}={c}"
                    for r, c in sorted(reason_counts.items(), key=lambda x: -x[1])
                )
                or "none"
            )

            utilization = round((1 - available / total) * 100, 1) if total else 0.0

            with self._counter_lock:
                lt_success = self._cnt_success
                lt_cooldown = self._cnt_cooldown
                lt_exhausted = self._cnt_exhausted
                lt_reserved = self._cnt_reserved

            logger.info(
                f"[PROXY] POOL "
                f"total={total} "
                f"available={available} "
                f"reserved={reserved} "
                f"in_cooldown={in_cooldown} "
                f"utilization={utilization}% "
                f"cooldown_reasons=[{reasons_str}] "
                f"lifetime_success={lt_success} "
                f"lifetime_cooldown={lt_cooldown} "
                f"lifetime_exhausted={lt_exhausted} "
                f"lifetime_reserved={lt_reserved}"
            )
        except Exception as e:
            logger.error(f"[PROXYMGR] Pool snapshot error: {e}")

    def shutdown(self) -> None:
        logger.info("[PROXYMGR] Shutting down ProxyManager...")
        self._stop_event.set()
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=5.0)
        try:
            self._log_pool_snapshot()  # final snapshot on shutdown
        except Exception:
            pass
        logger.info("[PROXYMGR] Shutdown complete")

    def __del__(self):
        self.shutdown()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_global_manager: Optional[ProxyManager] = None
_global_manager_lock = threading.Lock()

def _fetch_proxy_groups_from_openbao() -> Dict[str, List[str]]:
    addr = os.getenv("OPENBAO_ADDR", "").rstrip("/")
    username = os.getenv("OPENBAO_USERNAME", "")
    password = os.getenv("OPENBAO_PASSWORD", "")
    secret_path = os.getenv("OPENBAO_SECRET_PATH", "secret/data/zodiac/config").lstrip("/")
    timeout = 10

    if not (addr and username and password):
        logger.warning(
            "[PROXYMGR] Missing OpenBao credentials | "
            f"addr={bool(addr)} username={bool(username)} password={bool(password)}"
        )
        return {}

    try:
        logger.info(f"[PROXYMGR] OpenBao login start | user={username} | addr={addr}")

        login_resp = requests.post(
            f"{addr}/v1/auth/userpass/login/{username}",
            json={"password": password},
            timeout=timeout,
        )

        logger.info(f"[PROXYMGR] Login response | status={login_resp.status_code}")

        if login_resp.status_code != 200:
            logger.error(
                f"[PROXYMGR] Login failed | status={login_resp.status_code} | body={login_resp.text}"
            )
            return {}

        login_data = login_resp.json()
        if not isinstance(login_data, dict):
            logger.error("[PROXYMGR] Invalid login response (not JSON dict)")
            return {}

        auth_data = login_data.get("auth", {})
        if not isinstance(auth_data, dict):
            logger.error("[PROXYMGR] Missing 'auth' in login response")
            return {}

        client_token = auth_data.get("client_token")
        if not client_token:
            logger.error("[PROXYMGR] Missing 'client_token' in login response")
            return {}

        logger.info("[PROXYMGR] OpenBao login successful")
        logger.info(f"[PROXYMGR] Fetching secret | path={secret_path}")

        secret_resp = requests.get(
            f"{addr}/v1/{secret_path}",
            headers={"X-Vault-Token": client_token},
            timeout=timeout,
        )

        logger.info(f"[PROXYMGR] Secret response | status={secret_resp.status_code}")

        if secret_resp.status_code != 200:
            logger.error(
                f"[PROXYMGR] Secret fetch failed | status={secret_resp.status_code} | body={secret_resp.text}"
            )
            return {}

        secret_data = secret_resp.json()
        if not isinstance(secret_data, dict):
            logger.error("[PROXYMGR] Secret response is not JSON dict")
            return {}

        data_block = secret_data.get("data", {})
        if not isinstance(data_block, dict):
            logger.error("[PROXYMGR] Missing 'data' block in secret response")
            return {}

        payload = data_block.get("data", {})
        if not isinstance(payload, dict):
            logger.error("[PROXYMGR] Invalid payload structure (missing inner data)")
            return {}

        proxies = payload.get("proxies", [])

        if not isinstance(proxies, list):
            logger.error(f"[PROXYMGR] 'proxies' is not a list | type={type(proxies)}")
            return {}

        cleaned: List[str] = []
        skipped = 0

        for proxy in proxies:
            if not isinstance(proxy, str):
                skipped += 1
                continue

            proxy = proxy.strip()
            if not proxy:
                skipped += 1
                continue

            cleaned.append(proxy)

        logger.info(
            f"[PROXYMGR] Proxy cleaning done | valid={len(cleaned)} | skipped={skipped}"
        )

        if not cleaned:
            logger.warning("[PROXYMGR] No valid proxies found after cleaning")

        return {"proxies": cleaned}

    except requests.exceptions.Timeout:
        logger.error("[PROXYMGR] OpenBao request timeout")
        return {}

    except requests.exceptions.ConnectionError:
        logger.error("[PROXYMGR] OpenBao connection error (is server running?)")
        return {}

    except Exception as e:
        logger.exception(f"[PROXYMGR] Unexpected error: {e}")
        return {}

def get_all_proxies() -> List[str]:
    """Return all proxies from OpenBao payload."""
    proxy_groups = _fetch_proxy_groups_from_openbao()
    all_proxies: List[str] = []
    for values in proxy_groups.values():
        all_proxies.extend(values)
    return all_proxies

def get_global_manager(keys: Optional[List[str]] = None) -> ProxyManager:
    """
    Get or create the shared ProxyManager instance.

    Redis-backed when REDIS_URL is set (shared across all containers).
    InMemory fallback otherwise.
    """
    global _global_manager
    if _global_manager is not None:
        return _global_manager

    with _global_manager_lock:
        platform = os.getenv("PLATFORM", "blinkit")
        logger.info(f"PLATFORM<><><>{platform}<><><>PLATFORM")
        if _global_manager is not None:  # double-checked locking
            return _global_manager

        proxy_groups = _fetch_proxy_groups_from_openbao()
        if not proxy_groups:
            logger.warning(
                "[PROXYMGR] No proxy groups loaded from OpenBao. "
                "Set OPENBAO_ADDR / OPENBAO_USERNAME / OPENBAO_PASSWORD and verify secret path."
            )

        total_proxies: List[str] = []
        for values in proxy_groups.values():
            total_proxies.extend(values)

        storage = None
        try:
            storage = RedisStorage.from_env(platform=platform)
            logger.info(
                f"[PROXYMGR] Storage=redis (proxy state shared across all containers)"
            )
        except Exception as e:
            logger.warning(
                f"[PROXYMGR] Storage=inmemory "
                f"Redis unavailable: {e} — "
                f"proxy state will NOT be shared across containers"
            )

        _global_manager = ProxyManager(storage_backend=storage)
        _global_manager.load_proxies_from_url_list(total_proxies)

        status = _global_manager.get_status()
        logger.info(
            f"[PROXYMGR] Ready "
            f"total_proxies={status['total_proxies']} "
            f"storage={'redis' if storage else 'inmemory'}"
        )

    return _global_manager


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def _mgr() -> ProxyManager:
    if _global_manager is None:
        raise RuntimeError(
            "[PROXYMGR] ProxyManager not initialised — call get_global_manager() first."
        )
    return _global_manager


def reserve_proxy(owner_id: str) -> Optional[ProxyInfo]:
    return _mgr().reserve_proxy(owner_id)


def release_proxy(proxy_id: str) -> bool:
    return _mgr().release_proxy(proxy_id)


def mark_success(proxy_id: str) -> bool:
    return _mgr().mark_success(proxy_id)


def mark_cooldown(proxy_id: str, seconds: float, reason: str = "manual") -> bool:
    return _mgr().mark_cooldown(proxy_id, seconds, reason)


def get_status() -> Dict[str, Any]:
    return _mgr().get_status()
