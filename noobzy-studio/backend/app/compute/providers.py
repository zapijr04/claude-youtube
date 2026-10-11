"""Compute Providers abstraction (spec section 6).

local_cpu is always available (this entire pipeline runs on it). local_gpu
is detected, not assumed. comfyui_local and runpod_gpu are real adapters
gated behind actual configuration (a reachable ComfyUI URL / an API key) --
when not configured they report `not_configured` with the exact
prerequisite, never a fake success. No paid job is ever submitted without
an explicit CostApproval with `approved_by_user=True`.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from app.schemas import ComputeJob, ComputeJobStatus, ComputeProviderKind, CostApproval


def detect_local_gpu() -> dict:
    if shutil.which("nvidia-smi") is None:
        return {"available": False, "reason": "nvidia-smi not found in this environment"}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {"available": False, "reason": "nvidia-smi present but returned no GPU"}
        return {"available": True, "gpus": result.stdout.strip().splitlines()}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def comfyui_status() -> dict:
    url = os.environ.get("COMFYUI_URL")
    if not url:
        return {"configured": False, "reason": "COMFYUI_URL not set"}
    try:
        import urllib.request
        with urllib.request.urlopen(f"{url.rstrip('/')}/system_stats", timeout=3) as resp:
            return {"configured": True, "reachable": resp.status == 200, "url": url}
    except Exception as e:
        return {"configured": True, "reachable": False, "error": str(e), "url": url}


def runpod_status() -> dict:
    key = os.environ.get("RUNPOD_API_KEY")
    if not key:
        return {"configured": False, "reason": "RUNPOD_API_KEY not set"}
    return {"configured": True, "reason": "key present; no job submitted without explicit CostApproval"}


def list_providers() -> list[dict]:
    gpu = detect_local_gpu()
    return [
        {"provider": ComputeProviderKind.local_cpu.value, "status": "available"},
        {"provider": ComputeProviderKind.local_gpu.value, **gpu},
        {"provider": ComputeProviderKind.comfyui_local.value, **comfyui_status()},
        {"provider": ComputeProviderKind.runpod_gpu.value, **runpod_status()},
    ]


def submit_job(job: ComputeJob, approval: CostApproval | None = None) -> ComputeJob:
    if job.provider in (ComputeProviderKind.comfyui_local,):
        status = comfyui_status()
        if not status.get("configured") or not status.get("reachable"):
            job.status = ComputeJobStatus.not_configured
            job.log.append(f"ComfyUI not available: {status}")
            return job

    if job.provider == ComputeProviderKind.runpod_gpu:
        status = runpod_status()
        if not status.get("configured"):
            job.status = ComputeJobStatus.not_configured
            job.log.append("RUNPOD_API_KEY not set.")
            return job
        if job.estimated_cost_usd and job.estimated_cost_usd > 0:
            if approval is None or not approval.approved_by_user:
                job.status = ComputeJobStatus.awaiting_cost_approval
                job.log.append(
                    f"Blocked pending explicit user cost approval (est. ${job.estimated_cost_usd:.2f}, "
                    f"cap ${job.max_cost_usd or 0:.2f}). No spend has occurred."
                )
                return job
            if job.estimated_cost_usd > approval.max_spend_usd:
                job.status = ComputeJobStatus.failed
                job.log.append("Estimated cost exceeds approved max spend; refusing to submit.")
                return job

    # Real RunPod/ComfyUI submission would happen here. Neither is wired to
    # a live job executor in this environment -- marking as not_configured
    # rather than fabricating a running job.
    job.status = ComputeJobStatus.not_configured
    job.log.append("Provider adapter implemented but no live job executor connected in this environment.")
    return job
