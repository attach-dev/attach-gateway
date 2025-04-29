# mem/weaviate.py
import os, weaviate, uuid, time, asyncio

_client = weaviate.Client(os.getenv("WEAVIATE_URL"))

async def write(event: dict):
    event["id"] = uuid.uuid4().hex
    event["timestamp"] = int(time.time())
    _client.data_object.create(event, "MemoryEvent", uuid=event["id"])
