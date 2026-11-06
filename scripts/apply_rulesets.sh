#!/usr/bin/env bash
# Create or update this repository's branch and tag rulesets, matching the main Armada repository's.
#
#   scripts/apply_rulesets.sh <org>/<repo>
#
# Requires the gh CLI, authenticated with admin rights. Re-running updates in place.
set -euo pipefail

TARGET="${1:-}"
if [[ "$TARGET" != */* ]]; then
  echo "usage: $0 <org>/<repo>" >&2
  exit 2
fi
SCOPE="/repos/${TARGET}/rulesets"
echo "Applying rulesets to repository ${TARGET}"

# Both jobs run on every pull request, so requiring them can never leave one pending.
REQUIRED_CHECKS='
  { "context": "commit-messages" },
  { "context": "build" }
'

# Linear history is intentionally not enforced, so merge commits stay possible
# for the cases that need them. Rebase is the norm, upheld in review.
branch_rules() {
  cat <<JSON
  { "type": "deletion" },
  { "type": "non_fast_forward" },
  {
    "type": "pull_request",
    "parameters": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews_on_push": true,
      "require_code_owner_review": false,
      "require_last_push_approval": false,
      "required_review_thread_resolution": true,
      "allowed_merge_methods": ["rebase"]
    }
  },
  {
    "type": "required_status_checks",
    "parameters": {
      "strict_required_status_checks_policy": true,
      "do_not_enforce_on_create": false,
      "required_status_checks": [ ${REQUIRED_CHECKS} ]
    }
  }
JSON
}

ruleset_json() {
  local name="$1" target="$2" refs="$3" rules="$4"
  cat <<JSON
{
  "name": "${name}",
  "target": "${target}",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": { "include": [${refs}], "exclude": [] }
  },
  "rules": [ ${rules} ]
}
JSON
}

apply() {
  local name="$1" body="$2" id
  id=$(gh api "$SCOPE" --jq ".[] | select(.name==\"${name}\") | .id" 2>/dev/null | head -1)
  if [ -n "$id" ]; then
    printf '%s' "$body" | gh api --method PUT "${SCOPE}/${id}" --input - >/dev/null
    echo "  updated  ${name}"
  else
    printf '%s' "$body" | gh api --method POST "$SCOPE" --input - >/dev/null
    echo "  created  ${name}"
  fi
}

apply "main" "$(ruleset_json "main" "branch" '"~DEFAULT_BRANCH"' "$(branch_rules)")"
# A release tag, once pushed, can never move or disappear: consumers pin what it built.
apply "version-tags" "$(ruleset_json "version-tags" "tag" '"refs/tags/v*"' \
  '{ "type": "deletion" }, { "type": "non_fast_forward" }, { "type": "update" }')"

echo "Done. Review at: https://github.com/${TARGET}/settings/rules"