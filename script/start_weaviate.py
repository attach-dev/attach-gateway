#!/usr/bin/env python
"""
Start an **embedded Weaviate v4** instance for local dev.

Usage
-----
python script/start_weaviate.py [--port 6666]

• Boots the embedded DB in‑process and blocks forever.
• Creates a `MemoryEvent` collection if it does not exist.
"""

import argparse, time
from weaviate import WeaviateClient
from weaviate.embedded import EmbeddedOptions
from weaviate.exceptions import WeaviateBaseError

def main() -> None:
    parser = argparse.ArgumentParser(description="Start embedded Weaviate")
    parser.add_argument("--port", type=int, default=6666, help="HTTP port (default 6666)")
    args = parser.parse_args()

    client = WeaviateClient(
        embedded_options=EmbeddedOptions(
            port=args.port,
            hostname="127.0.0.1",           # ← new
            persistence_data_path=".weaviate",
        )
    )

    try:
        if "MemoryEvent" not in client.collections.list().keys():
            client.collections.create(name="MemoryEvent")
            print("Created collection MemoryEvent")
    except WeaviateBaseError as exc:
        print(f"⚠️  Could not create collection: {exc}")

    print(f"✅ Embedded Weaviate ready on http://localhost:{args.port}")

    # Block process forever so the container/lonely process stays alive
    try:
        while True:
            time.sleep(3600)
    finally:
        client.close()

if __name__ == "__main__":
    main()