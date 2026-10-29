---
title: "Hosting Slurm and LSF Controllers on Kubernetes: What's the Gap?"
date: 2026-10-28
tags: [Kubernetes, Slurm, LSF, High Availability]
summary: "Using Kubernetes only to keep slurmctld or the LSF master alive sounds simple. Here's where that model breaks, and what works in practice."
---

## The idea

Let Slurm or LSF keep doing the job scheduling, but host the scheduler's control plane inside Kubernetes. Kubernetes' only job is high uptime for the LSF master and slurmctld: if they crash, bring them back up.

The model is sound for one case: **the process crashes**, Kubernetes restarts it, and slurmctld reloads its saved state while running jobs keep going on the compute nodes. The gaps show up in every other failure mode.

## Where the model breaks

### 1. Kubernetes detects death, not hangs
By default Kubernetes only notices that a process exited. A slurmctld that's alive but wedged, or an LSF mbatchd stuck replaying events, looks healthy. You need a liveness probe that actually asks the scheduler, such as `scontrol ping` for Slurm or `badmin`/`bhosts` for LSF.

That creates the opposite risk: a busy controller in a long scheduling cycle fails the probe, and Kubernetes kills a healthy master. Tune probe timeouts carefully, and use a `startupProbe` so a long state reload isn't mistaken for a hang.

### 2. Node failure is slow by default
A process crash recovers in seconds. A *node* failure doesn't. Kubernetes waits for the node to be marked unreachable, then applies the default 300-second eviction toleration. If the state volume is single-attach block storage, detaching it from the dead node can add several more minutes.

Realistic recovery is 5–10 minutes unless you tune it. Slurm's native backup controller takes over in about 2 minutes by default (`SlurmctldTimeout`). So in the worst case, Kubernetes can be **slower** than what Slurm already gives you.

### 3. State storage becomes the real single point of failure
slurmctld's `StateSaveLocation` and LSF's work directory (`lsb.events`) must live on persistent storage. Restarting the pod doesn't help if that storage is down. Your HA is now only as good as your storage backend.

### 4. Split-brain safety versus availability
Two controllers writing the same state directory will corrupt it. A StatefulSet prevents this: it won't start a replacement until it's sure the old pod is gone. During a network partition it *can't* be sure, so it waits, sometimes indefinitely, until a human force-deletes the old pod. You trade automatic failover for safety in exactly the scenario where you wanted automation.

### 5. Network identity
Compute nodes outside Kubernetes must reach the controller at a stable name and IP, and the controller must reach back to them. Pod IPs change, so you need `hostNetwork`, a stable Service, or careful DNS.

LSF is especially hostname-sensitive: master candidates are listed by name in `lsf.conf`, and LIM expects to run on a real host. Containerizing an LSF master is far less common, and less supported, than running Slurm on Kubernetes.

### 6. Kubernetes becomes a new dependency
The scheduler now depends on the Kubernetes control plane, etcd, the network plugin (CNI), and the storage plugin (CSI). A Kubernetes upgrade or CNI problem can take down a scheduler that would otherwise have been fine. The Kubernetes cluster has to be **more** reliable than the thing it protects.

### 7. Supporting pieces need their own HA
Munge keys have to be distributed as secrets. slurmdbd and MariaDB are a separate stateful HA problem, although slurmctld does cache accounting records during a database outage.

## What works in practice

Combine both layers instead of replacing one with the other:

- Run the primary and backup slurmctld (or two LSF master candidates) as **separate pods**.
- Use **anti-affinity** so the two pods never land on the same node.
- Put the **state directory on shared NFS** (for example, from a NetApp), mounted by both.
- Let the **scheduler's native failover** handle fast takeover, and let **Kubernetes** handle restarts, placement, and declarative upgrades.

> **Be honest about the alternative.** If all you want is "restart it when it crashes," `systemd` with `Restart=always` plus Slurm's native backup controller already does that without the extra layers. Kubernetes earns its place when you also want declarative deployment, rebuilding clusters from manifests, or sharing nodes with other Kubernetes workloads.
