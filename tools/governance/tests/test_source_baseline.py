"""The source pin is a product evidence check independent of runner activation."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.governance import source_baseline as B


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.repo, self.pin = root / "repo", root / "private" / "baseline-pin.json"
        self.repo.mkdir()
        rows = []
        for name in B.PREFIXES:
            data = f"source: {name}".encode()
            (self.repo / name).write_bytes(data)
            rows.append(f"| `{name}` | `{hashlib.sha256(data).hexdigest()}` |")
        (self.repo / "PROJECT_INDEX.md").write_text("# Sources\n" + "\n".join(rows) + "\n")

    def test_missing_pin_is_not_pinned_and_wrong_confirmation_writes_nothing(self):
        self.assertEqual(B.verify(self.repo, self.pin)["code"], "NOT_PINNED")
        with self.assertRaisesRegex(ValueError, "does not match"):
            B.pin(self.repo, self.pin, "0" * 64)
        self.assertFalse(self.pin.exists())
        self.assertEqual(B.main(["verify", "--repo", str(self.repo), "--pin", str(self.pin)]), 1)
        self.assertEqual(B.main(["pin", "--repo", str(self.repo), "--pin", str(self.pin)]), 2)
        self.assertFalse(self.pin.exists())

    def test_exact_pin_detects_changed_index_and_source(self):
        confirmation = B.digest(self.repo / "PROJECT_INDEX.md")
        self.assertTrue(B.pin(self.repo, self.pin, confirmation)["ok"])
        self.assertTrue(B.verify(self.repo, self.pin)["ok"])
        with self.assertRaisesRegex(ValueError, "already pinned"):
            B.pin(self.repo, self.pin, confirmation)
        (self.repo / B.PREFIXES[0]).write_text("changed")
        self.assertEqual(B.verify(self.repo, self.pin)["code"], "MISMATCH")
        (self.repo / "PROJECT_INDEX.md").write_text("changed")
        self.assertEqual(B.verify(self.repo, self.pin)["code"], "ERROR")

    def test_l1_a_pin_file_that_is_valid_json_but_not_an_object_fails_closed_without_a_traceback(self):
        """L1: load_pin used to call .get() on whatever json.loads returned; a non-object pin (list, string, number,
        null, bool) raised an uncaught AttributeError - a traceback instead of a structured fail-closed response."""
        self.pin.parent.mkdir(parents=True, exist_ok=True)
        for bad in ("[]", "42", "null", '"x"', "true", "{}"):
            self.pin.write_text(bad)
            result = B.verify(self.repo, self.pin)
            self.assertEqual((result["ok"], result["code"]), (False, "PIN_INVALID"))
            self.assertEqual(B.main(["verify", "--repo", str(self.repo), "--pin", str(self.pin)]), 1)
            self.pin.unlink()

    def test_symlinked_source_is_not_accepted(self):
        name = B.PREFIXES[0]
        (self.repo / name).unlink()
        (self.repo / name).symlink_to(self.repo / B.PREFIXES[1])
        with self.assertRaisesRegex(ValueError, "symlink"):
            B.pin(self.repo, self.pin, B.digest(self.repo / "PROJECT_INDEX.md"))
        self.assertFalse(self.pin.exists())


if __name__ == "__main__":
    unittest.main()
