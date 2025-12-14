#!/bin/bash
set -e

# Keycloak Realm Export Script
# Exports the knowledge-mapper-dev realm with clients and configuration

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "=== Keycloak Realm Export ==="
echo "Getting admin token..."

# Get admin token
TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    -d "client_id=admin-cli" \
    -d "username=$ADMIN_USER" \
    -d "password=$ADMIN_PASS" \
    -d "grant_type=password" | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
    echo "Failed to get admin token"
    exit 1
fi

echo "Exporting realm knowledge-mapper-dev (partial export with clients and users)..."

# Use partial export endpoint to include clients and users
curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/partial-export?exportClients=true&exportGroupsAndRoles=true" \
    | jq '.' > "$SCRIPT_DIR/realm-export.json"

if [ $? -eq 0 ]; then
    echo "✓ Realm exported to keycloak/realm-export.json"
    echo ""
    echo "Export includes:"
    jq -r '{realm: .realm, clients: [.clients // [] | .[] | .clientId], usersCount: (.users // [] | length)}' "$SCRIPT_DIR/realm-export.json"
else
    echo "✗ Export failed"
    exit 1
fi
