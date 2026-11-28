"""Local safety checks for the constructor-only Raw-RAG runtime diagnostic."""
import importlib.util
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/paper1/check_rawrag_runtime.py"


def runtime_module():
    spec = importlib.util.spec_from_file_location("p1_runtime_check_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeSafetyTests(unittest.TestCase):
    def test_environment_view_never_reads_credentials_and_preserves_proxy(self):
        module = runtime_module()

        class Environment(dict):
            def __getitem__(self, key):
                if key in {"OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "OPENAI_CUSTOM_HEADERS"}:
                    raise AssertionError("a real credential value was read")
                return super().__getitem__(key)

        source = Environment(OPENAI_API_KEY="do-not-read", OPENAI_ADMIN_KEY="do-not-read",
                             OPENAI_CUSTOM_HEADERS="do-not-read",
                             HTTPS_PROXY="socks5://proxy.invalid:1234",
                             TIKTOKEN_CACHE_DIR="/tmp/tokenizer-cache")
        view = module.CredentialFreeEnvironment(source, {"P1_RUNTIME_DUMMY_KEY": "unused"})
        self.assertIsNone(view.get("OPENAI_API_KEY"))
        self.assertEqual(dict(view), {"HTTPS_PROXY": "socks5://proxy.invalid:1234",
                                    "TIKTOKEN_CACHE_DIR": "/tmp/tokenizer-cache",
                                    "P1_RUNTIME_DUMMY_KEY": "unused"})

    def test_network_is_blocked_before_any_connection(self):
        module = runtime_module()
        guard = module.OfflineGuard()
        with guard:
            with self.assertRaises(module.RuntimeCheckError):
                socket.create_connection(("127.0.0.1", 1), timeout=0.1)
        self.assertEqual(guard.network_attempts_blocked, 1)

    def test_environment_file_reads_are_blocked(self):
        module = runtime_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("only-a-test-fixture", encoding="utf-8")
            guard = module.OfflineGuard()
            with guard:
                with self.assertRaises(module.RuntimeCheckError):
                    path.read_text(encoding="utf-8")
            self.assertEqual(guard.environment_file_accesses_blocked, 1)

    def test_missing_tokenizer_cache_fails_without_network_attempt(self):
        module = runtime_module()
        with tempfile.TemporaryDirectory() as directory:
            guard = module.OfflineGuard()
            with guard:
                with self.assertRaisesRegex(module.RuntimeCheckError,
                                            "local_tokenizer_cache_required"):
                    module.check_tokenizer_cache({"TIKTOKEN_CACHE_DIR": directory})
            self.assertEqual(guard.network_attempts_blocked, 0)


if __name__ == "__main__":
    unittest.main()
