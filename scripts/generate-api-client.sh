#!/usr/bin/env bash
# Knowledge Mapper - OpenAPI TypeScript Client Generator
#
# Generates TypeScript API client from backend OpenAPI schema.
#
# Usage:
#   ./scripts/generate-api-client.sh [options]
#
# Options:
#   --from-url    Fetch OpenAPI spec from running backend (default)
#   --from-file   Use local openapi.json file
#   --validate    Validate spec only, don't generate
#   --dry-run     Show what would be generated
#   --help        Show this help message
#
# Prerequisites:
#   - Node.js 18+ (for openapi-generator-cli)
#   - Java 11+ (for generator execution)
#   - Backend running (for --from-url)
#
# Examples:
#   ./scripts/generate-api-client.sh                 # Fetch spec and generate
#   ./scripts/generate-api-client.sh --from-file    # Use existing spec file
#   ./scripts/generate-api-client.sh --validate     # Validate spec only

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
OPENAPI_SPEC_PATH="$PROJECT_ROOT/backend/openapi.json"
HEALTH_ENDPOINT="/api/v1/health"
OPENAPI_ENDPOINT="/openapi.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default options
FROM_URL=true
VALIDATE_ONLY=false
DRY_RUN=false

# Print functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show help
show_help() {
    cat << 'EOF'
Knowledge Mapper - OpenAPI TypeScript Client Generator

USAGE:
    ./scripts/generate-api-client.sh [OPTIONS]

OPTIONS:
    --from-url    Fetch OpenAPI spec from running backend (default)
    --from-file   Use existing local openapi.json file
    --validate    Validate spec only, don't generate client
    --dry-run     Show what would be generated without making changes
    --help        Show this help message

ENVIRONMENT VARIABLES:
    BACKEND_URL   Override backend URL (default: http://localhost:8000)

PREREQUISITES:
    - Node.js 18+ (for openapi-generator-cli npm wrapper)
    - Java 11+ (for OpenAPI Generator runtime)
    - Backend running (for --from-url mode)

EXAMPLES:
    # Fetch spec from running backend and generate client
    ./scripts/generate-api-client.sh

    # Use existing spec file (backend doesn't need to be running)
    ./scripts/generate-api-client.sh --from-file

    # Validate the OpenAPI spec without generating
    ./scripts/generate-api-client.sh --validate

    # See what would be generated
    ./scripts/generate-api-client.sh --dry-run

    # Use a different backend URL
    BACKEND_URL=http://api.staging.example.com ./scripts/generate-api-client.sh

OUTPUT:
    Generated files are placed in: frontend/src/api/generated/

    Directory structure:
    - apis/         API classes grouped by OpenAPI tags
    - models/       TypeScript interfaces from OpenAPI schemas
    - runtime.ts    Fetch configuration and helpers
    - index.ts      Re-exports all APIs and models

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --from-file)
                FROM_URL=false
                shift
                ;;
            --from-url)
                FROM_URL=true
                shift
                ;;
            --validate)
                VALIDATE_ONLY=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help to see available options."
                exit 1
                ;;
        esac
    done
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."

    # Check Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed. Please install Node.js 18+."
        exit 1
    fi

    local node_version
    node_version=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    if [[ "$node_version" -lt 18 ]]; then
        print_error "Node.js 18+ required. Found: $(node -v)"
        exit 1
    fi

    # Check Java (required by OpenAPI Generator)
    if ! command -v java &> /dev/null; then
        print_error "Java is not installed. OpenAPI Generator requires Java 11+."
        echo ""
        echo "Install Java:"
        echo "  macOS:  brew install openjdk@11"
        echo "  Ubuntu: sudo apt-get install openjdk-11-jdk"
        echo "  Docker: Run this script inside a container with Java"
        exit 1
    fi

    local java_version
    java_version=$(java -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
    if [[ "$java_version" -lt 11 ]]; then
        print_error "Java 11+ required. Found: $(java -version 2>&1 | head -1)"
        exit 1
    fi

    # Check npm dependencies
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        print_warning "Node modules not installed. Running npm install..."
        cd "$FRONTEND_DIR"
        npm install
    fi

    print_success "Prerequisites check passed"
}

# Fetch OpenAPI spec from running backend
fetch_spec() {
    print_info "Fetching OpenAPI spec from $BACKEND_URL..."

    # Check if backend is running
    local health_url="$BACKEND_URL$HEALTH_ENDPOINT"
    if ! curl -sf "$health_url" > /dev/null 2>&1; then
        print_error "Backend is not running at $BACKEND_URL"
        echo ""
        echo "Start the backend with: ./scripts/docker-dev.sh up"
        echo "Or use --from-file to use an existing spec file."
        exit 1
    fi

    # Fetch OpenAPI spec
    local openapi_url="$BACKEND_URL$OPENAPI_ENDPOINT"
    if ! curl -sf "$openapi_url" > "$OPENAPI_SPEC_PATH"; then
        print_error "Failed to fetch OpenAPI spec from $openapi_url"
        exit 1
    fi

    print_success "OpenAPI spec saved to $OPENAPI_SPEC_PATH"
}

