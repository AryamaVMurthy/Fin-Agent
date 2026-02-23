from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.code_strategy.runner import run_code_strategy_sandbox
from fin_agent.code_strategy.validator import validate_code_strategy_source
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


VALID_CODE = """
def prepare(data_bundle, context):
    return {"prepared": True}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.8}]

def risk_rules(positions, context):
    return {"max_positions": 5}
"""


class CodeStrategyTests(unittest.TestCase):
    def test_validator_rejects_missing_functions(self) -> None:
        bad = """
def prepare(data_bundle, context):
    return {}
"""
        with self.assertRaises(ValueError) as exc:
            validate_code_strategy_source(bad)
        self.assertIn("missing required function", str(exc.exception))

    def test_validator_rejects_wrong_outputs(self) -> None:
        bad = """
def prepare(data_bundle, context):
    return 123
def generate_signals(frame, state, context):
    return []
def risk_rules(positions, context):
    return {}
"""
        with self.assertRaises(ValueError) as exc:
            validate_code_strategy_source(bad)
        self.assertIn("prepare", str(exc.exception))

    def test_code_strategy_versioning_increments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            sqlite_store.init_db(paths)
            validation = validate_code_strategy_source(VALID_CODE)
            one = sqlite_store.save_code_strategy_version(
                paths,
                strategy_name="MyCodeStrat",
                source_code=VALID_CODE,
                validation=validation,
            )
            two = sqlite_store.save_code_strategy_version(
                paths,
                strategy_name="MyCodeStrat",
                source_code=VALID_CODE,
                validation=validation,
            )
            self.assertEqual(one["version_number"], 1)
            self.assertEqual(two["version_number"], 2)

    def test_sandbox_runner_times_out_runaway_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            bad = """
def prepare(data_bundle, context):
    while True:
        pass
def generate_signals(frame, state, context):
    return []
def risk_rules(positions, context):
    return {}
"""
            with self.assertRaises(ValueError) as exc:
                run_code_strategy_sandbox(paths, bad, timeout_seconds=1, memory_mb=128, cpu_seconds=1)
            self.assertIn("timeout", str(exc.exception).lower())

    def test_sandbox_runner_blocks_writes_outside_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            bad = """
def prepare(data_bundle, context):
    with open('/tmp/forbidden-write.txt', 'w', encoding='utf-8') as f:
        f.write('nope')
    return {}
def generate_signals(frame, state, context):
    return []
def risk_rules(positions, context):
    return {}
"""
            with self.assertRaises(ValueError) as exc:
                run_code_strategy_sandbox(paths, bad, timeout_seconds=2, memory_mb=128, cpu_seconds=1)
            self.assertIn("outside artifact dir", str(exc.exception).lower())

    def test_sandbox_runner_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            result = run_code_strategy_sandbox(paths, VALID_CODE, timeout_seconds=3, memory_mb=128, cpu_seconds=1)
            self.assertTrue(Path(result["result_path"]).exists())
            self.assertEqual(result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
