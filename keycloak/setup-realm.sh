#!/bin/bash
set -e

# Keycloak Realm Setup Script for Knowledge Mapper
# This script creates the knowledge-mapper-dev realm with OAuth clients and test users

KEYCLOAK_URL="${KEYCLOAK_URL:-http://keycloak.localtest.me:8080}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASS="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Keycloak Realm Setup ===${NC}"
echo "Keycloak URL: $KEYCLOAK_URL"
echo ""

# Function to get admin token
get_admin_token() {
    echo -e "${YELLOW}Getting admin access token...${NC}"
    TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
        -d "client_id=admin-cli" \
        -d "username=$ADMIN_USER" \
        -d "password=$ADMIN_PASS" \
        -d "grant_type=password" | jq -r '.access_token')

    if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
        echo -e "${RED}Failed to get admin token. Check Keycloak credentials.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Admin token obtained${NC}"
}

# Function to check if realm exists
realm_exists() {
    REALM_CHECK=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev")

    if [ "$REALM_CHECK" == "200" ]; then
        return 0
    else
        return 1
    fi
}

# Function to create realm
create_realm() {
    echo -e "${YELLOW}Creating knowledge-mapper-dev realm...${NC}"

    REALM_JSON='{
        "realm": "knowledge-mapper-dev",
        "displayName": "Knowledge Mapper (Development)",
        "enabled": true,
        "sslRequired": "none",
        "registrationAllowed": false,
        "loginWithEmailAllowed": true,
        "duplicateEmailsAllowed": false,
        "resetPasswordAllowed": false,
        "editUsernameAllowed": false,
        "bruteForceProtected": true,
        "rememberMe": true,
        "verifyEmail": false,
        "accessTokenLifespan": 300,
        "accessTokenLifespanForImplicitFlow": 900,
        "ssoSessionIdleTimeout": 1800,
        "ssoSessionMaxLifespan": 36000,
        "offlineSessionIdleTimeout": 2592000
    }'

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$REALM_JSON" \
        "$KEYCLOAK_URL/admin/realms")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}✓ Realm created successfully${NC}"
    else
        echo -e "${RED}Failed to create realm (HTTP $HTTP_CODE)${NC}"
        exit 1
    fi
}

# Function to create backend client
create_backend_client() {
    echo -e "${YELLOW}Creating knowledge-mapper-backend client...${NC}"

    CLIENT_JSON='{
        "clientId": "knowledge-mapper-backend",
        "name": "Knowledge Mapper Backend Service",
        "description": "Confidential client for backend API",
        "enabled": true,
        "protocol": "openid-connect",
        "publicClient": false,
        "secret": "knowledge-mapper-backend-secret",
        "standardFlowEnabled": true,
        "implicitFlowEnabled": false,
        "directAccessGrantsEnabled": true,
        "serviceAccountsEnabled": true,
        "redirectUris": [
            "http://localhost:8000/*",
            "http://localhost:8000/api/v1/auth/callback",
            "http://127.0.0.1:8000/*"
        ],
        "webOrigins": [
            "http://localhost:8000",
            "http://127.0.0.1:8000"
        ],
        "attributes": {
            "access.token.lifespan": "900"
        },
        "protocolMappers": [
            {
                "name": "tenant-id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": false,
                "config": {
                    "userinfo.token.claim": "true",
                    "user.attribute": "tenant_id",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "claim.name": "tenant_id",
                    "jsonType.label": "String",
                    "aggregate.attrs": "false",
                    "multivalued": "false"
                }
            },
            {
                "name": "custom-scopes",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": false,
                "config": {
                    "userinfo.token.claim": "true",
                    "user.attribute": "custom_scopes",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "claim.name": "custom_scopes",
                    "jsonType.label": "String",
                    "aggregate.attrs": "false",
                    "multivalued": "false"
                }
            },
            {
                "name": "audience-mapper",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": false,
                "config": {
                    "included.client.audience": "knowledge-mapper-backend",
                    "id.token.claim": "false",
                    "access.token.claim": "true"
                }
            }
        ]
    }'

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$CLIENT_JSON" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/clients")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}✓ Backend client created${NC}"
    else
        echo -e "${RED}Failed to create backend client (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to create frontend client