# Validate OpenAPI spec
validate_spec() {
    print_info "Validating OpenAPI spec..."

    if [[ ! -f "$OPENAPI_SPEC_PATH" ]]; then
        print_error "OpenAPI spec not found at $OPENAPI_SPEC_PATH"
        echo "Run with --from-url to fetch from running backend."
        exit 1
    fi

    cd "$FRONTEND_DIR"

    if ! npx @openapitools/openapi-generator-cli validate -i "$OPENAPI_SPEC_PATH"; then
        print_error "OpenAPI spec validation failed"
        exit 1
    fi

    print_success "OpenAPI spec is valid"
}

# Generate TypeScript client
generate_client() {
    print_info "Generating TypeScript client..."

    cd "$FRONTEND_DIR"

    # Clean previous generation (except ignored files)
    if [[ -d "src/api/generated" ]]; then
        print_info "Cleaning previous generated files..."
        rm -rf src/api/generated/apis src/api/generated/models 2>/dev/null || true
        # Keep files in .openapi-generator-ignore
    fi

    # Ensure generated directory exists
    mkdir -p src/api/generated

    # Copy ignore file to generated directory
    if [[ -f ".openapi-generator-ignore" ]]; then
        cp .openapi-generator-ignore src/api/generated/.openapi-generator-ignore
    fi

    # Run generator
    npx @openapitools/openapi-generator-cli generate \
        --config openapitools.json \
        --generator-key typescript-fetch

    print_success "TypeScript client generated"
}

# Post-process generated code
post_process() {
    print_info "Post-processing generated code..."

    cd "$FRONTEND_DIR"

    # Format generated code with Prettier
    if npx prettier --version > /dev/null 2>&1; then
        print_info "Formatting generated code with Prettier..."
        npx prettier --write src/api/generated/ 2>/dev/null || true
    fi

    # Run ESLint fix (if configured)
    if [[ -f ".eslintrc.js" ]] || [[ -f ".eslintrc.json" ]] || [[ -f "eslint.config.js" ]]; then
        print_info "Running ESLint auto-fix..."
        npx eslint --fix src/api/generated/ 2>/dev/null || true
    fi

    print_success "Post-processing complete"
}

# Print summary
print_summary() {
    cd "$FRONTEND_DIR"

    echo ""
    echo -e "${GREEN}=== Generation Complete ===${NC}"
    echo ""

    # Count generated files
    local total_files=0
    local api_files=0
    local model_files=0

    if [[ -d "src/api/generated" ]]; then
        total_files=$(find src/api/generated -type f -name "*.ts" 2>/dev/null | wc -l | tr -d ' ')
        if [[ -d "src/api/generated/apis" ]]; then
            api_files=$(find src/api/generated/apis -type f -name "*.ts" 2>/dev/null | wc -l | tr -d ' ')
        fi
        if [[ -d "src/api/generated/models" ]]; then
            model_files=$(find src/api/generated/models -type f -name "*.ts" 2>/dev/null | wc -l | tr -d ' ')
        fi
    fi

    echo "Generated files:"
    echo "  - Total:  $total_files TypeScript files"
    echo "  - APIs:   $api_files API classes"
    echo "  - Models: $model_files model interfaces"
    echo ""
    echo "Output directory: frontend/src/api/generated/"
    echo ""
    echo "Usage example:"
    echo '  import { DefaultApi, Configuration } from "./api/generated"'
    echo '  const api = new DefaultApi(new Configuration({ basePath: "'"$BACKEND_URL"'" }))'
    echo '  const response = await api.healthCheck()'
    echo ""
    echo "Documentation: frontend/src/api/generated/README.md"
}

# Main function
main() {
    parse_args "$@"

    echo ""
    echo -e "${GREEN}=== Knowledge Mapper - OpenAPI TypeScript Client Generator ===${NC}"
    echo ""

    check_prerequisites

    # Step 1: Get OpenAPI spec
    if [[ "$FROM_URL" == true ]]; then
        fetch_spec
    else
        if [[ ! -f "$OPENAPI_SPEC_PATH" ]]; then
            print_error "OpenAPI spec not found at $OPENAPI_SPEC_PATH"
            echo "Run with --from-url to fetch from running backend."
            exit 1
        fi
        print_info "Using existing OpenAPI spec: $OPENAPI_SPEC_PATH"
    fi

    # Step 2: Validate spec
    validate_spec

    if [[ "$VALIDATE_ONLY" == true ]]; then
        echo ""
        print_success "Validation complete. Exiting."
        exit 0
    fi

    # Step 3: Dry run check
    if [[ "$DRY_RUN" == true ]]; then
        echo ""
        print_info "Dry run - would generate client to: $FRONTEND_DIR/src/api/generated/"
        echo ""
        echo "Files that would be generated:"
        echo "  - src/api/generated/index.ts"
        echo "  - src/api/generated/runtime.ts"
        echo "  - src/api/generated/apis/*.ts (API classes by tag)"
        echo "  - src/api/generated/models/*.ts (TypeScript interfaces)"
        exit 0
    fi

    # Step 4: Generate client
    generate_client

    # Step 5: Post-process
    post_process

    # Step 6: Print summary
    print_summary
}

# Run main
main "$@"
