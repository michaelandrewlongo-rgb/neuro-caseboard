import pytest

from neuro_core.gpu_guard import (
    GpuNotReadyError,
    GpuProcess,
    GpuState,
    ensure_gpu_ready,
    evaluate_readiness,
    query_gpu_state,
)


def _runner(mem, procs):
    """Fake nvidia-smi: returns `mem` for the memory query, `procs` otherwise."""
    def run(args):
        if any("memory.total" in a for a in args):
            return mem
        return procs
    return run


class _Cfg:
    gpu_min_free_mib = 10000


def test_query_gpu_state_parses_memory_and_processes():
    runner = _runner("12227, 11944\n",
                     "1234, /usr/bin/python3, 4096\n5678, ollama, 5000\n")
    state = query_gpu_state(runner)
    assert state.total_mib == 12227
    assert state.free_mib == 11944
    assert state.processes == [
        GpuProcess(1234, "/usr/bin/python3", 4096),
        GpuProcess(5678, "ollama", 5000),
    ]


def test_query_gpu_state_empty_process_list():
    state = query_gpu_state(_runner("12227, 11944\n", "\n"))
    assert state.processes == []


def test_ready_when_clear_and_enough_free():
    state = GpuState(12227, 11944, [])
    ok, _ = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is True


def test_not_ready_when_foreign_process_present():
    state = GpuState(12227, 6000, [GpuProcess(1234, "comfyui-python", 6000)])
    ok, msg = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is False
    assert "1234" in msg


def test_our_ollama_counts_as_available():
    # Ollama holds the warm model (ours): free is low but effective free is fine.
    state = GpuState(12227, 6900, [GpuProcess(4321, "ollama", 5000)])
    ok, _ = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is True  # 6900 + 5000 = 11900 >= 10000


def test_not_ready_when_insufficient_free():
    state = GpuState(12227, 8000, [])
    ok, msg = evaluate_readiness(state, min_free_mib=10000, our_pid=999)
    assert ok is False
    assert "8000" in msg


def test_ensure_raises_when_not_ready():
    runner = _runner("12227, 6000\n", "1234, comfyui, 6000\n")
    with pytest.raises(GpuNotReadyError):
        ensure_gpu_ready(_Cfg(), runner=runner, our_pid=999)


def test_ensure_force_bypasses_check():
    def boom(args):
        raise AssertionError("runner must not be called when force=True")
    ensure_gpu_ready(_Cfg(), runner=boom, our_pid=999, force=True)  # no raise


def test_ensure_skips_when_no_nvidia_smi():
    def missing(args):
        raise FileNotFoundError("nvidia-smi")
    ensure_gpu_ready(_Cfg(), runner=missing, our_pid=999)  # no raise