create_frontend_client() {
    echo -e "${YELLOW}Creating knowledge-mapper-frontend client...${NC}"

    CLIENT_JSON='{
        "clientId": "knowledge-mapper-frontend",
        "name": "Knowledge Mapper Frontend Application",
        "description": "Public client for frontend with PKCE",
        "enabled": true,
        "protocol": "openid-connect",
        "publicClient": true,
        "standardFlowEnabled": true,
        "implicitFlowEnabled": false,
        "directAccessGrantsEnabled": false,
        "serviceAccountsEnabled": false,
        "redirectUris": [
            "http://localhost:5173/*",
            "http://localhost:5173/auth/callback",
            "http://127.0.0.1:5173/*"
        ],
        "webOrigins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173"
        ],
        "attributes": {
            "pkce.code.challenge.method": "S256"
        },
        "protocolMappers": [
            {
                "name": "tenant-id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": false,
                "config": {
                    "userinfo.token.claim": "true",
                    "user.attribute": "tenant_id",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "claim.name": "tenant_id",
                    "jsonType.label": "String",
                    "aggregate.attrs": "false",
                    "multivalued": "false"
                }
            },
            {
                "name": "custom-scopes",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "consentRequired": false,
                "config": {
                    "userinfo.token.claim": "true",
                    "user.attribute": "custom_scopes",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "claim.name": "custom_scopes",
                    "jsonType.label": "String",
                    "aggregate.attrs": "false",
                    "multivalued": "false"
                }
            },
            {
                "name": "audience-mapper",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": false,
                "config": {
                    "included.client.audience": "knowledge-mapper-backend",
                    "id.token.claim": "false",
                    "access.token.claim": "true"
                }
            }
        ]
    }'

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$CLIENT_JSON" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/clients")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}✓ Frontend client created${NC}"
    else
        echo -e "${RED}Failed to create frontend client (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to create user
create_user() {
    local USERNAME=$1
    local EMAIL=$2
    local FIRSTNAME=$3
    local LASTNAME=$4
    local TENANT_ID=$5

    echo -e "${YELLOW}Creating user: $USERNAME...${NC}"

    USER_JSON=$(cat <<EOF
{
    "username": "$USERNAME",
    "email": "$EMAIL",
    "emailVerified": true,
    "firstName": "$FIRSTNAME",
    "lastName": "$LASTNAME",
    "enabled": true,
    "attributes": {
        "tenant_id": ["$TENANT_ID"]
    },
    "credentials": [
        {
            "type": "password",
            "value": "password123",
            "temporary": false
        }
    ]
}
EOF
)

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$USER_JSON" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/users")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}✓ User $USERNAME created${NC}"
    else
        echo -e "${YELLOW}⚠ User $USERNAME may already exist or failed (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to get user UUID
get_user_uuid() {
    local USERNAME=$1

    USER_UUID=$(curl -s \
        -H "Authorization: Bearer $TOKEN" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/users?username=$USERNAME&exact=true" | jq -r '.[0].id')

    echo "$USER_UUID"
}

# Function to create a realm role
create_realm_role() {
    local ROLE_NAME=$1
    local ROLE_DESCRIPTION=$2

    echo -e "${YELLOW}Creating role: $ROLE_NAME...${NC}"

    ROLE_JSON=$(cat <<EOF
{
    "name": "$ROLE_NAME",
    "description": "$ROLE_DESCRIPTION"
}
EOF
)

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$ROLE_JSON" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/roles")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}+ Role $ROLE_NAME created${NC}"
    elif [ "$HTTP_CODE" == "409" ]; then
        echo -e "${YELLOW}! Role $ROLE_NAME already exists${NC}"
    else
        echo -e "${RED}Failed to create role $ROLE_NAME (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to configure User Profile with custom attributes
