#!/bin/bash
set -e

echo "🚀 Starting Noon-Scrapper application..."

# Wait for dependencies to be ready

echo "⏳ Waiting for dependencies..."
# --- Add these lines for debugging ---
echo "--- Checking environment variables ---"
echo "MODE is: [$MODE]"
echo "PORT is: [$PORT]"
echo "------------------------------------"

if [ "$MODE" = "DEVELOPMENT" ]; then
    echo "🐛 Starting in DEBUG mode..."
    echo "Debugger will listen on port 5678 - attach VS Code debugger to continue"
    # CORRECTED: Changed to 'main:app' and removed '--workers' and '--reload', which conflict with the debugger.
    exec python -m debugpy \
        --listen 0.0.0.0:5679 \
        -m uvicorn main:app \
        --host 0.0.0.0 \
        --port $PORT \
        --reload

else
    echo "🚀 Starting in PRODUCTION mode..."
    # CORRECTED: Changed to 'main:app'.
    exec uvicorn main:app \
        --host 0.0.0.0 \
        --port $PORT \
        --workers 4 \
        --log-level info
fi
