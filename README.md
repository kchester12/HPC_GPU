# HPC Runbooks

Practical, field-tested workflows for Linux HPC and infrastructure operations: GPUs, job schedulers, RDMA fabrics, and the incidents in between.

**Live site:** https://kchester12.github.io/HPC_GPU/

## Topics

| Runbook | What it covers |
|---|---|
| [GPU & CUDA HPC Sysadmin Workflow](https://kchester12.github.io/HPC_GPU/gpu_cuda_hpc_runbook.html) | Bottom-up troubleshooting for Linux GPU nodes, from PCIe and driver up to scheduler isolation and hardware faults |
| [Slurm GPU Partition Hardening Checklist](https://kchester12.github.io/HPC_GPU/slurm_gpu_hardening.html) | Security checklist for GPU nodes on Rocky Linux 9: isolation, access control, drivers, containers, monitoring, firmware |
| [NCCL and GPUDirect RDMA](https://kchester12.github.io/HPC_GPU/nccl_gpudirect_rdma.html) | NCCL collectives, GPUDirect RDMA mechanics, and why PCIe topology decides multi-node GPU performance |
| [InfiniBand and RoCE for HPC Schedulers](https://kchester12.github.io/HPC_GPU/infiniband_roce_hpc.html) | IB vs. RoCE v2, failure modes, diagnostic tools, and fabric-aware placement in LSF and Slurm |
| [Fairshare and Scheduler Tuning](https://kchester12.github.io/HPC_GPU/job_scheduling_tuning.html) | How LSF, Slurm, and Grid Engine compute fairshare priority and what to tune when delays creep up |
| [After an OOM Kill: Reboot or Not?](https://kchester12.github.io/HPC_GPU/oom_recovery.html) | Checking whether a node recovered cleanly from an OOM event, and preventing it on cluster nodes |

## Notes

- Each page is a single standalone HTML file with no external libraries or network calls.
- Examples use generic hostnames and illustrative output. Defaults and parameter names vary by version, so check vendor and scheduler documentation before changing production settings.

Author: Koushik Chaudhuri · [LinkedIn](https://www.linkedin.com/in/koushik-chaudhuri-06211a4)
