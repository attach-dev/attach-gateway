from __future__ import annotations

"""Usage accounting backends for Attach Gateway."""

import inspect
import logging
import os
from datetime import datetime, timezone
from typing import Protocol

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter
except Exception:  # pragma: no cover - optional dep
    Counter = None  # type: ignore

    class Counter:  # type: ignore[misc]
        """Minimal in-memory Counter fallback."""

        def __init__(self, name: str, desc: str, labelnames: list[str]):
            self.labelnames = labelnames
            self.values: dict[tuple[str, ...], float] = {}

        def labels(self, **labels):
            key = tuple(labels.get(name, "") for name in self.labelnames)
            self.values.setdefault(key, 0.0)

            class _Wrapper:
                def __init__(self, parent: Counter, k: tuple[str, ...]) -> None:
                    self.parent = parent
                    self.k = k

                def inc(self, amt: float) -> None:
                    self.parent.values[self.k] += amt

                @property
                def _value(self):
                    class V:
                        def __init__(self, parent: Counter, k: tuple[str, ...]):
                            self.parent = parent
                            self.k = k

                        def get(self) -> float:
                            return self.parent.values[self.k]

                    return V(self.parent, self.k)

            return _Wrapper(self, key)


class AbstractUsageBackend(Protocol):
    """Interface for usage event sinks."""

    async def record(self, **evt) -> None:
        """Persist a single usage event."""
        ...


class NullUsageBackend:
    """No-op usage backend."""

    async def record(self, **evt) -> None:  # pragma: no cover - trivial
        return


class PrometheusUsageBackend:
    """Expose a Prometheus counter for token usage."""

    def __init__(self) -> None:
        if Counter is None:  # pragma: no cover - missing lib
            raise RuntimeError("prometheus_client is required for this backend")
        self.counter = Counter(
            "attach_usage_tokens_total",
            "Total tokens processed by Attach Gateway",
            ["user", "direction", "model"],
        )

    async def record(self, **evt) -> None:
        user = evt.get("user", "unknown")
        model = evt.get("model", "unknown")
        tokens_in = int(evt.get("tokens_in", 0) or 0)
        tokens_out = int(evt.get("tokens_out", 0) or 0)
        self.counter.labels(user=user, direction="in", model=model).inc(tokens_in)
        self.counter.labels(user=user, direction="out", model=model).inc(tokens_out)


class OpenMeterBackend:
    """Send token usage events to OpenMeter."""

    def __init__(self) -> None:
        api_key = os.getenv("OPENMETER_API_KEY")
        if not api_key:
            raise ImportError("OPENMETER_API_KEY is required for OpenMeter")

        self.api_key = api_key
        self.base_url = os.getenv("OPENMETER_URL", "https://openmeter.cloud")
        
        # Use httpx instead of buggy OpenMeter SDK
        try:
            import httpx
            self.client = httpx.AsyncClient(
                timeout=30.0
            )
        except ImportError as exc:
            raise ImportError("httpx is required for OpenMeter") from exc

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if hasattr(self.client, 'aclose'):
            await self.client.aclose()

    async def record(self, **evt) -> None:
        try:
            from uuid import uuid4
        except ImportError as exc:
            return

        base_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        user = evt.get("user")
        model = evt.get("model")
        
        tokens_in = int(evt.get("tokens_in", 0) or 0)
        tokens_out = int(evt.get("tokens_out", 0) or 0)

        # Send separate events for input and output tokens
        events_to_send = []
        
        if tokens_in > 0:
            events_to_send.append({
                "specversion": "1.0",
                "type": "prompt",        # ← Changed from "tokens" to "prompt"
                "id": str(uuid4()),
                "time": base_time,
                "source": "attach-gateway",
                "subject": user,
                "data": {
                    "tokens": tokens_in,
                    "model": model,
                    "type": "input"      # ← This stays the same
                }
            })
        
        if tokens_out > 0:
            events_to_send.append({
                "specversion": "1.0", 
                "type": "prompt",
                "id": str(uuid4()),
                "time": base_time,
                "source": "attach-gateway",
                "subject": user,
                "data": {
                    "tokens": tokens_out,   # ← Single tokens field
                    "model": model,
                    "type": "output"        # ← Add type field
                }
            })

        # Send each event
        for event in events_to_send:
            try:
                response = await self.client.post(
                    f"{self.base_url}/api/v1/events",
                    json=event,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/cloudevents+json"
                    }
                )
                
                if response.status_code not in [200, 201, 202, 204]:
                    logger.warning(f"OpenMeter error: {response.status_code}")
                    
            except Exception as exc:
                logger.warning("OpenMeter request failed: %s", exc)
