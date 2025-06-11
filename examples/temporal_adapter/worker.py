import os
from typing import Any

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker


@workflow.defn
class ProcessChat:
    @workflow.run
    async def run(self, messages: list[dict[str, Any]]) -> str:
        tokens = sum(len(m.get("content", "").split()) for m in messages)
        result = f"Processed {tokens} tokens"
        return result


async def main() -> None:
    client = await Client.connect(os.getenv("TEMPORAL_URL", "localhost:7233"))
    worker = Worker(
        client,
        task_queue=os.getenv("TEMPORAL_QUEUE", "attach-gateway"),
        workflows=[ProcessChat],
    )
    print("Worker started. Waiting for tasks...")
    await worker.run()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
