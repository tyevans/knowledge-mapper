#!/bin/sh
# Docker entrypoint for frontend development container
# Ensures node_modules are installed before starting the dev server

set -e

CHECKSUM_FILE="node_modules/.package-checksum"

# Calculate package.json checksum
current_checksum=$(md5sum package.json | cut -d' ' -f1)

# Check if node_modules needs to be installed/updated
needs_install=false

if [ ! -d "node_modules" ] || [ ! -d "node_modules/.bin" ]; then
    echo "node_modules missing or empty"
    needs_install=true
elif [ ! -f "node_modules/.package-lock.json" ]; then
    echo "node_modules may be corrupted (no .package-lock.json)"
    needs_install=true
elif [ ! -f "$CHECKSUM_FILE" ]; then
    echo "No package checksum found, dependencies may be stale"
    needs_install=true
elif [ "$(cat $CHECKSUM_FILE)" != "$current_checksum" ]; then
    echo "package.json has changed since last install"
    needs_install=true
fi

if [ "$needs_install" = true ]; then
    echo "Running npm install..."
    npm install
    echo "$current_checksum" > "$CHECKSUM_FILE"
    echo "Dependencies installed successfully"
fi

# Execute the command passed to docker run
exec "$@"