# This is required in Keycloak 26+ where User Profile is enabled by default
# Custom attributes like tenant_id must be defined in the User Profile
# before they can be set on users via the API
configure_user_profile() {
    echo -e "${YELLOW}Configuring User Profile with custom attributes...${NC}"

    # Get current user profile to preserve default attributes
    CURRENT_PROFILE=$(curl -s \
        -H "Authorization: Bearer $TOKEN" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/users/profile")

    # Build updated profile with tenant_id and custom_scopes attributes
    # We need to add our custom attributes to the existing ones
    UPDATED_PROFILE=$(cat <<'PROFILE_EOF'
{
    "attributes": [
        {
            "name": "username",
            "displayName": "${username}",
            "validations": {
                "length": { "min": 3, "max": 255 },
                "username-prohibited-characters": {},
                "up-username-not-idn-homograph": {}
            },
            "permissions": {
                "view": ["admin", "user"],
                "edit": ["admin", "user"]
            },
            "multivalued": false
        },
        {
            "name": "email",
            "displayName": "${email}",
            "validations": {
                "email": {},
                "length": { "max": 255 }
            },
            "required": { "roles": ["user"] },
            "permissions": {
                "view": ["admin", "user"],
                "edit": ["admin", "user"]
            },
            "multivalued": false
        },
        {
            "name": "firstName",
            "displayName": "${firstName}",
            "validations": {
                "length": { "max": 255 },
                "person-name-prohibited-characters": {}
            },
            "required": { "roles": ["user"] },
            "permissions": {
                "view": ["admin", "user"],
                "edit": ["admin", "user"]
            },
            "multivalued": false
        },
        {
            "name": "lastName",
            "displayName": "${lastName}",
            "validations": {
                "length": { "max": 255 },
                "person-name-prohibited-characters": {}
            },
            "required": { "roles": ["user"] },
            "permissions": {
                "view": ["admin", "user"],
                "edit": ["admin", "user"]
            },
            "multivalued": false
        },
        {
            "name": "tenant_id",
            "displayName": "Tenant ID",
            "validations": {
                "length": { "min": 36, "max": 36 }
            },
            "required": {},
            "permissions": {
                "view": ["admin"],
                "edit": ["admin"]
            },
            "multivalued": false,
            "annotations": {
                "inputType": "text"
            }
        },
        {
            "name": "custom_scopes",
            "displayName": "Custom Scopes",
            "validations": {
                "length": { "max": 1024 }
            },
            "permissions": {
                "view": ["admin"],
                "edit": ["admin"]
            },
            "multivalued": false,
            "annotations": {
                "inputType": "text"
            }
        }
    ],
    "groups": [
        {
            "name": "user-metadata",
            "displayHeader": "User metadata",
            "displayDescription": "Attributes, which refer to user metadata"
        }
    ]
}
PROFILE_EOF
)

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X PUT \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$UPDATED_PROFILE" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/users/profile")

    if [ "$HTTP_CODE" == "200" ]; then
        echo -e "${GREEN}✓ User Profile configured with tenant_id and custom_scopes${NC}"
    else
        echo -e "${RED}Failed to configure User Profile (HTTP $HTTP_CODE)${NC}"
        exit 1
    fi
}

