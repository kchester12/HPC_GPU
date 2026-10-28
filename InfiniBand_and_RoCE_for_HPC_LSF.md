# InfiniBand and RoCE for HPC/LSF — Reference Guide

*Prepared for interview prep and operational reference. Written to bridge from production RoCE (ConnectX-6 Lx) experience toward deeper InfiniBand fluency.*

---

## 1. The Core Idea: Why RDMA Fabrics Exist

Both InfiniBand and RoCE exist to solve the same problem: **standard TCP/IP networking is too slow and too CPU-hungry for tightly-coupled HPC workloads** (large MPI jobs, distributed training, tightly synchronized emulation workloads).

The fix is **RDMA (Remote Direct Memory Access)** — letting one server's NIC write directly into another server's memory, bypassing the OS kernel, the TCP/IP stack, and the CPU almost entirely. This gets you:

- **Microsecond-scale latency** instead of the ~50–100+ microseconds of a TCP round trip
- **Near-zero CPU overhead** for data movement (the NIC does the work, not the CPU)
- **Very high sustained bandwidth** with minimal jitter

**InfiniBand** is a purpose-built fabric designed for RDMA from the ground up — its own physical layer, switches, and management protocol.

**RoCE (RDMA over Converged Ethernet)** takes the same RDMA verbs/semantics and runs them over standard Ethernet, so you get RDMA-class performance while staying on Ethernet switches, cabling, and (mostly) tooling your team already knows.

They are **not competing technologies at the application layer** — an MPI job calling RDMA verbs doesn't fundamentally care whether it's IB or RoCE underneath. The differences are almost entirely in the **fabric, management, and failure modes** — which is exactly the layer an HPC operations engineer lives in.

---

## 2. InfiniBand Architecture

### 2.1 Physical/Link Layer
- Dedicated IB switches and HCAs (Host Channel Adapters) — not shared with general Ethernet traffic
- Link speeds named by generation: SDR, DDR, QDR, FDR, EDR, HDR, NDR (each roughly doubling throughput)
- Typically deployed in a **fat-tree (Clos) topology** for HPC clusters — non-blocking or near-non-blocking bisection bandwidth is the whole point

### 2.2 Subnet Manager (SM) — the defining IB concept
This is the single biggest conceptual difference from Ethernet, and the part most Ethernet-background engineers haven't touched:

