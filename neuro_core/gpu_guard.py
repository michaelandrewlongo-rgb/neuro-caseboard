import os
import subprocess
from dataclasses import dataclass


class GpuNotReadyError(RuntimeError):
    """Raised when the GPU is busy with another process or lacks free VRAM."""


@dataclass
class GpuProcess:
    pid: int
    name: str
    used_mib: int


@dataclass
class GpuState:
    total_mib: int
    free_mib: int
    processes: list  # list[GpuProcess]


def _default_runner(args):
    return subprocess.run(["nvidia-smi", *args], capture_output=True,
                          text=True, check=True).stdout


def query_gpu_state(runner=_default_runner):
    mem = runner(["--query-gpu=memory.total,memory.free",
                  "--format=csv,noheader,nounits"])
    total_s, free_s = (x.strip() for x in mem.strip().splitlines()[0].split(","))
    procs_out = runner(["--query-compute-apps=pid,process_name,used_memory",
                        "--format=csv,noheader,nounits"])
    processes = []
    for line in procs_out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        pid_s, name, used_s = parts
        processes.append(GpuProcess(pid=int(pid_s), name=name,
                                    used_mib=int(used_s) if used_s.isdigit() else 0))
    return GpuState(total_mib=int(total_s), free_mib=int(free_s),
                    processes=processes)


def _is_ours(proc, our_pid, ours_name_substrings):
    if proc.pid == our_pid:
        return True
    low = proc.name.lower()
    return any(s in low for s in ours_name_substrings)


def evaluate_readiness(state, min_free_mib, our_pid,
                       ours_name_substrings=("ollama",), foreign_floor_mib=300):
    """Pure check. Returns (ok, message). 'ours' = this process or Ollama; their
    VRAM counts as available because we reuse it. A foreign process holding more
    than `foreign_floor_mib` (ignores tiny display usage) means the GPU isn't
    clear; otherwise we need effective free VRAM >= min_free_mib."""
    foreign = [p for p in state.processes
               if not _is_ours(p, our_pid, ours_name_substrings)]
    ours_used = sum(p.used_mib for p in state.processes
                    if _is_ours(p, our_pid, ours_name_substrings))
    foreign_used = sum(p.used_mib for p in foreign)
    effective_free = state.free_mib + ours_used

    if foreign_used > foreign_floor_mib:
        procs = ", ".join(f"{p.name} (pid {p.pid}, {p.used_mib} MiB)"
                          for p in foreign)
        return False, (f"GPU is in use by another process: {procs}. Free it (or "
                       f"re-run with --force) before a local-model query.")
    if effective_free < min_free_mib:
        return False, (f"GPU has only {effective_free} MiB available but this query "
                       f"needs >= {min_free_mib} MiB. Close other GPU work, or lower "
                       f"GPU_MIN_FREE_MIB / use a smaller model.")
    return True, (f"GPU ready: {effective_free} MiB available "
                  f"(need {min_free_mib} MiB).")


def ensure_gpu_ready(config, runner=_default_runner, our_pid=None, force=False):
    """Raise GpuNotReadyError unless the GPU is clear and has budget. `force`
    skips the check; a missing nvidia-smi (no NVIDIA GPU) also skips it."""
    if force:
        return
    our_pid = os.getpid() if our_pid is None else our_pid
    try:
        state = query_gpu_state(runner)
    except FileNotFoundError:
        return
    ok, message = evaluate_readiness(state, config.gpu_min_free_mib, our_pid)
    if not ok:
        raise GpuNotReadyError(message)
