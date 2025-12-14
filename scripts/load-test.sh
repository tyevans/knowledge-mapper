#!/bin/bash
set -euo pipefail

# Knowledge Mapper - Load Testing Script
#
# Wrapper script for running k6 load tests.
#
# Usage:
#   ./scripts/load-test.sh [scenario] [options]
#
# Scenarios:
#   smoke       - Quick validation (1 VU, 1 minute)
#   load        - Normal load test (50 VUs, 5 minutes)
#   stress      - Stress test to find breaking points
#   soak        - Extended duration test (20 VUs, 30 minutes)
#   health      - Health endpoint specific test
#   api         - Public API endpoint test
#   api-auth    - Authenticated API endpoint test
#   rate-limit  - Rate limiting behavior test
#   multi-tenant - Multi-tenant isolation test
#
# Options:
#   --vus N        Override virtual users count
#   --duration T   Override duration (e.g., 5m, 1h)
#   --base-url U   Override base URL
#   --output F     Output results to file
#   --json         Output results as JSON
#   --quiet        Suppress k6 progress output
#   --help         Show this help message
#
# Auth Options (for api-auth, rate-limit, multi-tenant):
#   --token-url U  Override OAuth token endpoint
#   --client-id C  Override OAuth client ID
#   --test-users U Override test users (user:pass,user:pass)
#   --debug        Enable auth debug logging
#
# Examples:
#   ./scripts/load-test.sh smoke
#   ./scripts/load-test.sh load --vus 100 --duration 10m
#   ./scripts/load-test.sh stress --base-url https://staging.example.com
#   ./scripts/load-test.sh api-auth --test-users alice:pass,bob:pass
#   ./scripts/load-test.sh rate-limit --vus 50
#   ./scripts/load-test.sh multi-tenant --debug

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TESTS_DIR="$PROJECT_ROOT/tests/load"
RESULTS_DIR="$PROJECT_ROOT/tests/load/results"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
SCENARIO="${1:-smoke}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
VUS=""
DURATION=""
OUTPUT_FILE=""
JSON_OUTPUT=""
QUIET=""

# Auth-related defaults
TOKEN_URL="${TOKEN_URL:-}"
CLIENT_ID="${CLIENT_ID:-}"
CLIENT_SECRET="${CLIENT_SECRET:-}"
TEST_USERS="${TEST_USERS:-}"
AUTH_DEBUG="${AUTH_DEBUG:-}"

# Show help
show_help() {
    head -45 "$0" | tail -40
    exit 0
}

# Parse arguments
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --vus)
            VUS="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --json)
            JSON_OUTPUT="true"
            shift
            ;;
        --quiet)
            QUIET="true"
            shift
            ;;
        --token-url)
            TOKEN_URL="$2"
            shift 2
            ;;
        --client-id)
            CLIENT_ID="$2"
            shift 2
            ;;
        --client-secret)
            CLIENT_SECRET="$2"
            shift 2
            ;;
        --test-users)
            TEST_USERS="$2"
            shift 2
            ;;
        --debug)
            AUTH_DEBUG="true"
            shift
            ;;
        --help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Check k6 is installed
check_k6() {
    if ! command -v k6 &> /dev/null; then
        echo -e "${RED}Error: k6 is not installed${NC}"
        echo ""
        echo "Install k6:"
        echo "  macOS:   brew install k6"
        echo "  Ubuntu:  sudo gpg -k"
        echo "           sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \\"
        echo "               --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69"
        echo "           echo 'deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main' | \\"
        echo "               sudo tee /etc/apt/sources.list.d/k6.list"
        echo "           sudo apt-get update && sudo apt-get install k6"
        echo "  Docker:  docker run --rm -i grafana/k6 run -"
        echo ""
        echo "See: https://k6.io/docs/get-started/installation/"
        exit 1
    fi
}

# Create results directory
mkdir -p "$RESULTS_DIR"

# Determine test file
get_test_file() {
    case $SCENARIO in
        smoke)
            echo "$TESTS_DIR/scenarios/smoke.js"
            ;;
        load)
            echo "$TESTS_DIR/scenarios/load.js"
            ;;
        stress)
            echo "$TESTS_DIR/scenarios/stress.js"
            ;;
        soak)
            echo "$TESTS_DIR/scenarios/soak.js"
            ;;
        health)
            echo "$TESTS_DIR/scripts/health.js"
            ;;
        api|api-public)
            echo "$TESTS_DIR/scripts/api-public.js"
            ;;
        api-auth|api-authenticated)
            echo "$TESTS_DIR/scripts/api-authenticated.js"
            ;;
        rate-limit|rate-limiting)
            echo "$TESTS_DIR/scripts/rate-limiting.js"
            ;;
        multi-tenant|tenant)
            echo "$TESTS_DIR/scripts/multi-tenant.js"
            ;;
        *)
            # Allow direct file path
            if [[ -f "$SCENARIO" ]]; then
                echo "$SCENARIO"
            elif [[ -f "$TESTS_DIR/$SCENARIO" ]]; then
                echo "$TESTS_DIR/$SCENARIO"
            elif [[ -f "$TESTS_DIR/$SCENARIO.js" ]]; then
                echo "$TESTS_DIR/$SCENARIO.js"
            else
                echo ""
            fi
            ;;
    esac
}

