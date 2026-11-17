#!/usr/bin/env bash
# obs-check.sh: probe every observability endpoint, print a status table
set -u
HOST=${1:-localhost}
TIMEOUT=5
fail=0

check() {   # name url [expected-substring]
  local name=$1 url=$2 want=${3:-} body code t
  body=$(curl -sS --max-time $TIMEOUT -w '\n%{http_code} %{time_total}' "$url" 2>&1)
  read -r code t <<<"$(tail -n1 <<<"$body")"
  body=$(sed '$d' <<<"$body")
  if [[ $code =~ ^2 ]] && { [[ -z $want ]] || grep -q "$want" <<<"$body"; }; then
    printf '%-16s OK    %3s %6.3fs  %s\n' "$name" "$code" "$t" "$url"
  else
    printf '%-16s FAIL  %3s %6ss  %s\n' "$name" "${code:-000}" "${t:--}" "$url"; fail=1
  fi
}

check prometheus    http://$HOST:9090/-/ready
check prom-config   http://$HOST:9090/api/v1/status/runtimeinfo '"reloadConfigSuccess":true'
check alertmanager  http://$HOST:9093/-/ready
check grafana       http://$HOST:3000/api/health '"database": *"ok"'
check node_exporter http://$HOST:9100/metrics 'node_exporter_build_info'
check loki          http://$HOST:3100/ready 'ready'
check otelcol       http://$HOST:13133/ 'Server available'

# scrape-target summary straight from Prometheus
down=$(curl -s --max-time $TIMEOUT http://$HOST:9090/api/v1/targets |
       jq -r '[.data.activeTargets[] | select(.health!="up")] | length' 2>/dev/null)
if [[ ${down:-x} == 0 ]]; then echo "targets          OK    all scrape targets up"
else echo "targets          FAIL  ${down:-?} target(s) down"; fail=1
  curl -s http://$HOST:9090/api/v1/targets | jq -r '.data.activeTargets[] | select(.health!="up") | "   - \(.scrapeUrl): \(.lastError)"'
fi
exit $fail
