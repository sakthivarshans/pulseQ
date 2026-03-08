"""
modules/ingestion/collectors/system_metrics.py
──────────────────────────────────────────────
Real system metrics collector using psutil.
Runs as a background task. Stores ring buffer of last 100 samples.
Served via GET /api/v1/metrics/system
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# In-memory ring buffer — last 100 10-second samples
_metrics_buffer: deque[dict[str, Any]] = deque(maxlen=100)
_running = False
_prev_net = None
_prev_disk = None
_prev_time = None


def get_metrics_buffer() -> list[dict[str, Any]]:
    """Return a copy of the current metrics buffer."""
    return list(_metrics_buffer)


def get_latest_metrics() -> dict[str, Any]:
    """Return the most recent single sample."""
    if _metrics_buffer:
        return _metrics_buffer[-1]
    return _make_empty_sample()


def _make_empty_sample() -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "memory_used_mb": 0,
        "memory_total_mb": 0,
        "disk_read_mb_s": 0.0,
        "disk_write_mb_s": 0.0,
        "net_sent_mb_s": 0.0,
        "net_recv_mb_s": 0.0,
        "process_count": 0,
        "load_avg_1m": 0.0,
    }


def _collect_sample() -> dict[str, Any]:
    global _prev_net, _prev_disk, _prev_time

    if not PSUTIL_AVAILABLE:
        return _make_empty_sample()

    now = time.monotonic()
    elapsed = (now - _prev_time) if _prev_time else 10.0
    _prev_time = now

    sample: dict[str, Any] = {"timestamp": datetime.now(UTC).isoformat()}

    # CPU
    try:
        sample["cpu_percent"] = psutil.cpu_percent(interval=None)
    except Exception:
        sample["cpu_percent"] = 0.0

    # Memory
    try:
        mem = psutil.virtual_memory()
        sample["memory_percent"] = mem.percent
        sample["memory_used_mb"] = round(mem.used / 1024 / 1024)
        sample["memory_total_mb"] = round(mem.total / 1024 / 1024)
    except Exception:
        sample["memory_percent"] = 0.0
        sample["memory_used_mb"] = 0
        sample["memory_total_mb"] = 0

    # Disk I/O rates
    try:
        disk_now = psutil.disk_io_counters()
        if _prev_disk and disk_now:
            read_bytes = disk_now.read_bytes - _prev_disk.read_bytes
            write_bytes = disk_now.write_bytes - _prev_disk.write_bytes
            sample["disk_read_mb_s"] = round(max(0, read_bytes) / elapsed / 1024 / 1024, 3)
            sample["disk_write_mb_s"] = round(max(0, write_bytes) / elapsed / 1024 / 1024, 3)
        else:
            sample["disk_read_mb_s"] = 0.0
            sample["disk_write_mb_s"] = 0.0
        _prev_disk = disk_now
    except Exception:
        sample["disk_read_mb_s"] = 0.0
        sample["disk_write_mb_s"] = 0.0

    # Network I/O rates
    try:
        net_now = psutil.net_io_counters()
        if _prev_net and net_now:
            sent = net_now.bytes_sent - _prev_net.bytes_sent
            recv = net_now.bytes_recv - _prev_net.bytes_recv
            sample["net_sent_mb_s"] = round(max(0, sent) / elapsed / 1024 / 1024, 4)
            sample["net_recv_mb_s"] = round(max(0, recv) / elapsed / 1024 / 1024, 4)
        else:
            sample["net_sent_mb_s"] = 0.0
            sample["net_recv_mb_s"] = 0.0
        _prev_net = net_now
    except Exception:
        sample["net_sent_mb_s"] = 0.0
        sample["net_recv_mb_s"] = 0.0

    # Process count
    try:
        sample["process_count"] = len(psutil.pids())
    except Exception:
        sample["process_count"] = 0

    # Load average (Unix only; Windows returns (0, 0, 0))
    try:
        la = psutil.getloadavg()
        sample["load_avg_1m"] = round(la[0], 2)
    except Exception:
        sample["load_avg_1m"] = 0.0

    return sample


async def start_collector() -> None:
    """Background loop: collect real metrics every 10 seconds."""
    global _running, _prev_time
    if _running:
        return
    _running = True
    _prev_time = time.monotonic()

    if not PSUTIL_AVAILABLE:
        import logging
        logging.getLogger(__name__).warning(
            "psutil not installed — install with: pip install psutil"
        )

    # Warm up counters (first read is always 0 for I/O deltas)
    if PSUTIL_AVAILABLE:
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    while True:
        try:
            sample = _collect_sample()
            _metrics_buffer.append(sample)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Metrics collection error: {e}")
        await asyncio.sleep(10)