# Function to add custom scopes protocol mapper to a client
add_custom_scopes_mapper() {
    local CLIENT_ID=$1

    echo -e "${YELLOW}Adding custom scopes mapper to $CLIENT_ID...${NC}"

    # Get client UUID
    CLIENT_UUID=$(curl -s \
        -H "Authorization: Bearer $TOKEN" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/clients?clientId=$CLIENT_ID" | jq -r '.[0].id')

    if [ "$CLIENT_UUID" == "null" ] || [ -z "$CLIENT_UUID" ]; then
        echo -e "${RED}Cannot find client $CLIENT_ID${NC}"
        return 1
    fi

    # Add protocol mapper for custom_scopes attribute
    MAPPER_JSON=$(cat <<EOF
{
    "name": "custom-scopes-mapper",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-usermodel-attribute-mapper",
    "consentRequired": false,
    "config": {
        "userinfo.token.claim": "true",
        "user.attribute": "custom_scopes",
        "id.token.claim": "true",
        "access.token.claim": "true",
        "claim.name": "custom_scopes",
        "jsonType.label": "String",
        "aggregate.attrs": "true",
        "multivalued": "false"
    }
}
EOF
)

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$MAPPER_JSON" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/clients/$CLIENT_UUID/protocol-mappers/models")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}+ Custom scopes mapper added to $CLIENT_ID${NC}"
    elif [ "$HTTP_CODE" == "409" ]; then
        echo -e "${YELLOW}! Mapper already exists on $CLIENT_ID${NC}"
    else
        echo -e "${RED}Failed to add mapper to $CLIENT_ID (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to create platform admin user with tenant management scopes
create_platform_admin_user() {
    local USERNAME=$1
    local EMAIL=$2
    local PASSWORD=$3
    local FIRSTNAME=$4
    local LASTNAME=$5
    local SCOPES=$6

    echo -e "${YELLOW}Creating platform admin user: $USERNAME...${NC}"

    USER_JSON=$(cat <<EOF
{
    "username": "$USERNAME",
    "email": "$EMAIL",
    "emailVerified": true,
    "firstName": "$FIRSTNAME",
    "lastName": "$LASTNAME",
    "enabled": true,
    "attributes": {
        "tenant_id": ["00000000-0000-0000-0000-000000000000"],
        "custom_scopes": ["$SCOPES"]
    },
    "credentials": [
        {
            "type": "password",
            "value": "$PASSWORD",
            "temporary": false
        }
    ]
}
EOF
)

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$USER_JSON" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/users")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}+ Platform admin user $USERNAME created${NC}"
    elif [ "$HTTP_CODE" == "409" ]; then
        echo -e "${YELLOW}! User $USERNAME already exists${NC}"
    else
        echo -e "${RED}Failed to create user $USERNAME (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to create a test user with specific password
create_test_user() {
    local USERNAME=$1
    local EMAIL=$2
    local PASSWORD=$3
    local FIRSTNAME=$4
    local LASTNAME=$5
    local TENANT_ID=${6:-"33333333-3333-3333-3333-333333333333"}  # Default tenant for test users

    echo -e "${YELLOW}Creating test user: $USERNAME...${NC}"

    USER_JSON=$(cat <<EOF
{
    "username": "$USERNAME",
    "email": "$EMAIL",
    "emailVerified": true,
    "firstName": "$FIRSTNAME",
    "lastName": "$LASTNAME",
    "enabled": true,
    "attributes": {
        "tenant_id": ["$TENANT_ID"]
    },
    "credentials": [
        {
            "type": "password",
            "value": "$PASSWORD",
            "temporary": false
        }
    ]
}
EOF
)

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$USER_JSON" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/users")

    if [ "$HTTP_CODE" == "201" ]; then
        echo -e "${GREEN}+ User $USERNAME created${NC}"
    elif [ "$HTTP_CODE" == "409" ]; then
        echo -e "${YELLOW}! User $USERNAME already exists${NC}"
    else
        echo -e "${RED}Failed to create user $USERNAME (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to assign realm role to user
assign_role_to_user() {
    local USERNAME=$1
    local ROLE_NAME=$2

    # Get user UUID
    local USER_UUID=$(get_user_uuid "$USERNAME")

    if [ "$USER_UUID" == "null" ] || [ -z "$USER_UUID" ]; then
        echo -e "${RED}Cannot find user $USERNAME to assign role${NC}"
        return 1
    fi

    # Get role representation
    local ROLE_JSON=$(curl -s \
        -H "Authorization: Bearer $TOKEN" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/roles/$ROLE_NAME")

    if [ -z "$ROLE_JSON" ] || [ "$(echo "$ROLE_JSON" | jq -r '.name')" == "null" ]; then
        echo -e "${RED}Cannot find role $ROLE_NAME${NC}"
        return 1
    fi

    # Assign role to user
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "[$ROLE_JSON]" \
        "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev/users/$USER_UUID/role-mappings/realm")

    if [ "$HTTP_CODE" == "204" ]; then
        echo -e "${GREEN}+ Assigned role $ROLE_NAME to $USERNAME${NC}"
    else
        echo -e "${YELLOW}! Role assignment may have failed for $USERNAME -> $ROLE_NAME (HTTP $HTTP_CODE)${NC}"
    fi
}

