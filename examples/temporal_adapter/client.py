import asyncio
import os

import httpx

JWT = os.environ["JWT"]
GW_URL = os.getenv("GW_URL", "http://127.0.0.1:8080")


async def main() -> None:
    headers = {
        "Authorization": f"Bearer {JWT}",
        "X-Attach-Session": "temporal-demo",
    }
    payload = {
        "input": {
            "messages": [
                {"role": "user", "content": "ping"},
            ]
        },
        "target_url": "temporal://ProcessChat",
    }
    async with httpx.AsyncClient() as cli:
        resp = await cli.post(f"{GW_URL}/a2a/tasks/send", json=payload, headers=headers)
        resp.raise_for_status()
        tid = resp.json()["task_id"]
        while True:
            r = await cli.get(
                f"{GW_URL}/a2a/tasks/status/{tid}",
                headers={"Authorization": f"Bearer {JWT}"},
            )
            data = r.json()
            if data["state"] in {"done", "error"}:
                print(data)
                break
            await asyncio.sleep(0.5)


if __name__ == "__main__":
    asyncio.run(main())
