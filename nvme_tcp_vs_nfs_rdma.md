# NVMe/TCP vs NFS over RDMA for HPC and EDA

## Overview

**NVMe/TCP** and **NFS over RDMA** are not direct equivalents. They operate at different layers of the storage stack:

- **NVMe/TCP** provides remote **block storage** using NVMe over standard TCP/IP networks.
- **NFS over RDMA** provides a shared **file-level filesystem** using NFS semantics over an RDMA transport.

For HPC and EDA architecture, first decide whether the compute nodes need a shared filesystem or remote block devices. Then choose the appropriate transport and backend architecture.

---

## 1. How NVMe/TCP works

NVMe/TCP maps NVMe queues, NVMe-oF capsules, commands, completions, and data delivery onto TCP connections.

```text
Application
    |
Filesystem / LVM / storage layer
    |
NVMe-oF initiator
    |
NVMe/TCP
    |
TCP/IP
    |
Ethernet
    |
NVMe-oF target
    |
NVMe SSDs
```

A Linux client typically consumes the exported NVMe namespace as a block device and places the appropriate filesystem or storage layer above it.

### Why this is attractive

- Uses standard IP networking.
- Can operate over conventional Ethernet infrastructure.
- Presents block storage rather than a shared NFS namespace.
- Fits environments where remote NVMe storage is needed without making RDMA mandatory for the transport.

### Important limitation

NVMe/TCP itself does **not** provide ordinary shared-file semantics to many independent compute nodes. Do not treat one conventional single-host filesystem on a shared NVMe namespace as if it were NFS. Multi-host access requires a storage/filesystem architecture specifically designed for it.

---

## 2. How NFS over RDMA works

NFS over RDMA retains the NFS filesystem model but uses RDMA for transport.

```text
Application
    |
Linux VFS
    |
NFS client
    |
RPC/RDMA
    |
RDMA NIC
    |
RoCE / InfiniBand
    |
NFS server
    |
Server filesystem
    |
Storage
```

This is useful when many compute nodes need the same namespace:

```text
/projects
/tools
/home
/design
/scratch
```

RDMA can reduce CPU involvement in data movement and reduce transfer latency compared with a conventional networking path, while NFS still provides the shared filesystem semantics.

---

## 3. The most important difference: block vs file

| Characteristic | NVMe/TCP | NFS over RDMA |
|---|---|---|
| Client interface | Block device | Shared filesystem |
| Protocol model | NVMe-oF | NFS |
| Transport | TCP/IP | RDMA |
| Standard Ethernet/IP | Yes | Requires an RDMA-capable configuration |
| Shared NFS namespace | No | Yes |
| NFS file/locking semantics | No | Yes |
| Typical role | Remote block storage / backend | Compute-facing shared filesystem |

The **block-versus-file** distinction is usually more important than the TCP-versus-RDMA distinction.

---

## 4. HPC architecture view

### NVMe/TCP as backend block storage

```text
Compute / storage host
        |
Filesystem or storage service
        |
NVMe/TCP initiator
        |
IP/Ethernet fabric
        |
NVMe target
        |
NVMe media
```

### NFS/RDMA as compute-facing shared storage

```text
HPC compute nodes
   |   |   |   |
   +---+---+---+
       |
    NFS/RDMA
       |
RDMA fabric
       |
NFS servers
       |
Filesystem / backend storage
```

The compute nodes continue to work with normal shared files and directories while RDMA changes the transport beneath NFS.

---

## 5. The technologies can be complementary

A useful architecture may combine the two:

```text
                     HPC / EDA COMPUTE FARM

        node01       node02       node03       nodeNN
           |            |            |            |
           +------------+------------+------------+
                             |
                         NFS/RDMA
                             |
                        RDMA fabric
                             |
                 +-----------+-----------+
                 |                       |
            NFS Server 1            NFS Server 2
                 |                       |
                 +-----------+-----------+
                             |
                         Filesystem
                             |
                         NVMe/TCP
                             |
                       IP/Ethernet
                             |
                       NVMe storage
```

In this design:

- **NFS/RDMA** handles the compute-facing shared-filesystem protocol and transport.
- **NVMe/TCP** can handle block transport between storage servers and an NVMe storage target.