# Function to create Playwright API test users
# These users match the definitions in playwright/tests/test-users.ts
create_playwright_test_users() {
    echo ""
    echo -e "${GREEN}=== Creating Playwright API Test Users ===${NC}"
    echo -e "${YELLOW}Note: These users are defined in playwright/tests/test-users.ts${NC}"
    echo ""

    # Create realm roles first
    echo -e "${GREEN}--- Creating Realm Roles ---${NC}"
    create_realm_role "user" "Standard user role"
    create_realm_role "admin" "Administrator role with full access"
    create_realm_role "readonly" "Read-only access role"
    create_realm_role "manager" "Manager role with elevated permissions"
    create_realm_role "service" "Service account role for API-to-API communication"
    echo ""

    # Create test users
    echo -e "${GREEN}--- Creating Test Users ---${NC}"

    # admin / admin123 (roles: user, admin)
    create_test_user "admin" "admin@example.com" "admin123" "Admin" "User"

    # testuser / test123 (roles: user)
    create_test_user "testuser" "test@example.com" "test123" "Test" "User"

    # readonly / readonly123 (roles: user, readonly)
    create_test_user "readonly" "readonly@example.com" "readonly123" "Readonly" "User"

    # newuser / newuser123 (roles: user)
    create_test_user "newuser" "newuser@example.com" "newuser123" "New" "User"

    # manager / manager123 (roles: user, manager)
    create_test_user "manager" "manager@example.com" "manager123" "Manager" "User"

    # service-account / service123 (roles: service)
    create_test_user "service-account" "service@example.com" "service123" "Service" "Account"

    echo ""

    # Assign roles to users
    echo -e "${GREEN}--- Assigning Roles to Users ---${NC}"

    # admin: user, admin
    assign_role_to_user "admin" "user"
    assign_role_to_user "admin" "admin"

    # testuser: user
    assign_role_to_user "testuser" "user"

    # readonly: user, readonly
    assign_role_to_user "readonly" "user"
    assign_role_to_user "readonly" "readonly"

    # newuser: user
    assign_role_to_user "newuser" "user"

    # manager: user, manager
    assign_role_to_user "manager" "user"
    assign_role_to_user "manager" "manager"

    # service-account: service (note: does NOT have 'user' role)
    assign_role_to_user "service-account" "service"

    echo ""
    echo -e "${GREEN}=== Playwright API Test Users Created ===${NC}"
    echo "Users created with matching credentials from test-users.ts:"
    echo "  - admin / admin123 (roles: user, admin)"
    echo "  - testuser / test123 (roles: user)"
    echo "  - readonly / readonly123 (roles: user, readonly)"
    echo "  - newuser / newuser123 (roles: user)"
    echo "  - manager / manager123 (roles: user, manager)"
    echo "  - service-account / service123 (roles: service)"
}

