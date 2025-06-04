import weaviate
import time

print("Starting Weaviate...")
client = weaviate.connect_to_embedded(
    version="1.29.8",
    hostname="localhost",
    port=6666,
    grpc_port=6667,
    environment_variables={
        "WEAVIATE_DISABLE_CLUSTER": "true",
        "WEAVIATE_CLUSTER_ENABLED": "false",
        "WEAVIATE_CLUSTER_HOSTNAME": "localhost",
        "WEAVIATE_CLUSTER_JOIN": "",
        "WEAVIATE_CLUSTER_BIND_PORT": "0",
        "WEAVIATE_CLUSTER_GOSSIP_BIND_PORT": "0",
        "QUOTA_MAX_DISK_USAGE_PERCENT": "95",
        "WEAVIATE_DISABLE_TELEMETRY": "true",
        "WEAVIATE_DISABLE_GRAPHQL": "false",
        "WEAVIATE_DISABLE_REST": "false",
        "WEAVIATE_DISABLE_GRPC": "true",
        "ENABLE_MODULES": "",
        "BACKUP_FILESYSTEM_PATH": "/tmp/backups"
    }
)

print(f"✅ Weaviate is running at {client.url}")

try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    print("\nShutting down Weaviate...")
finally:
    client.close()