# Main execution
main() {
    check_k6

    TEST_FILE=$(get_test_file)

    if [[ -z "$TEST_FILE" ]] || [[ ! -f "$TEST_FILE" ]]; then
        echo -e "${RED}Unknown scenario: $SCENARIO${NC}"
        echo ""
        echo "Available scenarios:"
        echo "  smoke        - Quick validation (1 VU, 1 minute)"
        echo "  load         - Normal load test (50 VUs, 5 minutes)"
        echo "  stress       - Stress test to find breaking points"
        echo "  soak         - Extended duration test (20 VUs, 30 minutes)"
        echo "  health       - Health endpoint specific test"
        echo "  api          - Public API endpoint test"
        echo "  api-auth     - Authenticated API endpoint test"
        echo "  rate-limit   - Rate limiting behavior test"
        echo "  multi-tenant - Multi-tenant isolation test"
        echo ""
        echo "Or provide a path to a test file."
        exit 1
    fi

    # Build k6 command
    K6_CMD="k6 run"
    K6_ENV=""

    # Add environment variables
    K6_ENV="$K6_ENV --env BASE_URL=$BASE_URL"
    [[ -n "$VUS" ]] && K6_ENV="$K6_ENV --env VUS=$VUS"
    [[ -n "$DURATION" ]] && K6_ENV="$K6_ENV --env DURATION=$DURATION"

    # Add auth-related environment variables
    [[ -n "$TOKEN_URL" ]] && K6_ENV="$K6_ENV --env TOKEN_URL=$TOKEN_URL"
    [[ -n "$CLIENT_ID" ]] && K6_ENV="$K6_ENV --env CLIENT_ID=$CLIENT_ID"
    [[ -n "$CLIENT_SECRET" ]] && K6_ENV="$K6_ENV --env CLIENT_SECRET=$CLIENT_SECRET"
    [[ -n "$TEST_USERS" ]] && K6_ENV="$K6_ENV --env TEST_USERS=$TEST_USERS"
    [[ -n "$AUTH_DEBUG" ]] && K6_ENV="$K6_ENV --env AUTH_DEBUG=$AUTH_DEBUG"

    # Add output options
    if [[ -n "$OUTPUT_FILE" ]]; then
        K6_CMD="$K6_CMD --out json=$RESULTS_DIR/$OUTPUT_FILE"
    fi

    if [[ -n "$JSON_OUTPUT" ]]; then
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        K6_CMD="$K6_CMD --out json=$RESULTS_DIR/${SCENARIO}_${TIMESTAMP}.json"
    fi

    if [[ -n "$QUIET" ]]; then
        K6_CMD="$K6_CMD --quiet"
    fi

    echo -e "${BLUE}=== Knowledge Mapper Load Testing ===${NC}"
    echo ""
    echo -e "${YELLOW}Scenario:${NC}  $SCENARIO"
    echo -e "${YELLOW}Test File:${NC} $TEST_FILE"
    echo -e "${YELLOW}Base URL:${NC}  $BASE_URL"
    [[ -n "$VUS" ]] && echo -e "${YELLOW}VUs:${NC}       $VUS"
    [[ -n "$DURATION" ]] && echo -e "${YELLOW}Duration:${NC}  $DURATION"

    # Show auth info for auth-related tests
    if [[ "$SCENARIO" =~ ^(api-auth|api-authenticated|rate-limit|rate-limiting|multi-tenant|tenant)$ ]]; then
        echo ""
        echo -e "${BLUE}=== Auth Configuration ===${NC}"
        [[ -n "$TOKEN_URL" ]] && echo -e "${YELLOW}Token URL:${NC}  $TOKEN_URL" || echo -e "${YELLOW}Token URL:${NC}  (default)"
        [[ -n "$CLIENT_ID" ]] && echo -e "${YELLOW}Client ID:${NC}  $CLIENT_ID" || echo -e "${YELLOW}Client ID:${NC}  (default)"
        [[ -n "$TEST_USERS" ]] && echo -e "${YELLOW}Test Users:${NC} $TEST_USERS" || echo -e "${YELLOW}Test Users:${NC} (default: alice, bob)"
        [[ -n "$AUTH_DEBUG" ]] && echo -e "${YELLOW}Debug:${NC}      enabled"
    fi
    echo ""

    # Run the test
    echo -e "${GREEN}Starting test...${NC}"
    echo ""

    # Execute k6
    cd "$TESTS_DIR"
    $K6_CMD $K6_ENV "$TEST_FILE"
    EXIT_CODE=$?

    echo ""
    if [[ $EXIT_CODE -eq 0 ]]; then
        echo -e "${GREEN}Test complete.${NC}"
    else
        echo -e "${RED}Test failed with exit code: $EXIT_CODE${NC}"
    fi

    # Show results location if output was specified
    if [[ -n "$OUTPUT_FILE" ]]; then
        echo -e "Results saved to: ${BLUE}$RESULTS_DIR/$OUTPUT_FILE${NC}"
    fi

    if [[ -n "$JSON_OUTPUT" ]]; then
        echo -e "JSON results saved to: ${BLUE}$RESULTS_DIR/${NC}"
    fi

    exit $EXIT_CODE
}

main