# Main execution
main() {
    get_admin_token

    if realm_exists; then
        echo -e "${YELLOW}⚠ Realm knowledge-mapper-dev already exists${NC}"
        read -p "Do you want to recreate it? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${YELLOW}Deleting existing realm...${NC}"
            curl -s -X DELETE \
                -H "Authorization: Bearer $TOKEN" \
                "$KEYCLOAK_URL/admin/realms/knowledge-mapper-dev"
            echo -e "${GREEN}✓ Realm deleted${NC}"
        else
            echo "Skipping realm creation"
            exit 0
        fi
    fi

    create_realm
    create_backend_client
    create_frontend_client

    echo ""
    echo -e "${GREEN}=== Configuring User Profile ===${NC}"
    configure_user_profile

    echo ""
    echo -e "${GREEN}=== Creating Platform Admin User ===${NC}"
    # Create platform admin with tenant management scopes
    # tenant_id is set to a special "platform" UUID (all zeros)
    create_platform_admin_user "platform-admin" "platform-admin@example.com" "admin123" "Platform" "Administrator" "openid profile email tenants/read tenants/manage tenants/stores admin consolidation/read consolidation/write consolidation/admin"

    echo ""
    echo -e "${GREEN}=== Creating Test Users ===${NC}"

    # Tenant: acme-corp
    create_user "alice@example.com" "alice@example.com" "Alice" "Admin" "11111111-1111-1111-1111-111111111111"
    create_user "bob@example.com" "bob@example.com" "Bob" "User" "11111111-1111-1111-1111-111111111111"

    # Tenant: demo-org
    create_user "charlie@demo.example" "charlie@demo.example" "Charlie" "Manager" "22222222-2222-2222-2222-222222222222"
    create_user "diana@demo.example" "diana@demo.example" "Diana" "Developer" "22222222-2222-2222-2222-222222222222"

    # Create Playwright API test users (from playwright/tests/test-users.ts)
    create_playwright_test_users

    echo ""
    echo -e "${GREEN}=== Extracting User UUIDs ===${NC}"

    ALICE_UUID=$(get_user_uuid "alice@example.com")
    BOB_UUID=$(get_user_uuid "bob@example.com")
    CHARLIE_UUID=$(get_user_uuid "charlie@demo.example")
    DIANA_UUID=$(get_user_uuid "diana@demo.example")

    echo ""
    echo -e "${GREEN}=== User UUIDs for Database Seeding ===${NC}"
    echo "alice@example.com:     $ALICE_UUID"
    echo "bob@example.com:       $BOB_UUID"
    echo "charlie@demo.example:  $CHARLIE_UUID"
    echo "diana@demo.example:    $DIANA_UUID"

    # Save UUIDs to file
    cat > /tmp/keycloak-user-uuids.txt <<EOF
# Keycloak User UUIDs for Knowledge Mapper
# Generated: $(date)
# Use these UUIDs in database seeding for oauth_subject field

alice@example.com=$ALICE_UUID
bob@example.com=$BOB_UUID
charlie@demo.example=$CHARLIE_UUID
diana@demo.example=$DIANA_UUID
EOF

    echo ""
    echo -e "${GREEN}✓ User UUIDs saved to /tmp/keycloak-user-uuids.txt${NC}"

    echo ""
    echo -e "${GREEN}=== Setup Complete ===${NC}"
    echo -e "Realm: ${GREEN}knowledge-mapper-dev${NC}"
    echo -e "Admin Console: ${GREEN}http://localhost:8080/admin/master/console/#/knowledge-mapper-dev${NC}"
    echo -e "OIDC Discovery: ${GREEN}http://localhost:8080/realms/knowledge-mapper-dev/.well-known/openid-configuration${NC}"
    echo ""
    echo -e "${YELLOW}Demo users (multi-tenant):${NC}"
    echo -e "  Username: alice@example.com"
    echo -e "  Password: password123"
    echo ""
    echo -e "${YELLOW}Platform Admin (for tenant management):${NC}"
    echo -e "  Username: platform-admin"
    echo -e "  Email: platform-admin@example.com"
    echo -e "  Password: admin123"
    echo -e "  Scopes: tenants/read tenants/manage tenants/stores admin consolidation/*"
    echo ""
    echo -e "${YELLOW}Playwright API test users (see playwright/tests/test-users.ts):${NC}"
    echo -e "  admin / admin123       (roles: user, admin)"
    echo -e "  testuser / test123     (roles: user)"
    echo -e "  readonly / readonly123 (roles: user, readonly)"
    echo -e "  newuser / newuser123   (roles: user)"
    echo -e "  manager / manager123   (roles: user, manager)"
    echo -e "  service-account / service123 (roles: service)"
}

main
