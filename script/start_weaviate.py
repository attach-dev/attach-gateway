from weaviate.embedded import EmbeddedOptions
import weaviate, time

client = weaviate.Client(embedded_options=EmbeddedOptions())
try:
    client.schema.create_class({
        "class": "MemoryEvent"
        # ... other class properties
    })
except weaviate.exceptions.UnexpectedStatusCodeException as e:
    if "already exists" in str(e):
        print("MemoryEvent class already exists, skipping creation")
    else:
        raise
print("✅ Embedded Weaviate up")
while True: time.sleep(3600)