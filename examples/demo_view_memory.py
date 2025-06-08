"""
Print the 10 latest MemoryEvent objects using Weaviate *v3* REST client.
Run with a Docker-based server started like:
  docker run -p 6666:8080 semitechnologies/weaviate:1.30.5
"""

import json

import weaviate

# We expose 8080 inside the container – forwarded to 6666 on the host
client = weaviate.Client("http://localhost:6666")

classes = {c["class"] for c in client.schema.get().get("classes", [])}
if "MemoryEvent" not in classes:
    print("⚠️  No MemoryEvent class yet (run a chat first)")
    exit(0)

# Fetch the last 10 events, newest first
result = (
    client.query.get("MemoryEvent", ["timestamp", "role", "content"])
    .with_additional(["id"])
    .with_limit(10)
    .do()
)

if "errors" in result:
    print("GraphQL error:", result["errors"])
    exit(1)
if "data" not in result:
    print("No data in response:", result)
    exit(1)

objs = result["data"]["Get"]["MemoryEvent"]
print(f"Fetched {len(objs)} events\n")
for o in objs:
    print(json.dumps(o, indent=2)[:600], "...\n")

objs = client.data_object.get(class_name="MemoryEvent", limit=1)
print(objs)