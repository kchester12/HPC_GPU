#!/usr/bin/env python3
"""jobtrace.py - trace a Slurm job end to end and map its endpoints.

Given a Slurm job ID, this script collects, on every node the job runs on:
  - the job's processes (PIDs, found via SLURM_JOB_ID in /proc/<pid>/environ)
  - the network peers (ss, filtered by PID)
  - the open files (lsof, or /proc/<pid>/fd when lsof is absent)
  - the GPUs each process is using (nvidia-smi compute apps)

and prints one map: rank -> node -> GPU -> network peers -> open files.

Usage:
  python3 jobtrace.py <jobid> [--nodes node001,node002] [--user kchaudhu]
      [--timeout 30] [--json] [--ssh-user kchaudhu] [--ssh-opts "-o StrictHostKeyChecking=no"]

Requirements:
  - scontrol on the machine you run this from (to get the job's nodelist).
  - passwordless SSH to the compute nodes (or ssh-agent).
  - No agent or daemon on the nodes. This is the on-demand Level 1 tool:
    it only sees what is running right now. After the job exits, the
    processes are gone and ss/lsof show nothing.

How it works:
  1. scontrol show job <id> gives the NodeList, the user, and the state.
  2. The NodeList is expanded (node[001-004] -> node001..node004).
  3. On each node, in parallel over SSH, a small bash collector runs:
     it finds the job's PIDs by reading /proc/<pid>/environ for
     SLURM_JOB_ID=<id>, then collects ps, ss, lsof, and nvidia-smi.
  4. The results are parsed and printed as one map, plus a summary
     of the unique endpoints (peers, filesystems, GPUs).
"""

import argparse
import concurrent.futures
import itertools
import json
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# The collector that runs on each compute node over SSH.
# It is passed to the node as a bash script on stdin (ssh <node> "bash -s" < script).
# It prints a simple line-based format that the Python side parses:
#   == PIDS: <pid> <pid> ...
#   == PROC <pid>
#   <ps output line>
#   == SS <pid>
#   <ss output lines>
#   == FD <pid>
#   <lsof or /proc fd lines>
#   == NVIDIA
#   <nvidia-smi compute apps csv lines>
#   == NVIDIA-GPUS
#   <nvidia-smi gpu list csv lines>
# ---------------------------------------------------------------------------
COLLECTOR = r"""#!/bin/bash
JOBID="$1"
PIDS=""
for p in /proc/[0-9]*; do
  pid="${p#/proc/}"
  # cat opens the file itself, so a permission error goes to cat's stderr
  # (redirected here) instead of being reported by the shell for a failed
  # redirect. The NUL-separated environ is turned into lines by tr.
  if cat "$p/environ" 2>/dev/null | tr '\0' '\n' | grep -q "^SLURM_JOB_ID=${JOBID}$"; then
    PIDS="$PIDS $pid"
  fi
done
echo "== PIDS:$PIDS"
for pid in $PIDS; do
  echo "== PROC $pid"
  ps -o pid,ppid,pcpu,pmem,etime,args -p "$pid" --no-headers 2>/dev/null || echo "(ps failed)"
  echo "== SS $pid"
  if command -v ss >/dev/null 2>&1; then
    ss -tnp 2>/dev/null | grep -E "pid=${pid}[,)]" || echo "(no tcp connections)"
  else
    echo "(ss not found)"
  fi
  echo "== FD $pid"
  if command -v lsof >/dev/null 2>&1; then
    lsof -p "$pid" 2>/dev/null | awk 'NR>1 {print $NF}' | sort -u || echo "(lsof failed)"
  else
    ls -l /proc/$pid/fd 2>/dev/null | awk '{print $NF}' | grep -v '^total' | sort -u || echo "(fd read failed)"
  fi
done
echo "== NVIDIA"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-compute-apps=pid,used_memory,gpu_uuid,gpu_name --format=csv,noheader 2>/dev/null || echo "(no compute apps)"
  echo "== NVIDIA-GPUS"
  nvidia-smi --query-gpu=index,name,pci.bus_id --format=csv,noheader 2>/dev/null || echo "(no gpus)"
else
  echo "(nvidia-smi not found)"
fi
"""


