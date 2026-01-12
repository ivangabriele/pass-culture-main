#!/usr/bin/env bash

set -euo pipefail

UPSTREAM_REPO="https://github.com/pass-culture/pass-culture-main.git"

COMPANY_NAME="Ivan Gabriele"
COMPANY_EMAIL="ivan.gabriele@passculture.app"
COMPANY_GITHUB_EMAIL="igabriele-pass@users.noreply.github.com"

PERSONAL_NAME="Ivan Gabriele"
PERSONAL_EMAIL="ivan.gabriele@protonmail.com"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
WORK_DIR="${REPO_ROOT}/.sync-workdir"

if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
    source "${REPO_ROOT}/.venv/bin/activate"
fi

PUSH=false
VERBOSE=false
DRY_DEPTH=""

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Sync from upstream and rewrite commits to personal identity.

OPTIONS:
    --push          Push changes to origin after rewriting
    --dry N     Only clone the last N commits (for testing)
    --verbose       Enable verbose output
    --help          Show this help message

EXAMPLES:
    $(basename "$0")              # Sync and rewrite locally (dry run)
    $(basename "$0") --dry 10 # Test with last 10 commits
    $(basename "$0") --push       # Sync, rewrite, and push to origin
EOF
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log_verbose() {
    if [[ "$VERBOSE" == true ]]; then
        log "$@"
    fi
}

check_dependencies() {
    local missing=()

    if ! command -v git &>/dev/null; then
        missing+=("git")
    fi

    if ! command -v git-filter-repo &>/dev/null; then
        missing+=("git-filter-repo")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Error: Missing required dependencies: ${missing[*]}"
        echo "Install git-filter-repo with: pip install git-filter-repo"
        exit 1
    fi
}

create_mailmap() {
    local mailmap_file="$1"

    cat >"$mailmap_file" <<EOF
${PERSONAL_NAME} <${PERSONAL_EMAIL}> ${COMPANY_NAME} <${COMPANY_EMAIL}>
${PERSONAL_NAME} <${PERSONAL_EMAIL}> ${COMPANY_NAME} <${COMPANY_GITHUB_EMAIL}>
${PERSONAL_NAME} <${PERSONAL_EMAIL}> <${COMPANY_EMAIL}>
${PERSONAL_NAME} <${PERSONAL_EMAIL}> <${COMPANY_GITHUB_EMAIL}>
EOF

    log_verbose "Created mailmap file:"
    if [[ "$VERBOSE" == true ]]; then
        cat "$mailmap_file"
    fi
}


sync_and_rewrite() {
    log "Starting sync from upstream..."

    if [[ -d "$WORK_DIR" ]]; then
        log "Cleaning up existing work directory..."
        rm -rf "$WORK_DIR"
    fi

    mkdir -p "$WORK_DIR"

    local clone_args="--bare"
    if [[ -n "$DRY_DEPTH" ]]; then
        log "Cloning upstream repository (dry run: last $DRY_DEPTH commits)..."
        clone_args="$clone_args --depth $DRY_DEPTH"
    else
        log "Cloning upstream repository (this may take a while on first run)..."
    fi
    git clone $clone_args "$UPSTREAM_REPO" "$WORK_DIR/repo.git"

    cd "$WORK_DIR/repo.git"

    local mailmap_file="$WORK_DIR/mailmap"

    create_mailmap "$mailmap_file"

    log "Rewriting commit history..."
    git filter-repo \
        --mailmap "$mailmap_file" \
        --message-callback "$(cat <<'EOF'
REPLACEMENTS = [
    (b'Co-authored-by: Ivan Gabriele <ivan.gabriele@passculture.app>',
     b'Co-authored-by: Ivan Gabriele <ivan.gabriele@protonmail.com>'),
    (b'Co-authored-by: Ivan Gabriele <igabriele-pass@users.noreply.github.com>',
     b'Co-authored-by: Ivan Gabriele <ivan.gabriele@protonmail.com>'),
    (b'Co-Authored-By: Ivan Gabriele <ivan.gabriele@passculture.app>',
     b'Co-Authored-By: Ivan Gabriele <ivan.gabriele@protonmail.com>'),
    (b'Co-Authored-By: Ivan Gabriele <igabriele-pass@users.noreply.github.com>',
     b'Co-Authored-By: Ivan Gabriele <ivan.gabriele@protonmail.com>'),
]
for old, new in REPLACEMENTS:
    message = message.replace(old, new)
return message
EOF
)" \
        --force

    log "Rewriting complete."

    if [[ "$PUSH" == true ]]; then
        log "Pushing to origin..."

        git remote add origin "$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "origin-not-set")"

        git push --force origin master

        log "Push complete."
    else
        log "Dry run complete. Use --push to push changes to origin."
        log "Rewritten repository is at: $WORK_DIR/repo.git"
    fi
}

cleanup() {
    if [[ "$PUSH" == true ]] && [[ -d "$WORK_DIR" ]]; then
        log "Cleaning up work directory..."
        rm -rf "$WORK_DIR"
    fi
}

main() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --push)
                PUSH=true
                shift
                ;;
            --dry)
                DRY_DEPTH="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    check_dependencies
    sync_and_rewrite
    cleanup

    log "Done!"
}

main "$@"