The two technologies solve separate parts of the I/O path.

---

## 6. Why CPU overhead matters in HPC

A compute node may be running large CPU jobs, GPU jobs, EDA simulation, compilation, or preprocessing. CPU cycles spent servicing storage networking compete with application work.

A simplified path is:

```text
Storage
   |
Network
   |
CPU / memory
   |
Application
```

NFS over RDMA becomes interesting when an RDMA infrastructure already exists and CPU overhead or data-transfer latency is important.

NVMe/TCP has a different operational advantage: it runs over the familiar TCP/IP stack and existing Ethernet designs.

---

## 7. Operational troubleshooting

### NVMe/TCP layers

```text
Application / filesystem
        |
NVMe subsystem
        |
NVMe/TCP
        |
TCP/IP
        |
NIC
        |
Ethernet switches
        |
NVMe target
```

Useful Linux areas include:

```bash
ip addr
ip route
ip link
ss
ethtool <interface>
tcpdump -i <interface>
```

Also inspect the Linux NVMe subsystem and target-specific health information.

### NFS/RDMA layers

```text
Application
    |
NFS client
    |
RPC/RDMA
    |
RDMA subsystem
    |
RoCE / InfiniBand
    |
NIC
    |
Switch fabric
    |
NFS server
```

The administrator therefore needs visibility into both NFS and the RDMA fabric.

---

## 8. EDA workload considerations

EDA environments are rarely limited by only raw sequential bandwidth. Workloads can include:

- very large file populations;
- heavy `stat()`, `open()`, and `close()` activity;
- metadata-intensive directory trees;
- temporary and scratch files;
- large databases and result files;
- many concurrent scheduler jobs.

Therefore, fast NVMe media alone does not guarantee fast EDA application performance.

Investigate the complete path:

```text
Application behavior
        |
Metadata / filesystem locking
        |
Filesystem client
        |
Network
        |
Storage server CPU / memory
        |
Backend protocol
        |
Storage controller / filesystem
        |
NVMe media
```

Benchmark the workload pattern that resembles production rather than relying only on sequential throughput tests.

---

## 9. Practical decision framework

### Need a shared filesystem across HPC workers?

Start with the compute-facing filesystem requirement:

```text
NFS/TCP
NFS/RDMA
Parallel/distributed filesystem
```

NFS/RDMA is most relevant when NFS semantics are desired and an RDMA-capable infrastructure is available.

### Need remote block storage?

Consider:

```text
NVMe/TCP
NVMe/RDMA
FC/NVMe
Local NVMe
```

NVMe/TCP is especially interesting when standard Ethernet/IP infrastructure is a design requirement.

### Need both?

Separate the design into two questions:

```text
COMPUTE-FACING
NFS/TCP vs NFS/RDMA vs parallel filesystem

STORAGE-FACING
NVMe/TCP vs NVMe/RDMA vs FC/NVMe vs local NVMe
```

This prevents a misleading direct comparison between a block-storage transport and a shared-filesystem protocol.

---

## 10. HPC / EDA rule of thumb

For a Linux HPC or EDA farm:

1. Determine whether worker nodes require the same shared namespace.
2. Characterize metadata operations, small-file IOPS, large-file bandwidth, concurrency, and latency requirements.
3. Decide the compute-facing filesystem architecture.
4. Decide the backend block-storage architecture separately.
5. Measure CPU, network, metadata, filesystem-server, and media utilization during a representative workload.
6. Validate failover, multi-pathing, scheduler behavior, and failure recovery before production deployment.

### Bottom line

> **NVMe/TCP is primarily a remote block-storage transport. NFS over RDMA is a shared filesystem transported over RDMA. In HPC/EDA, they may be alternatives at some architectural boundaries, but they can also be complementary components of the same storage design.**

---

## References

- NVM Express, *NVMe over TCP Transport Specification*: https://nvmexpress.org/specification/tcp-transport-specification/
- Red Hat Enterprise Linux 9 documentation, *Enabling NFS over RDMA on an NFS server*: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_infiniband_and_rdma_networks/enabling-nfs-over-rdma-on-an-nfs-server_configuring-infiniband_and_rdma_networks
