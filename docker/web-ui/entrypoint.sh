#!/bin/bash
set -e

echo "Waiting for agent-runtime API..."
# Poll the health endpoint rather than just TCP — ensures the app is fully
# initialised (migrations complete, routes registered) before we start serving.
until curl -sf http://agent-runtime:8000/health > /dev/null 2>&1; do
    sleep 2
done
echo "API ready."

echo "Starting web-ui..."
exec node server.js
