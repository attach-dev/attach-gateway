from __future__ import annotations

import os
import subprocess
import time


def main() -> None:
    image = os.getenv("WEAVIATE_IMAGE", "semitechnologies/weaviate:1.30.5")
    print("Starting Weaviate via Docker...")
    cmd = [
        "docker",
        "run",
        "--rm",
        "-p",
        "6666:8080",
        "-e",
        "QUERY_DEFAULTS_LIMIT=25",
        "-e",
        "AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true",
        "-e",
        "PERSISTENCE_DATA_PATH=/var/lib/weaviate",
        "-e",
        "DEFAULT_VECTORIZER_MODULE=none",
        "-e",
        "CLUSTER_HOSTNAME=node1",
        image,
    ]

    proc = subprocess.Popen(cmd)
    print("✅ Weaviate Docker container started")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nShutting down Weaviate...")
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
