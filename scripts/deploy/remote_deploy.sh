#!/bin/bash
# Runs ON the EC2 instance (sent via AWS Systems Manager by .github/workflows/deploy.yml).
# Inputs (exported by the workflow before this file's body): IMAGE_REPO, TAG ("previous" = roll back).
# State lives in /opt/adaptivephish: current_tag, previous_tag, deployments.log.
set -uo pipefail

STATE=/opt/adaptivephish
NAME=adaptivephish-api
mkdir -p "$STATE"
cd "$STATE"

current=$(cat current_tag 2>/dev/null || true)
previous=$(cat previous_tag 2>/dev/null || true)

if [ "$TAG" = "previous" ]; then
  if [ -z "$previous" ]; then echo "no previous_tag recorded; cannot roll back"; exit 1; fi
  TAG="$previous"
fi
echo "current=${current:-none} previous=${previous:-none} requested=$TAG"

start() {  # start <tag>
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  local envfile=()
  [ -f "$STATE/api.env" ] && envfile=(--env-file "$STATE/api.env")
  docker run -d --name "$NAME" --restart unless-stopped \
    -p 8000:8000 --log-opt max-size=10m --log-opt max-file=3 \
    "${envfile[@]}" "$IMAGE_REPO:$1"
}

healthy() {  # healthy <tag>: wait for /health reporting a loaded model, then smoke-test /predict
  local ok=0
  for _ in $(seq 1 45); do
    if curl -sf localhost:8000/health | grep -q '"model_version"'; then ok=1; break; fi
    sleep 2
  done
  [ "$ok" = 1 ] || { echo "health check failed"; return 1; }
  curl -sf localhost:8000/health
  echo
  curl -sf -X POST localhost:8000/predict -H 'content-type: application/json' \
    -d '{"url":"https://www.nyc.gov/site/dcas/employment/jobs.page"}' | tee /dev/stderr | grep -q '"prediction"' \
    || { echo "predict smoke test failed"; return 1; }
  curl -sf localhost:8000/metrics | grep -q 'adaptivephish_model_loaded 1' \
    || { echo "model_loaded metric not 1"; return 1; }
}

if ! docker pull "$IMAGE_REPO:$TAG"; then echo "pull failed; running container untouched"; exit 1; fi

start "$TAG"
if healthy "$TAG"; then
  [ "$current" != "$TAG" ] && echo "$current" > previous_tag
  echo "$TAG" > current_tag
  echo "$(date -u +%FT%TZ) deployed $TAG (was ${current:-none})" >> deployments.log
  echo "DEPLOY OK: $TAG"
  exit 0
fi

echo "--- container logs ---"; docker logs --tail 40 "$NAME" 2>&1 || true
echo "$(date -u +%FT%TZ) FAILED $TAG" >> deployments.log
if [ -n "$current" ] && [ "$current" != "$TAG" ]; then
  echo "rolling back to $current"
  start "$current"
  if healthy "$current"; then echo "$(date -u +%FT%TZ) rolled back to $current" >> deployments.log; echo "ROLLED BACK to $current"; else echo "ROLLBACK ALSO FAILED"; fi
fi
exit 1
