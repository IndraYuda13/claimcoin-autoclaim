#!/usr/bin/env bash
set -euo pipefail
cd /root/.openclaw/workspace/projects/claimcoin-autoclaim
mkdir -p logs
if screen -ls | grep -q '[.]claimcoin-24x7'; then
  echo 'claimcoin-24x7 already running'
else
  screen -dmS claimcoin-24x7 bash -lc 'cd /root/.openclaw/workspace/projects/claimcoin-autoclaim; export PYTHONPATH=src; export ANTIBOT_RANKER_SHADOW_LOG=/tmp/antibot-ranker-shadow.jsonl; export ANTIBOT_RANKER_SHADOW_PROVIDER="/root/.openclaw/workspace/projects/antibot-ai-ranker/.venv/bin/python -m antibot_ai_ranker.cli shadow-provider --artifact /root/.openclaw/workspace/projects/antibot-ai-ranker/artifacts/disagreement-gate-v1.json"; while true; do .venv/bin/python -u -m claimcoin_autoclaim.cli run-loop --config accounts.yaml --sleep-floor 45 --sleep-cap 900 --settle-seconds 5 2>&1 | tee -a logs/run-loop-screen.log; echo "[claimcoin-24x7] crashed/exited, restart in 10s" | tee -a logs/run-loop-screen.log; sleep 10; done'
fi
if screen -ls | grep -q '[.]claimcoin-dashboard'; then
  echo 'claimcoin-dashboard already running'
else
  screen -dmS claimcoin-dashboard bash -lc 'cd /root/.openclaw/workspace/projects/claimcoin-autoclaim; .venv/bin/python scripts/claimcoin_dashboard.py'
fi
screen -ls | grep claimcoin || true
