#!/usr/bin/env bash
# Knowledge Mapper - Docker Development Helper Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Function to print colored messages
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

# Function to check if .env file exists
check_env_file() {
    if [ ! -f ".env" ]; then
        print_warning ".env file not found"
        print_info "Creating .env from .env.example..."
        cp .env.example .env
        print_success ".env file created"
        print_info "Please review and update .env with your configuration"
    fi
}

# Function to show usage
show_usage() {
    cat << EOF
Knowledge Mapper - Docker Development Helper

Usage: $0 [COMMAND]

Commands:
    up              Start all services
    down            Stop all services
    restart         Restart all services
    build           Build all service images
    rebuild         Rebuild all service images without cache
    logs [service]  Show logs (optionally for specific service)
    ps              Show running containers
    shell [service] Open shell in service container (default: backend)
    clean           Remove all containers, volumes, and images
    reset           Clean and start fresh
    help            Show this help message

Examples:
    $0 up                  # Start all services
    $0 logs backend        # Show backend logs
    $0 shell backend       # Open shell in backend container
    $0 rebuild             # Rebuild all images from scratch

EOF
}

# Function to start services
cmd_up() {
    check_env_file
    print_info "Starting all services..."
    docker compose up -d
    print_success "Services started"
    print_info "Waiting for services to be healthy..."
    sleep 5
    docker compose ps
    echo ""
    print_success "Services are running:"
    echo "  - Frontend:  http://localhost:5173"
    echo "  - Backend:   http://localhost:8000"
    echo "  - API Docs:  http://localhost:8000/docs"
    echo "  - Keycloak:  http://localhost:8080"
    echo "  - PostgreSQL: localhost:5435"
    echo "  - Redis:     localhost:6379"
}

# Function to stop services
cmd_down() {
    print_info "Stopping all services..."
    docker compose down
    print_success "Services stopped"
}

# Function to restart services
cmd_restart() {
    print_info "Restarting all services..."
    docker compose restart
    print_success "Services restarted"
    docker compose ps
}

# Function to build services
cmd_build() {
    check_env_file
    print_info "Building service images..."
    docker compose build
    print_success "Images built successfully"
}

# Function to rebuild services without cache
cmd_rebuild() {
    check_env_file
    print_info "Rebuilding service images without cache..."
    docker compose build --no-cache
    print_success "Images rebuilt successfully"
}

# Function to show logs
cmd_logs() {
    local service="${1:-}"
    if [ -n "$service" ]; then
        print_info "Showing logs for $service..."
        docker compose logs -f "$service"
    else
        print_info "Showing logs for all services..."
        docker compose logs -f
    fi
}

# Function to show running containers
cmd_ps() {
    docker compose ps
}

# Function to open shell in container
cmd_shell() {
    local service="${1:-backend}"
    print_info "Opening shell in $service container..."
    docker compose exec "$service" /bin/sh || docker compose exec "$service" /bin/bash
}

# Function to clean up
cmd_clean() {
    print_warning "This will remove all containers, volumes, and images"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cleaning up..."
        docker compose down -v --rmi all
        print_success "Cleanup complete"
    else
        print_info "Cleanup cancelled"
    fi
}

# Function to reset and start fresh
cmd_reset() {
    print_warning "This will remove all data and start fresh"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cmd_clean
        cmd_build
        cmd_up
    else
        print_info "Reset cancelled"
    fi
}

# Main script logic
main() {
    local command="${1:-help}"

    case "$command" in
        up)
            cmd_up
            ;;
        down)
            cmd_down
            ;;
        restart)
            cmd_restart
            ;;
        build)
            cmd_build
            ;;
        rebuild)
            cmd_rebuild
            ;;
        logs)
            cmd_logs "${2:-}"
            ;;
        ps)
            cmd_ps
            ;;
        shell)
            cmd_shell "${2:-backend}"
            ;;
        clean)
            cmd_clean
            ;;
        reset)
            cmd_reset
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            print_error "Unknown command: $command"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
