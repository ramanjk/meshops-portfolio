"""Smoke: the Prom exporter binds a port and returns Prometheus text on /metrics."""
from __future__ import annotations

import socket
import urllib.request

from prometheus_client import REGISTRY, Counter, start_http_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_metrics_endpoint_serves_text() -> None:
    port = _free_port()
    counter = Counter("meshops_test_counter", "test")
    counter.inc()
    start_http_server(port, registry=REGISTRY)
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics").read().decode()
    assert "meshops_test_counter" in body
    assert "1.0" in body
