#!/bin/bash
# Build + deploy the lovhistorie pipeline site.
#
# Usage:
#   bash build.sh site      # build static site in build/site/ (plaintext)
#   bash build.sh encrypt   # build/site/ → build/site-encrypted/ (staticrypt)
#   bash build.sh deploy    # build + encrypt + push to hsigstad/lovhistorie gh-pages
#   bash build.sh push      # (re)push the already-encrypted site only
#
# lovhistorie is a docs-only pipeline (no paper/ or talk/), so there is no
# make4ht step — build_site just runs the sitekit generator. The gh-pages
# site serves ONLY staticrypt-encrypted HTML. The site password is read from
# $STATICRYPT_PASSWORD or the gitignored .site-password.
#
# Deploy requirements: npx (for staticrypt) and git push access to
# hsigstad/lovhistorie.

set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Shared staticrypt-encrypt + gh-pages deploy (sk_encrypt_site / sk_deploy_site).
SITE_TITLE="Lovhistorie"
source "$PROJECT_DIR/../../research-kit/tools/site_deploy.sh"
MODE="${1:-site}"

build_site() {
    echo "=== Building static site ==="
    cd "$PROJECT_DIR"
    python3 -m source.site.build_all
}

case "$MODE" in
    site)     build_site ;;
    encrypt)  build_site; sk_encrypt_site ;;
    deploy)   build_site; sk_encrypt_site; sk_deploy_site ;;
    push)     sk_deploy_site ;;
    *) echo "Usage: bash build.sh [site|encrypt|deploy|push]"; exit 1 ;;
esac
