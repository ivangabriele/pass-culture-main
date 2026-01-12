# pass-culture-main (Personal Mirror)

This repository is a personal mirror of [pass-culture/pass-culture-main](https://github.com/pass-culture/pass-culture-main).

## Why?

My company requires employees to use company-dedicated GitHub accounts for work contributions. This mirror rewrites commits authored by my company account to my personal account, allowing my work contributions to appear on my personal GitHub profile.

## Structure

- **`master` branch**: Mirror of the upstream repository with commit authorship rewritten
- **`_sync` branch** (default): Contains the sync tooling and this README

## How It Works

A scheduled GitHub Actions workflow runs every 6 hours to:

1. Clone the upstream repository
2. Rewrite commit author/committer info using `git-filter-repo`
3. Rewrite `Co-authored-by` trailers in commit messages
4. Force-push to the `master` branch

## To View the Code

Switch to the [`master`](../../tree/master) branch to browse the mirrored codebase.

## Local Setup

To run the sync manually:

```bash
# Install dependencies (requires mise and uv)
mise install
uv venv && uv pip install git-filter-repo

# Run sync (dry run)
./scripts/sync.sh

# Run sync and push
./scripts/sync.sh --push
```
