---
title: "Turning Mixed GPU Capacity into a Platform People Can Trust"

tags: [GPU, Architecture, Isolation, Provisioning]
summary: "Owned and rented GPUs, none of them uniform: how to choose bare metal, VM, or container, rebuild remote machines, isolate tenants, and run it all as one platform."
---

The scenario: you're handed GPU capacity, some owned, some rented, none of it uniform, plus a set of business and security requirements. The job is to turn it into production infrastructure the rest of the company can trust and operate. That raises seven questions:

1. Should a workload run on bare metal, a VM, or a container?
2. How do you provision, rebuild, and recover machines you can't walk up to?
3. Where does owned hardware beat rented capacity, and where are you just paying for the privilege?
4. What should customer isolation look like?
5. Where should you standardize, and where should you keep flexibility?
6. How do you run owned and external compute as one platform rather than two?
7. Which parts of the infrastructure should become product capabilities?

## Bare metal, VM, or container

**Decide by GPU access, isolation, and lifetime, not by preference.**

- **Bare metal** gives direct PCIe access, full driver and firmware control, and no hypervisor overhead. That matters for long multi-node training and topology-sensitive work. The cost is slow provisioning and a node-sized blast radius.
- **A VM** gives the strongest isolation for untrusted work, plus snapshots and clean teardown. But GPU passthrough rules out most live migration, and you pay overhead and complexity in the virtualization layer.
- **A container** is fast and portable, but it shares the host kernel. That's fine for trusted internal batch work, especially with device control such as Slurm's cgroup device allowlist. It is not enough on its own for untrusted customers on a shared node.

A workable rule of thumb:

| Workload | Run it on |
|---|---|
| Untrusted tenant | A VM or a whole node, never a plain container on a shared GPU node |
| Trusted batch | Containers on bare metal |
| Short-lived inference | Containers |
| Long training | Bare metal with topology-aware placement |

On a card like the T4 (16 GB, PCIe Gen3, no NVLink, no MIG), sharing is never free. It has to be explicit: time-slicing, MPS within a single tenant, or lending whole nodes.

## Provisioning and recovering remote machines

**Make rebuild the normal path, not the emergency path.**

No SSH-and-fix snowflakes. A node should be discovered, imaged from a golden image, configured from code, health-gated, and only then returned to service. Recovery is a ladder: drain, try a soft reset, reimage, and if that fails, quarantine the node with exact diagnostics for remote hands, including which FRU is suspected.

Out-of-band access is non-negotiable: BMC, Redfish, serial-over-LAN, and kernel logs shipped over the network for when userspace is dead. Boot order matters too. A machine that PXE-boots or boots the wrong disk first will look like a storage or SAN problem when it is really a boot-order problem.

The gate before return is what builds trust: GPU reset between jobs, an ECC baseline, a short test job, and driver and firmware versions that match the supported matrix. A node that fails the gate does not quietly go back into the pool.

## Owned versus rented

**Compare total cost per useful GPU-hour, not sticker price.**

Owned looks cheap per hour until you add power, space, spares, remote hands, depreciation, and idle time. Rented looks flexible until you add egress, availability risk, noisy neighbors, and provider terms changing under you.

- **Owned wins** for steady, high-utilization, predictable work, especially where data stays put or you need a specific topology or storage locality.
- **Rented wins** for bursts, experiments, new regions, and short-lived peaks.
- **You're paying for the privilege** when you rent your steady base load at a premium, or own capacity that sits idle most of the time to cover a rare peak.

The practical shape is usually: own the base, rent the peak, and re-price quarterly on utilization, cost per GPU-hour, and queue wait time, not on a one-time spreadsheet.

## Customer isolation

**Build it in layers, and assume the claim will be attacked.**

No single mechanism is enough. You need all of these:

- One tenant per GPU at a time, or per node for untrusted work
- GPU memory reset between tenants; don't assume ending a process clears device memory
- No shared MPS daemon across tenants
- Network segmentation so tenants can't see each other
- Separate storage volumes with no cross-mounts
- Separate identities, with no shared service accounts
- Audit logs that actually show who ran what, where

Compliance-driven enclave separation is the right mindset, but it isn't the same as proving a multi-tenant isolation claim. The test is: if a tenant runs hostile code on a GPU, can it read another tenant's memory, escape to the host, or reach another tenant's network? If you can't answer with a *mechanism* rather than a policy, the isolation claim doesn't hold.

## Standardize versus flexibility

**Standardize the boring parts; keep flexibility at the workload boundary.**

Standardize the OS image, the driver and firmware matrix, monitoring, logging, identity, networking, storage access, and the provisioning API. Variation there creates operational cost with no customer value.

Keep flexibility where it materially changes performance or cost: GPU model, interconnect, placement constraints, scheduler choice, and container runtime. The trick is to express flexibility as a **placement constraint**, not a snowflake configuration. Support a small, versioned matrix of combinations and treat anything outside it as a time-limited exception. It's the same idea as node categories in a cluster manager: one T4 category, one image, one set of health checks, not fifty hand-built nodes.

## One platform across owned and rented

**One control plane, honest capabilities.**

Don't pretend rented capacity is identical to owned. That breaks trust the first time a job fails for a provider-specific reason.

- **Common to everything:** one inventory, one queue, one identity system, one observability stack, one cost accounting model in GPU-hours, and one provisioning API.
- **Visible to the placement engine, not necessarily the user:** GPU model, interconnect, storage locality, egress cost, availability, and isolation level.
- **Declared by jobs:** GPU count and memory, interconnect need, isolation level, data locality, maximum cost, and maximum wait. The platform picks the source.

Failures need different handling too. A provider API outage is not a node failure; it should trigger retry or fallback, not a node quarantine.

## Product capabilities versus internal operations

**Productize only what you would document, version, and support.**

Productize a capability when it's repeatable, can be exposed as an API with an SLA, and is something customers choose you for: provisioning, GPU-hour metering, isolation guarantees, placement and topology selection, checkpoint and resume, and usable observability.

Keep it internal when it's a workaround, a provider-specific hack, a manual remote-hands process, or something that would lock you into a shape you'll regret.

> **A useful test:** would you charge for it and support it for a customer you've never met? If not, keep it internal until a second real use case forces a clean abstraction. Productizing too early freezes a bad interface.
