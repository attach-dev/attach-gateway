import json
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

# Connect to Weaviate running in Docker
client = WeaviateClient(
    connection_params=ConnectionParams.from_url(
        url="http://localhost:8080",  # Default Docker port
        grpc_port=50051              # Default gRPC port
    )
)

# Explicitly connect to the client
client.connect()

# Check if the collection exists
if "MemoryEvent" not in client.collections.list_all():
    print("⚠️  No MemoryEvent collection yet (run a chat first)")
    exit(0)

# Get the collection
coll = client.collections.get("MemoryEvent")

# Fetch the 10 most-recent objects
objs = coll.query.fetch_objects(
    limit=10,
    sort=coll.sort.by_property("timestamp", asc=False)
)

print(f"last {len(objs)} memory events")
for o in objs:
    print(json.dumps(o.properties, indent=2)[:600], "...\n")

# Clean up
client.close()