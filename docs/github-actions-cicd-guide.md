# GitHub Actions CI/CD — Complete Guide

> **Scope**: This guide documents the full CI/CD pipeline built for `music-renamer`.
> Copy, adapt, and reuse it for any future Docker-based project that publishes
> images to GitHub Container Registry (GHCR).

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Workflow File Structure](#2-workflow-file-structure)
3. [Permissions Block](#3-permissions-block)
4. [Step-by-step Breakdown](#4-step-by-step-breakdown)
   - 4.1 Checkout
   - 4.2 GHCR Login
   - 4.3 Build & Push
   - 4.4 Trivy Security Scan (blocking)
   - 4.5 Trivy SARIF Upload (non-blocking)
   - 4.6 Cosign Image Signing
5. [.trivyignore — Managing False Positives](#5-trivyignore--managing-false-positives)
6. [Dependabot Automatic Updates](#6-dependabot-automatic-updates)
7. [Full Annotated Workflow](#7-full-annotated-workflow)
8. [Frequently Encountered Errors](#8-frequently-encountered-errors)
9. [Action Version Reference](#9-action-version-reference)
10. [Checklist for a New Project](#10-checklist-for-a-new-project)

---

## 1. Pipeline Overview

```
push to main
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  Job: docker                                         │
│                                                      │
│  1. Checkout code                                    │
│  2. Login to GHCR                                    │
│  3. Build Docker image + Push to GHCR                │
│       tags: :latest  :${{ github.sha }}              │
│  4. Trivy scan (CRITICAL+HIGH)  ← BLOCKS on findings │
│  5. Trivy SARIF  ──────────────► GitHub Security tab │
│  6. Cosign sign image (keyless via OIDC)             │
└──────────────────────────────────────────────────────┘
```

**Trigger**: every push to `main` + manual `workflow_dispatch`.

**What it guarantees**:
- No image with known CRITICAL/HIGH vulnerabilities reaches `:latest`.
- Every published image is cryptographically signed and verifiable.
- Security findings are visible in the repository's **Security → Code scanning** tab.
- All Action versions are kept current automatically via Dependabot.

---

## 2. Workflow File Structure

```
.github/
├── workflows/
│   └── build-push.yml      ← main CI/CD workflow
└── dependabot.yml          ← automatic Action version updates
.trivyignore                ← CVE exceptions (root of repo)
```

---

## 3. Permissions Block

The job needs **four** permissions. All are least-privilege; GitHub denies
everything not listed.

```yaml
permissions:
  contents: read          # checkout code
  packages: write         # push to GHCR
  id-token: write         # Cosign keyless signing via GitHub OIDC
  security-events: write  # upload Trivy SARIF to Security tab
```

> **Why `id-token: write`?**  
> Cosign keyless signing works by obtaining a short-lived certificate from
> Sigstore's Fulcio CA, proved by a GitHub OIDC token. Without this permission
> the token cannot be issued and signing fails.

---

## 4. Step-by-step Breakdown

### 4.1 Checkout

```yaml
- name: Checkout
  uses: actions/checkout@v7
```

- Always pin to the **latest stable major version** (currently `v7`).
- Dependabot will open a PR automatically when a new major is released.

---

### 4.2 GHCR Login

```yaml
- name: Log in to GHCR
  uses: docker/login-action@v4
  with:
    registry: ghcr.io
    username: ${{ github.repository_owner }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

- `GITHUB_TOKEN` is injected automatically — no extra secret needed.
- `github.repository_owner` works for both personal accounts and organisations.

---

### 4.3 Build & Push

```yaml
- name: Build & Push
  id: build                   # ← required: Cosign uses steps.build.outputs.digest
  uses: docker/build-push-action@v7
  with:
    context: .
    file: docker/Dockerfile
    push: true
    no-cache: true            # ensures Trivy scans a fresh image every time
    tags: |
      ghcr.io/${{ github.repository_owner }}/IMAGENAME:latest
      ghcr.io/${{ github.repository_owner }}/IMAGENAME:${{ github.sha }}
```

**Key decisions**:

| Option | Value | Reason |
|--------|-------|--------|
| `id: build` | `build` | Exposes `outputs.digest` for Cosign |
| `no-cache: true` | true | Prevents stale layers hiding new CVEs |
| Two tags | `:latest` + `:sha` | `:sha` is immutable; Trivy scans the exact built image |

> **Why scan with `:sha` instead of `:latest`?**  
> The `push` step may not finish atomically. Using `${{ github.sha }}` guarantees
> Trivy scans the image that was **just built in this exact run**, not a
> previously pushed `:latest`.

---

### 4.4 Trivy Security Scan (blocking)

```yaml
- name: Trivy scan (CRITICAL+HIGH blocks)
  uses: aquasecurity/trivy-action@v0.36.0
  with:
    image-ref: ghcr.io/${{ github.repository_owner }}/IMAGENAME:${{ github.sha }}
    format: table           # always visible in the Actions log
    severity: CRITICAL,HIGH
    exit-code: '1'          # FAILS the job if any finding is not suppressed
    ignore-unfixed: false   # report CVEs even if no patch exists yet
    trivyignores: .trivyignore
    vuln-type: os,library
```

**Important rules**:

1. **`exit-code: '1'`** — this is what makes the scan *blocking*. Without it,
   Trivy only reports findings but never fails the build.
2. **`ignore-unfixed: false`** — keeps visibility of all CVEs. Use `.trivyignore`
   to suppress specific ones rather than hiding them all with `ignore-unfixed: true`.
3. **`format: table`** — produces human-readable output in the Actions log. Use
   `sarif` only in the separate upload step below.
4. **Version pinning**: use explicit `vX.Y.Z` tags like `v0.36.0`, not `main`,
   `latest`, or bare `v0`. The bare major alias does not always exist for
   `trivy-action`.

#### How to find a valid trivy-action version

```bash
# List tags in the aquasecurity/trivy-action repo
curl -s https://api.github.com/repos/aquasecurity/trivy-action/tags \
  | jq '.[].name' | head -20
```

Or check: https://github.com/aquasecurity/trivy-action/releases

---

### 4.5 Trivy SARIF Upload (non-blocking)

```yaml
- name: Trivy scan (SARIF for Security tab)
  if: always()              # runs even when the blocking scan fails
  uses: aquasecurity/trivy-action@v0.36.0
  with:
    image-ref: ghcr.io/${{ github.repository_owner }}/IMAGENAME:${{ github.sha }}
    format: sarif
    output: trivy-results.sarif
    severity: CRITICAL,HIGH
    exit-code: '0'          # never blocks
    ignore-unfixed: false
    trivyignores: .trivyignore
    vuln-type: os,library

- name: Upload Trivy results to GitHub Security tab
  if: always()
  uses: github/codeql-action/upload-sarif@v4
  with:
    sarif_file: trivy-results.sarif
```

**Why two separate Trivy steps?**

| | Blocking scan | SARIF upload |
|---|---|---|
| Format | `table` | `sarif` |
| `exit-code` | `1` | `0` |
| `if:` | (default) | `always()` |
| Purpose | Fail the build | Populate Security tab |

You cannot use `format: sarif` and `format: table` in the same step.  
`if: always()` is needed on the SARIF step so that even when the blocking scan
fails, the findings still appear in the Security tab.

---

### 4.6 Cosign Image Signing

```yaml
- name: Install Cosign
  uses: sigstore/cosign-installer@v3

- name: Sign image with Cosign (keyless)
  run: |
    cosign sign --yes \
      ghcr.io/${{ github.repository_owner }}/IMAGENAME@${{ steps.build.outputs.digest }}
  env:
    COSIGN_EXPERIMENTAL: "1"
```

**How keyless signing works**:

```
GitHub Actions runner
    │
    ├─ requests OIDC token from GitHub
    │         (proves: "this code ran in github.com/OWNER/REPO")
    ▼
Sigstore Fulcio CA
    │
    ├─ issues short-lived X.509 certificate bound to the OIDC identity
    ▼
Cosign
    ├─ signs the image digest with the certificate
    └─ records the signature in Sigstore Rekor (public transparency log)
```

**Why sign the digest and not the tag?**  
Tags are mutable; digests are immutable. Signing `@sha256:abc...` ensures the
signature is permanently bound to exactly that image layer set.

**Verify on a host (e.g., OMV)**:
```bash
cosign verify ghcr.io/OWNER/IMAGENAME:latest \
  --certificate-identity-regexp="https://github.com/OWNER/.*" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

---

## 5. .trivyignore — Managing False Positives

Create `.trivyignore` in the **root of the repository** (same level as `compose.yaml`).

### Format

```
# Comments start with #
# One CVE or GHSA identifier per line

CVE-2026-12345
GHSA-xxxx-yyyy-zzzz
```

### When to suppress a CVE

| Situation | Action |
|-----------|--------|
| OS package CVE, Debian has no patch yet (`Status: affected`, no `Fixed Version`) | Add to `.trivyignore` with comment |
| Python transitive dep CVE detected from vendored metadata inside another package; fixed version is actually installed | Add to `.trivyignore` with comment explaining why |
| CVE in a package that is not used by your code at all | Add to `.trivyignore` with comment |
| CVE in a package that IS used AND a patched version exists | **Fix it** — upgrade the package |

### How to identify false positives

Trivy reports a Python CVE like `CVE-2025-47273` against `setuptools` at version
`67.6.0`. But your `requirements.txt` pins `setuptools==83.0.0`. What happened?

> Trivy reads `METADATA` files inside installed packages. Some packages bundle
> `setuptools` metadata from *when they were built*, not the version currently
> installed. So Trivy sees an old version number from inside another wheel.

Check by running inside the container:
```bash
docker run --rm IMAGE pip show setuptools
# Version: 83.0.0   ← this is what actually runs
```

If the real version is patched, the CVE is a false positive → add to `.trivyignore`.

### Annotated .trivyignore example

```
# Trivy ignore file
# Last reviewed: YYYY-MM-DD
# Re-evaluate each entry when Debian releases a patch.

# util-linux — no fix in Debian 13 yet (checked YYYY-MM-DD)
CVE-20XX-XXXXX

# Python false positive — setuptools bundled metadata inside 'wheel' package.
# Actual installed version is 83.0.0 (fixed). Run: pip show setuptools
CVE-2025-47273
GHSA-6v7p-g79w-8964
```

> **Maintenance**: Review `.trivyignore` entries after each Debian point release
> or when you update the base image. Remove entries once the upstream patch lands.

---

## 6. Dependabot Automatic Updates

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  # Keep GitHub Actions versions current
  - package-ecosystem: "github-actions"
    directory: "/"          # looks in .github/workflows/
    schedule:
      interval: "weekly"    # Monday by default
    labels:
      - "dependencies"

  # Keep Python dependencies current (add if you have requirements.txt)
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"

  # Keep Docker base image current (add if you use FROM in Dockerfile)
  - package-ecosystem: "docker"
    directory: "/docker"    # folder containing Dockerfile
    schedule:
      interval: "weekly"
    labels:
      - "dependencies"
```

### How Dependabot works with this workflow

```
Every Monday
    │
    ▼
Dependabot checks all Action @versions in .github/workflows/*.yml
    │
    ├─ actions/checkout@v4 → v7 exists → opens PR "Bump actions/checkout from 4 to 7"
    ├─ docker/login-action@v3 → v4 exists → opens PR
    └─ docker/build-push-action@v6 → v7 exists → opens PR

Each PR:
    ├─ triggers build-push.yml
    ├─ you review + merge
    └─ main now has the new version
```

### Merging Dependabot PRs safely

1. Open the PR and read the release notes (Dependabot embeds them).
2. Check the **Dependabot compatibility score** badge in the PR body.
3. If score ≥ 90% and no breaking changes noted: **Squash and merge**.
4. The pipeline re-runs on `main` with the new version.

> For major version bumps (e.g. v3 → v4) always check the action's own
> `CHANGELOG.md` or release notes for breaking changes before merging.

---

## 7. Full Annotated Workflow

```yaml
name: Build and Push (GHCR)

on:
  push:
    branches: [ "main" ]     # run on every push to main
  workflow_dispatch:          # also allow manual trigger from Actions UI

jobs:
  docker:
    runs-on: ubuntu-latest
    permissions:
      contents: read          # checkout
      packages: write         # push to GHCR
      id-token: write         # Cosign OIDC signing
      security-events: write  # SARIF upload

    steps:
      # -----------------------------------------------------------------------
      # 1. Get the code
      # -----------------------------------------------------------------------
      - name: Checkout
        uses: actions/checkout@v7

      # -----------------------------------------------------------------------
      # 2. Authenticate to GHCR (uses the auto-injected GITHUB_TOKEN)
      # -----------------------------------------------------------------------
      - name: Log in to GHCR
        uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.repository_owner }}
          password: ${{ secrets.GITHUB_TOKEN }}

      # -----------------------------------------------------------------------
      # 3. Build the image and push it with two tags
      #    id: build  →  needed so Cosign can reference steps.build.outputs.digest
      # -----------------------------------------------------------------------
      - name: Build & Push
        id: build
        uses: docker/build-push-action@v7
        with:
          context: .
          file: docker/Dockerfile   # adjust path if your Dockerfile is elsewhere
          push: true
          no-cache: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/IMAGENAME:latest
            ghcr.io/${{ github.repository_owner }}/IMAGENAME:${{ github.sha }}

      # -----------------------------------------------------------------------
      # 4. Trivy blocking scan — fails the job on CRITICAL or HIGH
      #    CVEs with no fix and false positives go in .trivyignore
      # -----------------------------------------------------------------------
      - name: Trivy scan (CRITICAL+HIGH blocks)
        uses: aquasecurity/trivy-action@v0.36.0
        with:
          image-ref: ghcr.io/${{ github.repository_owner }}/IMAGENAME:${{ github.sha }}
          format: table
          severity: CRITICAL,HIGH
          exit-code: '1'
          ignore-unfixed: false
          trivyignores: .trivyignore
          vuln-type: os,library

      # -----------------------------------------------------------------------
      # 5. Trivy SARIF — populates the Security tab; never blocks the build
      #    if: always() ensures this runs even when step 4 failed
      # -----------------------------------------------------------------------
      - name: Trivy scan (SARIF for Security tab)
        if: always()
        uses: aquasecurity/trivy-action@v0.36.0
        with:
          image-ref: ghcr.io/${{ github.repository_owner }}/IMAGENAME:${{ github.sha }}
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: '0'
          ignore-unfixed: false
          trivyignores: .trivyignore
          vuln-type: os,library

      - name: Upload Trivy results to GitHub Security tab
        if: always()
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: trivy-results.sarif

      # -----------------------------------------------------------------------
      # 6. Cosign keyless signing via GitHub OIDC
      #    Signs the immutable digest (not the mutable :latest tag)
      # -----------------------------------------------------------------------
      - name: Install Cosign
        uses: sigstore/cosign-installer@v3

      - name: Sign image with Cosign (keyless)
        run: |
          cosign sign --yes \
            ghcr.io/${{ github.repository_owner }}/IMAGENAME@${{ steps.build.outputs.digest }}
        env:
          COSIGN_EXPERIMENTAL: "1"
```

---

## 8. Frequently Encountered Errors

### `Error: unexpected status: 403 Forbidden`
**Cause**: `packages: write` missing from `permissions:`.  
**Fix**: Add `packages: write` to the job's `permissions` block.

---

### `Error: failed to fetch image: ... 401 Unauthorized`
**Cause**: Trivy is trying to pull the image but GHCR requires auth.  
**Fix**: The login step runs before the scan, so the Docker credentials are
already in the runner's keychain. If this still fails, ensure the `Log in to
GHCR` step is not conditional and runs before Trivy.

---

### `trivy-action: invalid version tag 'main'` or `'v0'`
**Cause**: `trivy-action` does not publish bare major aliases.  
**Fix**: Use an explicit `vX.Y.Z` tag. Check
https://github.com/aquasecurity/trivy-action/releases for the latest.

```yaml
# WRONG
uses: aquasecurity/trivy-action@main
uses: aquasecurity/trivy-action@v0

# CORRECT
uses: aquasecurity/trivy-action@v0.36.0
```

---

### Trivy finds CVEs that are already patched in requirements.txt
**Cause**: Python packages bundle `METADATA` from the *build time* of their
dependencies, not the currently installed version. Trivy reads those stale
metadata files.

**Fix**:
1. Verify the actually installed version: `pip show PACKAGE` inside the container.
2. If the installed version is patched: add the CVE to `.trivyignore` with
   a comment explaining it is a false positive.
3. Also explicitly pin the package in `requirements.txt` so it is always upgraded.

---

### `Error: cosign: signing failed: no private key or keyless config`
**Cause**: `id-token: write` missing from permissions.  
**Fix**: Add `id-token: write` to the job's `permissions` block.

---

### `Error: upload-sarif: ... security-events write permission required`
**Cause**: `security-events: write` missing from permissions.  
**Fix**: Add `security-events: write` to the job's `permissions` block.

---

### Build passes but Trivy finds CVEs on the next run
**Cause**: Base image layers change between runs when `no-cache: false`.  
**Fix**: Keep `no-cache: true` in `build-push-action`. This forces a fresh pull
of the base image and `apt-get` layer on every build, so any newly disclosed
CVE is immediately visible.

---

## 9. Action Version Reference

Versions current as of 2026-10-10. Dependabot will update these automatically.

| Action | Version used | Notes |
|--------|-------------|-------|
| `actions/checkout` | `v7` | Latest stable; Node 24 runtime |
| `docker/login-action` | `v4` | Latest stable; Node 24 runtime |
| `docker/build-push-action` | `v7` | Latest stable; Node 24 runtime |
| `aquasecurity/trivy-action` | `v0.36.0` | Pin to exact `vX.Y.Z` (no bare alias) |
| `github/codeql-action/upload-sarif` | `v4` | Latest stable |
| `sigstore/cosign-installer` | `v3` | Latest stable major |

---

## 10. Checklist for a New Project

Copy this checklist when setting up CI/CD from scratch:

```
[ ] Create .github/workflows/build-push.yml
    [ ] on: push + workflow_dispatch
    [ ] permissions: contents/packages/id-token/security-events
    [ ] Checkout @v7
    [ ] docker/login-action@v4 with GITHUB_TOKEN
    [ ] docker/build-push-action@v7 — id: build, no-cache: true, :latest + :sha tags
    [ ] trivy-action@vX.Y.Z — table, exit-code:1, CRITICAL+HIGH
    [ ] trivy-action@vX.Y.Z — sarif, exit-code:0, if: always()
    [ ] codeql-action/upload-sarif@v4 — if: always()
    [ ] cosign-installer@v3
    [ ] cosign sign with @${{ steps.build.outputs.digest }}

[ ] Create .trivyignore (can start empty)
    [ ] Add comment header with date
    [ ] Add OS CVEs with no fix (Debian status: affected, no Fixed Version)
    [ ] Add Python false positives (vendored metadata)

[ ] Create .github/dependabot.yml
    [ ] github-actions ecosystem, directory: /, weekly
    [ ] pip ecosystem if requirements.txt present
    [ ] docker ecosystem if Dockerfile present

[ ] Dockerfile hardening
    [ ] apt-get update && apt-get upgrade -y  (OS security patches)
    [ ] pip install --upgrade pip              (pip itself may have CVEs)
    [ ] Pin all deps in requirements.txt
    [ ] Use tini or dumb-init as PID 1
    [ ] Non-root USER (optional for this use case)

[ ] Merge first Dependabot PRs within a week of project creation
    [ ] Read release notes for major bumps
    [ ] Check compatibility score in PR
    [ ] Squash merge

[ ] Verify on first green run
    [ ] Actions tab: all steps green
    [ ] Security tab: SARIF results visible
    [ ] GHCR: image has both :latest and :sha tags
    [ ] GHCR: image has a Sigstore signature (cosign verify ...)
```
