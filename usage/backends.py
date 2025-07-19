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
        try:
            from openmeter import Client  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dep
            raise ImportError("openmeter package is required") from exc

        api_key = os.getenv("OPENMETER_API_KEY")
        if not api_key:
            raise ImportError("OPENMETER_API_KEY is required for OpenMeter")

        url = os.getenv("OPENMETER_URL", "https://openmeter.cloud")
        self.client = Client(api_key=api_key, base_url=url)

    async def aclose(self) -> None:
        """Close the underlying OpenMeter client."""
        try:
            await self.client.aclose()  # type: ignore[call-arg]
        except Exception:  # pragma: no cover - optional
            pass

    async def record(self, **evt) -> None:
        event = {
            "type": "tokens",
            "subject": evt.get("user"),
            "project": evt.get("project"),
            "time": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "data": {
                "tokens_in": int(evt.get("tokens_in", 0) or 0),
                "tokens_out": int(evt.get("tokens_out", 0) or 0),
                "model": evt.get("model"),
            },
        }

        create_fn = self.client.events.create
        import anyio

        try:
            if inspect.iscoroutinefunction(create_fn):
                await create_fn(**event)  # type: ignore[arg-type]
            else:
                await anyio.to_thread.run_sync(create_fn, **event)
        except Exception as exc:  # pragma: no cover - network errors
            logger.warning("OpenMeter create failed: %s", exc)