def _split_top_level(s):
    """Split on commas that are not inside square brackets."""
    parts, depth, current = [], 0, []
    for ch in s:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def expand_nodelist(nodelist):
    """Expand a Slurm nodelist into a list of hostnames.

    Handles: node001, node[001-004], node[001-002,005], node001,node002,
    and multiple bracket groups such as rack[1-2]node[01-02].
    """
    hosts = []
    for part in _split_top_level(nodelist):
        part = part.strip()
        if not part:
            continue
        m = re.search(r"\[([^\]]+)\]", part)
        if not m:
            hosts.append(part)
            continue
        # Split the part into a prefix, the bracket, and the suffix.
        prefix, rest = part[:m.start()], part[m.end():]
        items = []
        for token in m.group(1).split(","):
            token = token.strip()
            if "-" in token:
                lo, hi = token.split("-", 1)
                width = len(lo)
                for n in range(int(lo), int(hi) + 1):
                    items.append(str(n).zfill(width))
            else:
                items.append(token)
        # If the suffix has another bracket group, expand it recursively.
        suffix_hosts = expand_nodelist(rest) if "[" in rest else [rest]
        for item, suffix in itertools.product(items, suffix_hosts):
            hosts.append(prefix + item + suffix)
    return hosts


def get_job_info(jobid):
    """Run scontrol and parse the job's NodeList, user, and state."""
    try:
        out = subprocess.run(
            ["scontrol", "show", "job", str(jobid)],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError("scontrol not found; run this from a node with the Slurm client tools, "
                           "or pass --nodes to skip the lookup")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"scontrol timed out after 30s for job {jobid}")
    if out.returncode != 0:
        raise RuntimeError(f"scontrol failed for job {jobid}: {out.stderr.strip()}")
    text = out.stdout
    def field(name):
        m = re.search(rf"\b{name}=(\S+)", text)
        return m.group(1) if m else None
    nodelist = field("NodeList")
    user = field("UserId")
    state = field("JobState")
    if not nodelist:
        raise RuntimeError(f"no NodeList found for job {jobid}; is the job still in the system?")
    return {"nodelist": nodelist, "user": user, "state": state, "raw": text}


