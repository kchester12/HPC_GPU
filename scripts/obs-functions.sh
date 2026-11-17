# obs-functions.sh: shell helpers for poking observability APIs with curl + jq
# Usage: source this file from ~/.bashrc
#   [ -f ~/obs-functions.sh ] && . ~/obs-functions.sh
# Override the endpoints per shell or in ~/.bashrc:
#   export PROM_URL=http://monitor01:9090 AM_URL=http://monitor01:9093 LOKI_URL=http://monitor01:3100

: "${PROM_URL:=http://localhost:9090}"
: "${AM_URL:=http://localhost:9093}"
: "${LOKI_URL:=http://localhost:3100}"

# promq 'PromQL'  -> instant query, one line per series: labels <TAB> value
promq() {
  curl -sG "$PROM_URL/api/v1/query" --data-urlencode "query=$1" |
    jq -r 'if .status != "success" then "ERROR: \(.error)"
           else .data.result[] | "\(.metric | del(.__name__) | to_entries | map("\(.key)=\(.value)") | join(","))\t\(.value[1])" end'
}

# promdown  -> scrape targets that are not up, with the reason
promdown() {
  curl -s "$PROM_URL/api/v1/targets?state=active" |
    jq -r '.data.activeTargets[] | select(.health != "up") | "\(.labels.job)\t\(.scrapeUrl)\t\(.lastError)"'
}

# promalerts  -> pending/firing alerts as Prometheus sees them
promalerts() {
  curl -s "$PROM_URL/api/v1/alerts" |
    jq -r '.data.alerts[] | "\(.state)\t\(.labels.alertname)\t\(.labels.instance // "-")\t\(.activeAt)"'
}

# promreload  -> reload config and report whether it applied
promreload() {
  curl -s -X POST "$PROM_URL/-/reload" -o /dev/null -w 'reload HTTP %{http_code}\n'
  curl -s "$PROM_URL/api/v1/status/runtimeinfo" | jq '.data | {reloadConfigSuccess, lastConfigTime}'
}

# amalerts  -> alerts held by Alertmanager (state, name, instance)
amalerts() {
  curl -s "$AM_URL/api/v2/alerts" |
    jq -r '.[] | "\(.status.state)\t\(.labels.alertname)\t\(.labels.instance // "-")\t\(.startsAt)"'
}

# amsilence <instance-regex> <hours> "comment"  -> create a silence, print its ID
amsilence() {
  local match=${1:?instance regex} hours=${2:-2} comment=${3:-maintenance}
  curl -s -X POST "$AM_URL/api/v2/silences" -H 'Content-Type: application/json' -d "{
    \"matchers\":[{\"name\":\"instance\",\"value\":\"$match\",\"isRegex\":true,\"isEqual\":true}],
    \"startsAt\":\"$(date -u +%FT%TZ)\",\"endsAt\":\"$(date -u -d "+$hours hours" +%FT%TZ)\",
    \"createdBy\":\"$USER\",\"comment\":\"$comment\"}" | jq -r '.silenceID // .'
}

# amsilences  -> active silences
amsilences() {
  curl -s "$AM_URL/api/v2/silences" |
    jq -r '.[] | select(.status.state=="active") | "\(.id)\t\(.endsAt)\t\(.createdBy)\t\(.comment)"'
}

# lokiq 'LogQL' [limit] [since, e.g. "-1 hour"]  -> log lines, newest first
lokiq() {
  local q=${1:?LogQL} limit=${2:-50} since=${3:--1 hour}
  curl -sG "$LOKI_URL/loki/api/v1/query_range" --data-urlencode "query=$q" \
    --data-urlencode "limit=$limit" --data-urlencode "start=$(date -d "$since" +%s)" |
    jq -r '.data.result[] | .values[] | "\(.[0] | tonumber / 1e9 | strftime("%F %T"))  \(.[1])"' | sort -r
}

# scrapetime <host[:port]>  -> how long a /metrics scrape takes and how big it is
scrapetime() {
  local t=${1:?host[:port]}; [[ $t == *:* ]] || t="$t:9100"
  curl -s --compressed -o /dev/null \
    -w "http=%{http_code} time=%{time_total}s size=%{size_download}B\n" "http://$t/metrics"
}

# httpcheck <url>  -> status code and timing breakdown
httpcheck() {
  curl -s -o /dev/null -w 'code=%{http_code} dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} ttfb=%{time_starttransfer} total=%{time_total}\n' "${1:?url}"
}
