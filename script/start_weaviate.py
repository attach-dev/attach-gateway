from weaviate.embedded import EmbeddedOptions
import weaviate, threading, time

client = weaviate.Client(embedded_options=EmbeddedOptions())
client.schema.create_class({"class": "MemoryEvent"})
print("✅ Embedded Weaviate up")
while True: time.sleep(3600)