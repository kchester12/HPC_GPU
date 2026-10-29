# HPC Runbooks

Practical, field-tested workflows for Linux HPC and infrastructure operations: GPUs, job schedulers, RDMA fabrics, storage, and the incidents in between.

**Live site:** https://kchester12.github.io/HPC_GPU/

## Runbooks

| Runbook | What it covers |
|---|---|
| [GPU & CUDA HPC Sysadmin Workflow](https://kchester12.github.io/HPC_GPU/gpu_cuda_hpc_runbook.html) | Bottom-up troubleshooting for Linux GPU nodes, from PCIe and driver up to scheduler isolation and hardware faults |
| [Slurm GPU Partition Hardening Checklist](https://kchester12.github.io/HPC_GPU/slurm_gpu_hardening.html) | Security checklist for GPU nodes on Rocky Linux 9: isolation, access control, drivers, containers, monitoring, firmware |
| [NCCL and GPUDirect RDMA](https://kchester12.github.io/HPC_GPU/nccl_gpudirect_rdma.html) | NCCL collectives, GPUDirect RDMA mechanics, and why PCIe topology decides multi-node GPU performance |
| [InfiniBand and RoCE for HPC Schedulers](https://kchester12.github.io/HPC_GPU/infiniband_roce_hpc.html) | IB vs. RoCE v2, failure modes, diagnostic tools, and fabric-aware placement in LSF and Slurm |
| [NVMe/TCP vs NFS over RDMA](https://kchester12.github.io/HPC_GPU/nvme_tcp_vs_nfs_rdma.html) | Block transport vs. shared filesystem in HPC and EDA storage designs, with troubleshooting commands |
| [Fairshare and Scheduler Tuning](https://kchester12.github.io/HPC_GPU/job_scheduling_tuning.html) | How LSF, Slurm, and Grid Engine compute fairshare priority and what to tune when delays creep up |
| [After an OOM Kill: Reboot or Not?](https://kchester12.github.io/HPC_GPU/oom_recovery.html) | Checking whether a node recovered cleanly from an OOM event, and preventing it on cluster nodes |
| [Ansible Primer for HPC Compute Nodes](https://kchester12.github.io/HPC_GPU/ansible_primer.html) | A first playbook for node_exporter and slurm.conf, and how to run it safely on a live cluster |

## Discussions

Design questions and tradeoffs live at **https://kchester12.github.io/HPC_GPU/discussions.html**. The list builds itself from the files in the `_discussions` folder, newest first.

### Adding a discussion

1. Copy `DISCUSSION_TEMPLATE.md` into the `_discussions` folder.
2. Rename it after the topic, lowercase with dashes, for example `mig-vs-mps-sharing.md`.
3. Edit the title, date, tags, and summary at the top, write the discussion in Markdown, and commit.

It appears on the Discussions page within a minute or two. There's no index to update.

## Notes

- Runbook pages are standalone HTML files with no external libraries or network calls.
- Examples use generic hostnames and illustrative output. Defaults and parameter names vary by version, so check vendor and scheduler documentation before changing production settings.

Author: Koushik Chaudhuri · [LinkedIn](https://www.linkedin.com/in/koushik-chaudhuri-06211a4)
