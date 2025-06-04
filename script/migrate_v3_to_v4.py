#!/usr/bin/env python
"""Migrate MemoryEvent objects from a v3 Weaviate instance to v4."""

import os

import requests
from weaviate import WeaviateClient


def main() -> None:
    src_url = os.getenv("OLD_WEAVIATE_URL", "http://127.0.0.1:6666")
    dest_url = os.getenv("WEAVIATE_URL", "http://127.0.0.1:6666")

    # Fetch all MemoryEvent objects from the v3 instance
    resp = requests.get(f"{src_url}/v1/objects?class=MemoryEvent")
    resp.raise_for_status()
    objects = resp.json().get("objects", [])

    client = WeaviateClient(url=dest_url)
    coll = client.collections.get("MemoryEvent")

    for obj in objects:
        props = obj.get("properties", {})
        props["id"] = obj.get("id")
        coll.data.insert(props)


if __name__ == "__main__":
    main()
