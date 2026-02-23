from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid
from pathlib import Path
from typing import Any

from fin_agent.storage.paths import RuntimePaths


def _preexec_limits(cpu_seconds: int, memory_mb: int):  # type: ignore[no-untyped-def]
    import resource

    mem_bytes = int(memory_mb) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))


def run_code_strategy_sandbox(
    paths: RuntimePaths,
    source_code: str,
    timeout_seconds: int,
    memory_mb: int,
    cpu_seconds: int,
    data_bundle: dict[str, Any] | None = None,
    frame: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if memory_mb <= 0:
        raise ValueError("memory_mb must be positive")
    if cpu_seconds <= 0:
        raise ValueError("cpu_seconds must be positive")
    if not source_code.strip():
        raise ValueError("source_code is required")

    paths.ensure()
    run_id = uuid.uuid4().hex
    artifact_dir = paths.artifacts_dir / "code-runs" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / "result.json"

    sandbox_dir = Path(tempfile.mkdtemp(prefix="fin-agent-code-sandbox-"))
    strategy_path = sandbox_dir / "user_strategy.py"
    harness_path = sandbox_dir / "harness.py"
    input_path = sandbox_dir / "input.json"

    strategy_path.write_text(source_code, encoding="utf-8")
    input_path.write_text(
        json.dumps(
            {
                "data_bundle": data_bundle or {},
                "frame": frame or [],
                "context": context or {},
            }
        ),
        encoding="utf-8",
    )
    harness_path.write_text(
        textwrap.dedent(
            """
            import builtins
            import importlib.util
            import json
            import os
            from pathlib import Path

            artifact_dir = Path(os.environ["FIN_AGENT_ARTIFACT_DIR"]).resolve()
            strategy_path = Path(os.environ["FIN_AGENT_STRATEGY_PATH"]).resolve()
            input_path = Path(os.environ["FIN_AGENT_INPUT_PATH"]).resolve()
            result_path = artifact_dir / "result.json"

            _orig_open = builtins.open

            def _guarded_open(file, mode="r", *args, **kwargs):
                is_write = any(flag in mode for flag in ("w", "a", "x", "+"))
                if is_write:
                    candidate = Path(file).resolve()
                    artifact_root = artifact_dir
                    if candidate != artifact_root and artifact_root not in candidate.parents:
                        raise PermissionError(f"write outside artifact dir blocked: {candidate}")
                return _orig_open(file, mode, *args, **kwargs)

            builtins.open = _guarded_open

            spec = importlib.util.spec_from_file_location("user_strategy", strategy_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            payload = json.loads(input_path.read_text(encoding="utf-8"))
            data_bundle = payload.get("data_bundle", {})
            frame = payload.get("frame", [])
            context = payload.get("context", {})

            prepared = module.prepare(data_bundle, context)
            signals = module.generate_signals(frame, prepared, context)
            risk = module.risk_rules([], context)

            result = {
                "prepare_type": type(prepared).__name__,
                "signals_type": type(signals).__name__,
                "signals_count": len(signals) if isinstance(signals, list) else None,
                "risk_type": type(risk).__name__,
                "prepared": prepared,
                "signals": signals,
                "risk": risk,
            }
            result_path.write_text(json.dumps(result), encoding="utf-8")
            print(str(result_path))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["FIN_AGENT_ARTIFACT_DIR"] = str(artifact_dir)
    env["FIN_AGENT_STRATEGY_PATH"] = str(strategy_path)
    env["FIN_AGENT_INPUT_PATH"] = str(input_path)

    try:
        proc = subprocess.run(
            [sys.executable, str(harness_path)],
            cwd=str(sandbox_dir),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            preexec_fn=lambda: _preexec_limits(cpu_seconds=cpu_seconds, memory_mb=memory_mb),
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"sandbox timeout exceeded after {timeout_seconds}s; remediation: optimize strategy or increase timeout"
        ) from exc
    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        detail = stderr or f"exit_code={proc.returncode}"
        if proc.returncode < 0:
            raise ValueError(
                f"sandbox timeout or resource limit exceeded: {detail}; remediation: optimize strategy or increase limits"
            )
        if "outside artifact dir blocked" in detail:
            raise ValueError(
                f"sandbox blocked write outside artifact dir: {detail}; remediation: write outputs only under artifact dir"
            )
        raise ValueError(f"sandbox execution failed: {detail}")

    if not result_path.exists():
        raise ValueError("sandbox execution failed: result artifact missing")

    result_payload = json.loads(result_path.read_text(encoding="utf-8"))

    return {
        "status": "completed",
        "run_id": run_id,
        "result_path": str(result_path),
        "outputs": result_payload,
    }
