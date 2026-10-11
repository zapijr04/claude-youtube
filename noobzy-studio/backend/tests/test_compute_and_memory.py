from app.compute import providers
from app.creative_brief import parse_intent
from app.memory import store
from app.schemas import ComputeJob, ComputeJobStatus, ComputeProviderKind, CostApproval, MemoryRecordKind


def test_local_cpu_always_available():
    statuses = providers.list_providers()
    local_cpu = next(s for s in statuses if s["provider"] == "local_cpu")
    assert local_cpu["status"] == "available"


def test_runpod_gpu_reports_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    job = ComputeJob(provider=ComputeProviderKind.runpod_gpu, estimated_cost_usd=3.0)
    result = providers.submit_job(job)
    assert result.status == ComputeJobStatus.not_configured


def test_paid_job_blocked_without_explicit_cost_approval(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "fake-key-for-test")
    job = ComputeJob(provider=ComputeProviderKind.runpod_gpu, estimated_cost_usd=5.0, max_cost_usd=10.0)
    result = providers.submit_job(job)
    assert result.status == ComputeJobStatus.awaiting_cost_approval

    approval = CostApproval(compute_job_id=job.id, max_spend_usd=10.0, approved_by_user=True)
    job2 = ComputeJob(provider=ComputeProviderKind.runpod_gpu, estimated_cost_usd=5.0, max_cost_usd=10.0)
    result2 = providers.submit_job(job2, approval=approval)
    assert result2.status != ComputeJobStatus.awaiting_cost_approval


def test_cost_over_approved_cap_is_refused(monkeypatch):
    monkeypatch.setenv("RUNPOD_API_KEY", "fake-key-for-test")
    approval = CostApproval(compute_job_id="x", max_spend_usd=2.0, approved_by_user=True)
    job = ComputeJob(provider=ComputeProviderKind.runpod_gpu, estimated_cost_usd=50.0, max_cost_usd=2.0)
    result = providers.submit_job(job, approval=approval)
    assert result.status == ComputeJobStatus.failed


def test_memory_versions_increment_on_update():
    r1 = store.remember(MemoryRecordKind.editing_rule, "test_key_abc", {"a": 1})
    r2 = store.remember(MemoryRecordKind.editing_rule, "test_key_abc", {"a": 2})
    assert r2.version == r1.version + 1
    assert r2.id == r1.id


def test_creative_brief_parses_known_intents_and_flags_unknown():
    assert parse_intent("use three less meme sounds")["action"] == "adjust_density"
    assert parse_intent("softer zooms please")["action"] == "adjust_param"
    assert parse_intent("asdkjaslkdj random nonsense")["action"] == "unrecognized"
