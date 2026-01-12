# pass-culture-main (Personal Mirror)

This repository is a personal mirror of [pass-culture/pass-culture-main](https://github.com/pass-culture/pass-culture-main).

## Why?

My company requires employees to use company-dedicated GitHub accounts for work contributions. This mirror rewrites commits authored by my company account to my personal account, allowing my work contributions to appear on my personal GitHub profile.

## How It Works

```mermaid
flowchart LR
    subgraph upstream["pass-culture/pass-culture-main"]
        U[master branch]
    end

    subgraph workflow["GitHub Actions (manual trigger)"]
        direction TB
        A[Clone upstream] --> B[Rewrite authorship]
        B --> C[Force-push]
    end

    subgraph mirror["ivangabriele/pass-culture-main"]
        M[master branch]
        S[_sync branch]
    end

    U --> A
    C --> M
    S -.->|workflow_dispatch| workflow
```

The workflow (manually triggered from `_sync` branch):
1. Clones the upstream repository
2. Rewrites author/committer info using `git-filter-repo` and mailmap
3. Rewrites `Co-authored-by` trailers in commit messages
4. Force-pushes to the `master` branch

> **Note**: `master` is the default branch (for GitHub contribution counting). The workflow lives on `_sync` and must be triggered manually.

## Repository Structure

| Branch | Purpose |
|--------|---------|
| `master` (default) | Mirror of upstream with rewritten authorship |
| `_sync` | Sync tooling, workflow, and documentation |

## To View the Code

Switch to the [`master`](../../tree/master) branch to browse the mirrored codebase.

## Local Setup

```bash
# Install dependencies (requires mise and uv)
mise install
uv venv && uv pip install git-filter-repo

# Run sync (dry run with last N commits)
./scripts/sync.sh --dry 50

# Run full sync (no push)
./scripts/sync.sh

# Run sync and push
./scripts/sync.sh --push
```