- IB has **no equivalent of Ethernet's flooding/learning/spanning-tree**. Instead, a **Subnet Manager** (commonly **OpenSM**, or a vendor SM like NVIDIA UFM) actively discovers the fabric topology and **assigns routing (LIDs — Local Identifiers) to every port**.
- The SM runs on one node (or an embedded switch ASIC) and must be **highly available** — SM failure/failover is a classic IB operational risk. Fabrics typically run a primary + standby SM with master/standby election.
- Routing tables, partition keys (**P_Keys**, IB's VLAN-like segmentation), and QoS policies are all pushed out by the SM.
- **Operational implication:** an IB fabric problem is very often an SM problem — stale routing, SM failover storms, or P_Key misconfiguration — not a cable or card fault.

### 2.3 Key IB Tooling
| Tool | Purpose |
|---|---|
| `ibstat` / `ibv_devinfo` | Local HCA port state, link speed/width |
| `ibnetdiscover` | Walk and map the entire fabric topology |
| `ibdiagnet` | Comprehensive fabric health/diagnostic sweep |
| `ibqueryerrors` / `perfquery` | Pull per-port error counters (symbol errors, link downs, etc.) |
| `opensm` (logs) | SM state, routing recalculation events, sweep frequency |
| `smpquery` / `saquery` | Query subnet management/administration data directly |
| `ibportstate` | Manually enable/disable/query a specific port |

---

## 3. RoCE Architecture

### 3.1 RoCE v1 vs RoCE v2
- **RoCE v1**: RDMA frames encapsulated directly in Ethernet (layer 2 only) — not routable, rarely used today.
- **RoCE v2**: RDMA encapsulated in **UDP/IP** — routable across standard IP networks, which is why essentially all modern RoCE deployments (including ConnectX-6 Lx environments) are v2. This is the practical default assumption in any interview answer.

### 3.2 The Catch: Ethernet Must Be Made "Lossless"
This is the second-biggest concept to know cold. Standard Ethernet drops packets under congestion and expects TCP to retransmit — RDMA has much weaker tolerance for loss, so RoCE deployments require **lossless (or near-lossless) Ethernet**, achieved via:

- **PFC (Priority Flow Control, IEEE 802.1Qbb)** — pauses specific traffic *classes* (not the whole link) when a receiving buffer nears capacity, rather than dropping.
- **ECN (Explicit Congestion Notification)** combined with **DCQCN** (Data Center Quantized Congestion Notification) — a *proactive* congestion signaling scheme so senders back off before PFC pause frames are even needed. This is the standard congestion-control algorithm for RoCE v2 today.
- **DCB (Data Center Bridging)** — the umbrella switch feature set (PFC + ETS + DCBX) that must be correctly and *consistently* configured across every hop in the path — this is far and away the most common source of RoCE production incidents.

**Operational implication:** RoCE performance/stability problems are disproportionately **switch QoS/DCB misconfiguration** problems — a single hop with PFC or ECN mismatched from the rest of the fabric is a classic silent-degradation cause (throughput drops or micro-stalls appear without obvious link errors).

### 3.3 Key RoCE Tooling
| Tool | Purpose |
|---|---|
| `ethtool -S <iface>` | NIC-level counters (also surfaces RoCE-relevant drops/pause frames on Mellanox/NVIDIA NICs) |
| `mlxconfig` / `mlxlink` (NVIDIA/Mellanox ConnectX tooling) | Firmware config, link diagnostics on ConnectX adapters |
| `rdma` (iproute2's `rdma` tool) | Modern Linux-native way to inspect RDMA devices/links |
| `ibv_devinfo` | Works for RoCE NICs too (same verbs API as IB) |
| Switch-side DCB/PFC counters | Pause frame counts, ECN-marked packet counts — usually the real signal |
| `cma_roce_mode` / GID tables | Confirm RoCE v2 (UDP/IP) vs v1 is actually in use on a given interface |

---

## 4. Side-by-Side Comparison

| Dimension | InfiniBand | RoCE v2 |
|---|---|---|
| Fabric | Dedicated IB switches | Standard Ethernet switches (must support DCB/PFC/ECN) |
| Routing/management | Centralized Subnet Manager (OpenSM/UFM) | Standard IP routing + switch QoS config |
| Loss handling | Credit-based flow control built into the link layer | Requires PFC + ECN/DCQCN configured correctly end-to-end |
| Typical latency | Lowest (purpose-built) | Very low, slightly higher than native IB in most deployments |
| Operational familiarity | Specialized skill set (SM, P_Keys, IB tooling) | Leverages existing Ethernet/network team knowledge |
| Common failure mode | SM failover issues, routing staleness, P_Key errors | DCB/PFC/ECN misconfig on one hop, congestion-driven stalls |
| Cost/ecosystem | Higher cost, IB-specific switches | Reuses converged Ethernet infrastructure |

---

## 5. How This Connects to Scheduler-Level Work (LSF Focus)

This is the section that ties the fabric layer back to your actual day job.

### 5.1 Why the scheduler needs to know about the fabric at all
For tightly-coupled MPI/emulation workloads, **where** a job's ranks land relative to each other on the fabric matters as much as raw node availability. Two ranks on hosts under the same leaf switch communicate far faster than two ranks that have to cross the spine — so topology-aware placement is a real performance lever, not a nice-to-have.

### 5.2 LSF-specific mechanisms
- **Resource requirement strings (`-R`)** can be used to express affinity/locality preferences so LSF's scheduler biases placement toward fabric-local hosts for a job's ranks, rather than scattering them across the fabric arbitrarily.
- **`esub`/`eexec` scripts** are the natural place to add **pre-flight fabric health checks** — e.g., reject or flag a job submission if a target host's HCA/port is down, degraded, or showing elevated error counters, *before* the job wastes a slot failing at MPI init.
- **elim (external LIM) scripts** can be written to feed custom fabric-health metrics (port state, error counters, link speed) into LSF's own resource/load reporting, so bad-fabric hosts can be automatically deprioritized or drained from scheduling — the same operational pattern as feeding hardware health into any other elim-based custom resource.
- Job failures that look like "random MPI init failures" or "job hangs at startup" are extremely often **fabric-layer issues** (bad HCA, marginal cable, SM routing not yet converged, RoCE congestion) rather than LSF or application bugs — this is the single most useful diagnostic instinct to carry into this kind of role.

### 5.3 The diagnostic reflex to describe in an interview
When a job on an RDMA-fabric cluster fails or underperforms and LSF/Slurm config has been ruled out, the systematic order of investigation is typically:
1. **Local HCA/port state** on the specific hosts involved (`ibstat`, `mlxlink`, `ethtool -S`)
2. **Error counters** — symbol errors, link flaps, PFC pause counts, ECN-marked packets
3. **Fabric-wide state** — SM logs/routing recalculation (IB) or switch DCB config consistency (RoCE) across every hop in the path
4. **Workload pattern** — is this correlated with a specific job size, rank count, or time of day (congestion-driven)?
5. Only after those are ruled out, treat it as an application/scheduler-level bug

This is the same "isolate layer by layer, environment included" instinct as the LSF/LIM time-sync story — it's worth explicitly drawing that parallel if it comes up.

---

## 6. Quick Interview Talking Points

- **Framing your actual experience honestly:** "My production ownership has been RoCE v2 on ConnectX-6 Lx — I understand IB's architecture and have worked in environments running it, but I haven't personally owned Subnet Manager configuration."
- **What transfers directly:** RDMA verbs/semantics, MPI's sensitivity to fabric locality, the diagnostic reflex of checking NIC/port health → counters → fabric-wide state → workload, and the scheduler-side mechanisms (resource strings, esub health checks, elim-fed custom resources) for making the scheduler fabric-aware.
- **What's genuinely different and worth naming as a gap:** OpenSM/UFM administration, P_Key management, and native IB tooling (`ibnetdiscover`, `ibdiagnet`) — real but narrow, and fast to ramp on given the adjacent RoCE depth.

---

*This document is a study/reference aid — verify current tool syntax and DCQCN/PFC configuration specifics against your actual NIC/switch vendor documentation before using any command in production.*
