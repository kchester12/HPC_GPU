---
title: "What's Your Model for Owned and Rented GPU Capacity?"
date: 2026-10-28
tags: [GPU, Architecture, Operations, Cloud]
summary: "A GPU label hides almost everything that matters in production. What to abstract, what to keep visible, and how to operate hardware you can't touch and capacity you don't own."
---

## The three-way split

Owned hardware and rented capacity can both be called "a GPU," but that label hides almost everything that matters in production: which exact card, how it's connected, how much memory is really usable, whether another tenant can see your data, whether the machine will still be there tomorrow, and what it costs when it fails.

**Some things can honestly be abstracted away.** The rest of the company should never have to think about BMC passwords, PXE boot order, driver changelogs, or which remote-hands technician swapped a drive. Those belong to the infrastructure team.

**Some things have to stay visible**, because hiding them creates a false promise. GPU model and memory, interconnect, isolation level, data locality, failure domain, cost, and availability can't be hidden. If they are, a user writes a workload that assumes NVLink and gets PCIe, assumes isolation and gets shared memory, or assumes permanent capacity and gets preempted, and then blames the platform.

**Some things should be visible only as a decision, not a detail.** A user should be able to say: *I need 8 GPUs, this isolation level, this data locality, this max cost, this max wait.* They shouldn't have to say: *I need a node with this BIOS version and this driver build in this rack.*

> That three-way split is the job: abstract the mechanics, surface the constraints, hide the toil.

## The hardware end: trust without physical access

When capacity arrives as hardware, you get everything that implies: firmware versions that interact in undocumented ways, drivers that only work with certain kernels and CUDA versions, hosts that need bring-up, and physical work done by people you'll never meet in buildings you'll rarely visit.

You can't debug that by walking over to the machine. You debug it by discipline:

- Out-of-band console and BMC logs **before** you reboot away the evidence
- Kernel logs shipped over the network for when userspace is dead
- A known-good node to compare against
- A health gate before a node returns to service

Symptoms often show up one layer away from the cause. A job that looks like it's stuck in the scheduler may really be waiting on a dead filer, and the proof comes from tracing across layers, not from restarting the loudest service.

**Remote hands should never be asked to debug.** They should be asked for one precise physical action, based on diagnostics you've already gathered: replace this FRU, reseat this cable, check this power feed. A ticket that says "machine is broken, please investigate" has already lost.

**Acceptance is part of this too.** A machine isn't production capacity because a purchase order was paid. It's production capacity after it boots clean, passes a GPU diagnostic, matches the firmware and driver matrix, passes a test job, and reports correctly to monitoring. Everything before that is a long tail of wrong SKUs, BIOS settings, cabling, and cooling.

## The provider end: control without ownership

With a neocloud or another provider, you control the software and very little else, on terms set by someone whose interests aren't yours. Theirs are utilization, standardization, and margin. Yours are performance, isolation, availability, and cost for a specific workload.

So you can't trust the advertised spec. Measure it:

- Which GPU is actually attached
- Which interconnect is actually present, and what bandwidth you actually get
- Whether the driver is the version you need
- Whether capacity in that region is available when you need it, not just when you tested it

**Capacity that isn't permanent changes the design.** Preemptible or short-lived capacity is fine for fault-tolerant batch with checkpointing, and terrible for a long training run without checkpoints.

**Provider APIs fail in provider-specific ways:** rate limits, quota errors, region outages, maintenance windows. Those aren't node failures and shouldn't trigger node-quarantine logic. They should trigger retry, fallback to another provider or to owned capacity, and honest accounting of what the job actually cost.

The best foundation for judging provider claims is knowing the layer underneath the API: Linux, drivers, firmware, BMC, networking, and GPU provisioning. If you've operated the thing a provider abstracts, you know what to measure before you trust it.

## Bare metal, VM, or container is a placement decision

It isn't a religion. The right answer changes because the workload changes:

| Workload | Placement |
|---|---|
| Long, topology-sensitive training | Bare metal |
| Untrusted multi-tenant work | A VM or a whole node, not a shared container |
| Trusted internal batch | Containers on bare metal with device controls |
| Short inference | Containers |

The mistake is to pick one and defend it. Make placement **explicit and revisitable**: this workload got bare metal because of this interconnect and this isolation requirement, recorded somewhere, so when the workload or the price changes, the decision can change without a redesign.

## This isn't architecture-only

A diagram that has never been on call isn't infrastructure. The loop is design, build, debug, operate, and then redesign based on what broke.

Consider a broker that lends nodes between two schedulers. Its rules (drain first, never open a node on both sides, never kill running jobs, health-gate before handover) don't come from a whiteboard. They come from what goes wrong when two schedulers share nodes and nobody owns the transition.

## An open question

> A provider offers you the same GPU SKU at a lower price, in a region you've never used. What do you measure first, before you move a real workload there?
