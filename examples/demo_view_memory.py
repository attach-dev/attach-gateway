"""
Print the 10 latest MemoryEvent objects using Weaviate *v3* REST client.
Run with a Docker-based server started like:
  docker run -p 6666:8080 semitechnologies/weaviate:1.30.5
"""

import json

import weaviate

# We expose 8080 inside the container – forwarded to 6666 on the host
client = weaviate.Client("http://localhost:6666")

# Make sure the class exists (user has chatted once)
if not client.schema.contains({"class": "MemoryEvent"}):
    print("⚠️  No MemoryEvent class yet.  Send a chat first.")
    exit(0)

# Fetch the last 10 events, newest first
result = (
    client.query.get("MemoryEvent", ["id", "timestamp", "role", "content"])
    .with_additional(["id"])
    .with_limit(10)
    .with_near_text({"concepts": ["*"]})  # noop, preserves creation order
    .do()
)

objs = result["data"]["Get"]["MemoryEvent"]
print(f"Fetched {len(objs)} events\n")
for o in objs:
    print(json.dumps(o, indent=2)[:600], "...\n")

client.close()