def collect_on_node(node, jobid, ssh_user, ssh_opts, timeout):
    """SSH to one node and run the collector. Returns (node, text, error)."""
    target = f"{ssh_user}@{node}" if ssh_user else node
    cmd = ["ssh"] + ssh_opts + [target, "bash", "-s", str(jobid)]
    try:
        proc = subprocess.run(
            cmd, input=COLLECTOR, capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            return node, proc.stdout, proc.stderr.strip() or f"ssh exited {proc.returncode}"
        return node, proc.stdout, None
    except subprocess.TimeoutExpired:
        return node, "", f"ssh to {node} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001 - report it, do not crash the run
        return node, "", str(exc)


def parse_node_output(node, text):
    """Parse one node's collector output into a dict."""
    result = {"node": node, "pids": [], "procs": {}, "peers": {}, "files": {}, "gpu_apps": [], "gpus": []}
    section = None
    pid = None
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("== PIDS:"):
            result["pids"] = line[len("== PIDS:"):].split()
            section = None
            continue
        m = re.match(r"^== (PROC|SS|FD) (\d+)$", line)
        if m:
            section, pid = m.group(1), m.group(2)
            continue
        if line == "== NVIDIA":
            section, pid = "NVIDIA", None
            continue
        if line == "== NVIDIA-GPUS":
            section, pid = "NVIDIA-GPUS", None
            continue
        if line.startswith("=="):
            section = None
            continue
        if section == "PROC" and pid:
            result["procs"][pid] = line.strip()
        elif section == "SS" and pid:
            if line.strip() and not line.strip().startswith("("):
                result["peers"].setdefault(pid, []).append(line.strip())
        elif section == "FD" and pid:
            if line.strip() and not line.strip().startswith("("):
                result["files"].setdefault(pid, []).append(line.strip())
        elif section == "NVIDIA":
            if line.strip() and not line.strip().startswith("("):
                result["gpu_apps"].append(line.strip())
        elif section == "NVIDIA-GPUS":
            if line.strip() and not line.strip().startswith("("):
                result["gpus"].append(line.strip())
    return result


def summarise(results):
    """Build the unique-endpoint summary across all nodes."""
    peers = set()
    filesystems = set()
    gpus = set()
    for node_result in results:
        for pid, lines in node_result["peers"].items():
            for line in lines:
                # ss -t output: State Recv-Q Send-Q Local:Port Peer:Port
                parts = line.split()
                if len(parts) >= 5:
                    peers.add(parts[4])
        for pid, paths in node_result["files"].items():
            for path in paths:
                if path.startswith("/"):
                    # The filesystem is the first two components for a
                    # typical mount (/apps, /scratch, /home) and the full
                    # path is kept in the per-process listing.
                    filesystems.add("/" + path.split("/")[1] if len(path.split("/")) > 1 else path)
                elif path.startswith("socket:"):
                    peers.add(path)
        for line in node_result["gpu_apps"]:
            fields = [f.strip() for f in line.split(",")]
            if len(fields) >= 4:
                gpus.add(f"{fields[3]} ({fields[2]})")
    return {"peers": sorted(peers), "filesystems": sorted(filesystems), "gpus": sorted(gpus)}


def print_report(jobid, job_info, results, errors):
    """Print the human-readable map."""
    print(f"Job {jobid}  state={job_info['state'] or 'unknown'}  user={job_info['user'] or 'unknown'}")
    print(f"Nodes: {job_info['nodelist']}")
    print()
    if job_info["state"] and job_info["state"].upper() not in ("RUNNING",):
        print(f"Note: job state is {job_info['state']}. ss/lsof/nvidia-smi only")
        print("show live data while the job is running. After it exits, the")
        print("processes are gone and those sections will be empty.")
        print()
    for node_result in results:
        node = node_result["node"]
        print(f"--- {node} ---")
        if not node_result["pids"]:
            print("  no processes found for this job on this node")
            continue
        gpu_by_pid = {}
        for line in node_result["gpu_apps"]:
            fields = [f.strip() for f in line.split(",")]
            if len(fields) >= 4:
                gpu_by_pid[fields[0]] = f"{fields[3]} (uuid {fields[2]}, {fields[1]} used)"
        for pid in node_result["pids"]:
            print(f"  PID {pid}: {node_result['procs'].get(pid, '(no ps output)')}")
            if pid in gpu_by_pid:
                print(f"    GPU: {gpu_by_pid[pid]}")
            peers = node_result["peers"].get(pid, [])
            print(f"    Network peers ({len(peers)}):")
            for peer in peers:
                print(f"      {peer}")
            files = node_result["files"].get(pid, [])
            # Show sockets separately from file paths for readability.
            sock = [f for f in files if f.startswith("socket:")]
            paths = [f for f in files if not f.startswith("socket:")]
            print(f"    Open files ({len(paths)} paths, {len(sock)} sockets):")
            for path in paths[:20]:
                print(f"      {path}")
            if len(paths) > 20:
                print(f"      ... and {len(paths) - 20} more (use --json for the full list)")
        if node_result["gpus"]:
            print(f"  GPUs on node: {', '.join(node_result['gpus'])}")
        print()
    summary = summarise(results)
    print("=== Unique endpoints ===")
    print(f"Network peers ({len(summary['peers'])}):")
    for peer in summary["peers"]:
        print(f"  {peer}")
    print(f"Filesystems touched ({len(summary['filesystems'])}):")
    for fs in summary["filesystems"]:
        print(f"  {fs}")
    print(f"GPUs in use ({len(summary['gpus'])}):")
    for gpu in summary["gpus"]:
        print(f"  {gpu}")
    if errors:
        print()
        print("=== Errors ===")
        for node, err in errors.items():
            print(f"  {node}: {err}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jobid", help="Slurm job ID to trace")
    parser.add_argument("--nodes", help="override the nodelist (comma separated, or a Slurm nodelist)")
    parser.add_argument("--user", help="the job's user (shown in the report; scontrol already reports it)")
    parser.add_argument("--timeout", type=int, default=30, help="SSH timeout per node in seconds (default 30)")
    parser.add_argument("--ssh-user", help="SSH as this user (default: your current user)")
    parser.add_argument("--ssh-opts", default="-o BatchMode=yes -o ConnectTimeout=10",
                        help="extra ssh options (default: BatchMode, 10s connect timeout)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON instead of the human report")
    args = parser.parse_args(argv)

    try:
        job_info = get_job_info(args.jobid)
    except RuntimeError as exc:
        if not args.nodes:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        # --nodes was given, so the nodelist is known without scontrol.
        # Carry on; only the state and user are unknown.
        print(f"warning: {exc}; using --nodes, job state unknown", file=sys.stderr)
        job_info = {"nodelist": args.nodes, "user": None, "state": None, "raw": ""}
    if args.user:
        job_info["user"] = args.user
    nodelist = args.nodes if args.nodes else job_info["nodelist"]
    nodes = expand_nodelist(nodelist)
    if not nodes:
        print(f"error: no nodes in nodelist {nodelist!r}", file=sys.stderr)
        return 1

    ssh_opts = args.ssh_opts.split() if args.ssh_opts else []
    results, errors = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(nodes), 32)) as pool:
        futures = {
            pool.submit(collect_on_node, node, args.jobid, args.ssh_user, ssh_opts, args.timeout): node
            for node in nodes
        }
        for future in concurrent.futures.as_completed(futures):
            node, text, err = future.result()
            if err:
                errors[node] = err
            if text:
                results.append(parse_node_output(node, text))
    # Keep the node order stable for the report.
    order = {node: i for i, node in enumerate(nodes)}
    results.sort(key=lambda r: order.get(r["node"], 999))

    if args.json:
        print(json.dumps({"jobid": args.jobid, "job": job_info, "nodes": results, "errors": errors}, indent=2))
    else:
        print_report(args.jobid, job_info, results, errors)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
