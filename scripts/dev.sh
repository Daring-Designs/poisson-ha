#!/usr/bin/env bash
# Development helper for Poisson
# Usage: ./scripts/dev.sh [command]
#
# Commands:
#   test     - Run tests
#   lint     - Run linting
#   run      - Run locally (outside Docker)
#   build    - Build Docker image
#   shell    - Open shell in Docker container

set -euo pipefail
cd "$(dirname "$0")/.."

APP_DIR="rootfs/app"

case "${1:-help}" in
  test)
    echo "Running tests..."
    python3 -m pytest tests/ -v --tb=short
    ;;

  lint)
    echo "Running linting..."
    python3 -m ruff check "$APP_DIR" tests/
    ;;

  run)
    echo "Running Poisson locally..."
    echo "Note: Set POISSON_* env vars to override config."
    echo "      e.g. POISSON_INTENSITY=low POISSON_ENABLE_TOR=false"
    cd "$APP_DIR"
    python3 main.py
    ;;

  build)
    echo "Building Docker image..."
    docker build \
      --build-arg BUILD_FROM="ghcr.io/home-assistant/amd64-base:3.19" \
      -t poisson:dev .
    ;;

  shell)
    echo "Opening shell in Docker container..."
    docker run -it --rm \
      --build-arg BUILD_FROM="ghcr.io/home-assistant/amd64-base:3.19" \
      poisson:dev /bin/bash
    ;;

  help|*)
    echo "Poisson Development Helper"
    echo ""
    echo "Usage: ./scripts/dev.sh [command]"
    echo ""
    echo "Commands:"
    echo "  test     Run pytest test suite"
    echo "  lint     Run ruff linter"
    echo "  run      Run locally (outside Docker)"
    echo "  build    Build Docker image"
    echo "  shell    Open shell in container"
    ;;
esac
