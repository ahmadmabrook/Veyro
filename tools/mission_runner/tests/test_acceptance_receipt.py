"""Preserved v1 acceptance receipts: offline, bounded, fail-closed. Fixtures use the real receipt format (schema 1, ci, reviews with
kind/path/sha256/activation_sha) and the real CLI-json review shape, over a throwaway Git repo. The real v1 home is never read or
written here; the opt-in smoke test at the bottom reads a COPY named by VEYRO_REAL_ACCEPTANCES."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import acceptance_receipt as A
import runner as R
from tests import test_runner as TR

TMP_ROOT = TR.TMP_ROOT
OPUS = "claude-opus-4-1-20250805"
SONNET = "claude-sonnet-4-5"


def review_json(verdict="**OUTCOME: APPROVED.** The activation diff is sound.", models=((OPUS, 1000),), **over):
    out = {"type": "result", "subtype": "success", "is_error": False,
           "result": f"Findings follow.\nAn inline OUTCOME: CHANGES_REQUESTED mention in prose is ignored.\n\n{verdict}\n",
           "modelUsage": {m: {"inputTokens": n, "outputTokens": 7, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                              "contextWindow": 200000, "maxOutputTokens": 32000} for m, n in models}}
    out.update(over)
    return out


class Fixture(unittest.TestCase):
    MODULE = "MOD-002"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=TMP_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.repo, self.evidence = self.base / "repo", self.base / "evidence"
        for d in (self.repo, self.evidence / "acceptances", self.evidence / "runs"):
            d.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.activation = self.commit("activation")
        self.commit("later work")
        self.gk = self.put_review("runs/gatekeeper.out", review_json("OUTCOME: APPROVED"))
        self.ar = self.put_review("runs/activation.out", review_json())

    def git(self, *a, capture=False):
        r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(self.repo), *a], check=True,
                           capture_output=True, text=True)
        return r.stdout.strip()

    def commit(self, msg):
        (self.repo / "f.txt").write_text(msg)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def put_review(self, rel, obj_or_bytes):
        raw = obj_or_bytes if isinstance(obj_or_bytes, bytes) else json.dumps(obj_or_bytes).encode()
        (self.evidence / rel).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def receipt(self, **over):
        sha = over.pop("activation_sha", self.activation)
        r = {"activation_sha": sha,
             "ci": {"conclusion": "success", "event": "push", "head_sha": sha, "name": "Veyro Foundation CI", "run_id": "38907796747",
                    "status": "completed", "url": "https://github.com/x/y/actions/runs/38907796747"},
             "module": self.MODULE, "operator": "OpenClaw-hosted Codex operator", "recorded_at": "2026-10-16T15:22:48+00:00",
             "reviews": [{"activation_sha": sha, "kind": "gatekeeper", "path": "runs/gatekeeper.out", "sha256": self.gk},
                         {"activation_sha": sha, "kind": "activation-review", "path": "runs/activation.out", "sha256": self.ar}],
             "schema": 1}
        r.update(over)
        return r

    def write(self, receipt=None, module=None):
        raw = receipt if isinstance(receipt, bytes) else json.dumps(self.receipt() if receipt is None else receipt, indent=2,
                                                                    sort_keys=True).encode()
        (self.evidence / "acceptances" / f"{module or self.MODULE}.json").write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def verify(self, pin, **kw):
        return A.verify_receipt(self.evidence, self.repo, self.MODULE, pin, **kw)

    def refused(self, pin=None, *needle, **kw):
        pin = pin or self.write()
        with self.assertRaises(A.ReceiptError) as cm:
            self.verify(pin, **kw)
        for n in needle:
            self.assertIn(n, str(cm.exception))
        return str(cm.exception)


class ReceiptVerifierTests(Fixture):
    def test_a_complete_pinned_receipt_verifies(self):
        out = self.verify(self.write())
        self.assertEqual((out["module"], out["activation_sha"]), (self.MODULE, self.activation))
        self.assertEqual(sorted(out["reviews"]), sorted([self.gk, self.ar]))

    def test_an_opus_primary_with_other_opus_models_and_cache_tokens_verifies(self):
        self.ar = self.put_review("runs/activation.out", review_json(models=((OPUS, 5), ("claude-opus-4-5", 900))))
        self.verify(self.write())

    def test_the_pin_is_mandatory_and_must_match_byte_for_byte(self):
        pin = self.write()
        for bad in (None, "", "abc", "0" * 64, pin.upper()):
            with self.assertRaises(A.ReceiptError):
                self.verify(bad)
        raw = (self.evidence / "acceptances" / "MOD-002.json").read_bytes()
        (self.evidence / "acceptances" / "MOD-002.json").write_bytes(raw + b" ")  # whitespace is still a different copy
        self.refused(pin, "byte-for-byte")

    def test_a_missing_symlinked_oversized_or_non_json_receipt_is_refused(self):
        with self.assertRaises(A.ReceiptError):
            self.verify("0" * 64)  # nothing written
        path = self.evidence / "acceptances" / "MOD-002.json"
        pin = self.write(b"{not json")
        self.refused(pin, "not valid JSON")
        pin = self.write(b" " * (A.RECEIPT_MAX_BYTES + 1))
        self.refused(pin, "regular file within")
        real = self.base / "elsewhere.json"
        real.write_bytes(json.dumps(self.receipt()).encode())
        path.unlink()
        path.symlink_to(real)
        self.refused(hashlib.sha256(real.read_bytes()).hexdigest())
        path.unlink()
        os.mkfifo(path)  # must not block
        self.refused("0" * 64)

    def test_schema_module_operator_and_legacy_mode_are_checked(self):
        for over, needle in (({"schema": 2}, "schema"), ({"module": "MOD-003"}, "schema/module"), ({"operator": " "}, "operator"),
                             ({"recorded_at": 5}, "operator/recorded_at"), ({"mode": "legacy-mod000-lean-foundation"}, "not preserved"),
                             ({"activation_sha": "abc"}, "full commit sha"), ({"activation_sha": self.activation.upper()}, "full commit")):
            with self.subTest(over=over):
                self.refused(self.write(self.receipt(**over)), needle)

    def test_ci_evidence_must_be_a_completed_successful_push_run_on_the_activation_sha(self):
        base = self.receipt()["ci"]
        for k, v in (("conclusion", "failure"), ("conclusion", None), ("status", "in_progress"), ("event", "pull_request"),
                     ("name", "Other CI"), ("head_sha", "f" * 40), ("run_id", "12ab"), ("run_id", 123)):
            with self.subTest(k=k, v=v):
                self.refused(self.write(self.receipt(ci={**base, k: v})), "CI evidence")
        self.refused(self.write(self.receipt(ci=None)), "CI evidence")
        self.refused(self.write(self.receipt(ci="success")), "CI evidence")

    def test_the_activation_commit_must_be_an_ancestor_of_head(self):
        self.git("checkout", "-q", "-b", "side", self.activation)
        side = self.commit("side")
        self.git("checkout", "-q", "main")
        self.refused(self.write(self.receipt(activation_sha=side, reviews=[{**r, "activation_sha": side} for r in self.receipt()["reviews"]],
                                             ci={**self.receipt()["ci"], "head_sha": side})), "not an ancestor")
        unknown = "1" * 40
        self.refused(self.write(self.receipt(activation_sha=unknown, ci={**self.receipt()["ci"], "head_sha": unknown},
                                             reviews=[{**r, "activation_sha": unknown} for r in self.receipt()["reviews"]])), "not an ancestor")
        self.git("checkout", "-q", "side")
        self.verify(self.write())  # the activation commit is still an ancestor of side's HEAD
        self.git("checkout", "-q", "--orphan", "unrelated")
        self.git("commit", "-q", "--allow-empty", "-m", "unrelated history")
        self.refused(self.write(), "not an ancestor")

    def test_git_failures_are_not_acceptance(self):
        pin = self.write()
        for body in ("exit 128", "exit 1", "sleep 30"):
            fake = self.base / "git"
            fake.write_text(f"#!/bin/sh\n{body}\n")
            fake.chmod(0o755)
            with self.subTest(body=body), mock.patch.object(A.subprocess, "run", wraps=A.subprocess.run) as run:
                if body.startswith("sleep"):
                    run.side_effect = A.subprocess.TimeoutExpired("git", 10)
                self.refused(pin, "not an ancestor", git=str(fake))
        self.refused(pin, "not an ancestor", git=str(self.base / "no-such-git"))

    def test_only_a_restricted_offline_git_command_is_run(self):
        calls = []

        def fake(argv, **kw):
            calls.append((argv, kw))
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        with mock.patch.object(A.subprocess, "run", fake):
            self.verify(self.write())
        (argv, kw), = calls
        self.assertEqual(argv[-4:], ["merge-base", "--is-ancestor", self.activation, "HEAD"])
        self.assertIn("core.fsmonitor=", argv)
        self.assertEqual(kw["env"]["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertNotIn("HOME", kw["env"])
        self.assertTrue(kw["timeout"] <= 10 and kw["stdin"] == subprocess.DEVNULL)

    def test_reviews_are_hashed_bound_distinct_and_both_kinds_are_required(self):
        r = self.receipt()
        gk, ar = r["reviews"]
        cases = {
            "hash mismatch": ({**gk, "sha256": "0" * 64}, ar, "recorded sha256"),
            "unbound": ({**gk, "activation_sha": "2" * 40}, ar, "not bound"),
            "unbound-missing": ({k: v for k, v in gk.items() if k != "activation_sha"}, ar, "not bound"),
            "kind": ({**gk, "kind": "other"}, ar, "malformed review"),
            "path type": ({**gk, "path": 5}, ar, "malformed review"),
            "sha not hex": ({**gk, "sha256": "zz"}, ar, "malformed review"),
        }
        for name, (a, b, needle) in cases.items():
            with self.subTest(name):
                self.refused(self.write(self.receipt(reviews=[a, b])), needle)
        self.refused(self.write(self.receipt(reviews=[gk, gk])), "distinct")  # same output cannot be both reviews
        self.refused(self.write(self.receipt(reviews=[{**ar, "kind": "gatekeeper", "path": gk["path"], "sha256": gk["sha256"]}, ar][:1])),
                     "distinct")
        self.refused(self.write(self.receipt(reviews=[gk, {**gk, "path": "runs/gatekeeper.out"}])), "distinct")
        for bad in ([], None, "x", [gk, ar] * 6):
            with self.subTest(reviews=bad):
                self.refused(self.write(self.receipt(reviews=bad)), "no reviews")
        self.refused(self.write(self.receipt(reviews=[gk, "str"])), "malformed review")

    def test_review_content_must_be_an_approved_opus_verified_cli_success(self):
        cases = {
            "changes requested": review_json("**OUTCOME: CHANGES_REQUESTED.** no"),
            "blocked": review_json("OUTCOME: BLOCKED"),
            "no verdict": review_json("All good, I approve."),
            "prose only": review_json("The OUTCOME: APPROVED line would be here."),
            "contradictory": review_json("OUTCOME: APPROVED\nOUTCOME: BLOCKED"),
            "duplicate": review_json("OUTCOME: APPROVED\n**OUTCOME: APPROVED.**"),
            "is_error": review_json(is_error=True),
            "subtype": review_json(subtype="error_max_turns"),
            "sonnet primary": review_json(models=((SONNET, 1000),)),
            "sonnet side use": review_json(models=((OPUS, 1000), (SONNET, 1))),
            "haiku side use": review_json(models=((OPUS, 1000), ("claude-haiku-4-5", 3))),
            "no usage": review_json(models=()),
            "zero tokens": review_json(models=((OPUS, 0),), modelUsage={OPUS: {"inputTokens": 0, "outputTokens": 0}}),
            "limits only": review_json(modelUsage={OPUS: {"contextWindow": 200000, "maxOutputTokens": 32000}}),
            "unknown model": review_json(models=(("mystery-model", 1000),)),
            "result type": review_json(result=["OUTCOME: APPROVED"]),
        }
        for name, obj in cases.items():
            with self.subTest(name):
                self.ar = self.put_review("runs/activation.out", obj)
                self.refused(self.write(), "not an APPROVED, Opus-verified")
        self.ar = self.put_review("runs/activation.out", b"plain text, not json")
        self.refused(self.write(), "not CLI json")
        self.ar = self.put_review("runs/activation.out", b"[1]")
        self.refused(self.write(), "not an APPROVED")
        self.ar = self.put_review("runs/activation.out", b" " * (A.REVIEW_MAX_BYTES + 1))
        self.refused(self.write(), "regular file within")

    def test_canonical_model_names_the_family_when_present(self):
        obj = review_json(modelUsage={"alias-key": {"canonicalModel": OPUS, "inputTokens": 50, "outputTokens": 5}})
        self.ar = self.put_review("runs/activation.out", obj)
        self.verify(self.write())
        obj = review_json(modelUsage={OPUS: {"canonicalModel": SONNET, "inputTokens": 50, "outputTokens": 5}})
        self.ar = self.put_review("runs/activation.out", obj)
        self.refused(self.write(), "Opus-verified")

    def test_review_paths_cannot_leave_the_evidence_tree_or_follow_symlinks(self):
        outside = self.base / "outside.out"
        raw = json.dumps(review_json()).encode()
        outside.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        gk = self.receipt()["reviews"][0]
        for path in ("../outside.out", str(outside), "runs/../../outside.out", "", "."):
            with self.subTest(path=path):
                self.refused(self.write(self.receipt(reviews=[{**gk, "path": path, "sha256": digest}, self.receipt()["reviews"][1]])))
        (self.evidence / "runs" / "link.out").symlink_to(outside)
        self.refused(self.write(self.receipt(reviews=[{**gk, "path": "runs/link.out", "sha256": digest}, self.receipt()["reviews"][1]])))
        shutil.rmtree(self.evidence / "runs")  # a symlinked directory component cannot smuggle a file in either
        (self.base / "real-runs").mkdir()
        (self.base / "real-runs" / "gatekeeper.out").write_bytes(raw)
        (self.evidence / "runs").symlink_to(self.base / "real-runs")
        self.refused(self.write(self.receipt(reviews=[{**gk, "sha256": digest}, self.receipt()["reviews"][1]])), "escapes")

    def test_verification_writes_nothing(self):
        pin = self.write()

        def snapshot():
            return sorted((str(p.relative_to(self.base)), p.stat().st_mtime_ns, p.read_bytes()) for p in self.base.rglob("*")
                          if p.is_file() and ".git" not in p.parts)

        before = snapshot()
        self.verify(pin)
        self.assertEqual(snapshot(), before)

    def test_the_module_is_standard_library_only_and_never_touches_the_network(self):
        src = Path(A.__file__).read_text()
        imports = {ln.split()[1].split(".")[0] for ln in src.splitlines() if ln.startswith(("import ", "from "))}
        self.assertLessEqual(imports, {"hashlib", "json", "os", "re", "stat", "subprocess", "pathlib"})
        self.assertNotIn("socket", src)
        self.assertNotIn("urllib", src)


class RunnerIntegrationTests(TR.Env):
    """The runner keeps module order: a conditional prerequisite is satisfied only by a receipt that verifies right now."""

    COND = "**Status: ACCEPTED — FOUNDATION ONLY, CONDITIONAL ON OWN EXACT-SHA PUSH CI AND VERIFIED RECEIPT.**"

    def setUp(self):
        super().setUp()
        self.fx = Fixture()
        self.fx.tmp, self.fx.repo, self.fx.evidence, self.fx.base = self.tmp, self.repo, self.evidence, Path(self.tmp.name).resolve()
        self.fx.MODULE = "MOD-001"
        self.activation = subprocess.run(["git", "-C", str(self.repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.fx.activation = self.activation
        self.fx.gk = self.fx.put_review("runs/gatekeeper.out", review_json("OUTCOME: APPROVED"))
        self.fx.ar = self.fx.put_review("runs/activation.out", review_json())
        rec = self.repo / "knowledge/03-Modules/MOD-001/MOD-001.md"
        rec.parent.mkdir(parents=True)
        rec.write_text(f"# MOD-001\n\n{self.COND}\n")
        self.commit_all("conditional prerequisite")
        self.cfg = self.config(module_order=True)

    def pin(self, **over):
        pin = self.fx.write(self.fx.receipt(**over))
        self.cutover({"MOD-001": pin})
        return pin

    def cutover(self, pins):
        self.cfg.cutover_proof.write_text(json.dumps({"acceptance_receipts": pins}))

    def run_a(self):
        self.task("a")
        r = R.Runner(self.cfg)
        self.drain(r)
        return self.state()["a"]

    def test_a_conditional_module_with_a_valid_preserved_receipt_satisfies_the_dependent(self):
        self.pin()
        a = self.run_a()
        self.assertEqual((a["status"], len(self.calls())), ("COMPLETED", 1))
        self.assertEqual(R.module_record_state(self.repo, "MOD-001"), "conditional")  # and never becomes unconditional
        self.assertFalse(R.module_record_accepted(self.repo, "MOD-001"))
        self.assertIsNone(R.legacy_evidence_problem(self.cfg))

    def test_without_a_pin_or_with_an_altered_receipt_the_dependent_waits(self):
        self.fx.write(self.fx.receipt())
        self.cutover({})  # receipt is present but nobody pinned it
        a = self.run_a()
        self.assertEqual((a["status"], self.calls()), ("PENDING", []))
        self.assertIn("no preserved acceptance receipt verifies", a["waiting"])
        self.assertIn("is pinned in the cutover proof", a["waiting"])

    def test_a_receipt_is_reverified_on_every_evaluation_not_cached(self):
        self.pin()
        self.assertIsNone(R.prereq_problem(self.repo, "MOD-001", self.cfg))
        (self.evidence / "runs" / "activation.out").write_bytes(json.dumps(review_json(models=((SONNET, 9),))).encode())
        why = R.prereq_problem(self.repo, "MOD-001", self.cfg)
        self.assertIn("recorded sha256", why)
        self.assertIn("MOD-001", why)

    def test_a_stale_receipt_after_history_changes_is_not_a_prerequisite(self):
        self.pin(activation_sha="3" * 40, ci={**self.fx.receipt()["ci"], "head_sha": "3" * 40},
                 reviews=[{**r, "activation_sha": "3" * 40} for r in self.fx.receipt()["reviews"]])
        self.assertIn("not an ancestor", R.prereq_problem(self.repo, "MOD-001", self.cfg))

    def test_unconditional_acceptance_needs_no_receipt_and_a_missing_cfg_never_satisfies_a_conditional(self):
        self.assertIn("conditionally", R.prereq_problem(self.repo, "MOD-001"))
        rec = self.repo / "knowledge/03-Modules/MOD-001/MOD-001.md"
        rec.write_text("# MOD-001\n\n**Status: ACCEPTED — LEAN FOUNDATION.**\n")
        self.commit_all("unconditional")
        self.assertIsNone(R.prereq_problem(self.repo, "MOD-001", self.cfg))
        self.assertIsNone(R.prereq_problem(self.repo, "MOD-001"))

    def test_a_valid_receipt_does_not_block_forward_repair_of_failed_ci(self):
        self.pin()
        spec = {"id": "fix", "module": "MOD-001", "role": "implement", "title": "repair failed exact-SHA CI", "prompt": "forward repair",
                "allowed_paths": ["backend/"], "verify_cmd": [sys.executable, "-m", "unittest", "tests.test_ok"]}
        self.assertIsNone(R.proposal_problem(self.cfg, spec))

    def test_completing_tasks_never_creates_acceptance(self):
        self.cutover({})
        self.cfg.module_order = False
        self.task("a")
        self.drain()
        self.assertEqual(self.state()["a"]["status"], "COMPLETED")
        self.assertEqual(R.module_record_state(self.repo, "MOD-002"), "not-accepted")
        self.assertEqual(sorted(p.name for p in (self.evidence / "acceptances").iterdir()), [])
        self.assertIsNotNone(R.prereq_problem(self.repo, "MOD-002", self.cfg))

    def test_the_dashboard_shows_a_verified_receipt_as_conditional_never_accepted(self):
        import dashboard
        self.pin()
        rec = dashboard.module_records(self.repo, self.cfg)["MOD-001"]
        self.assertEqual((rec["accepted"], rec["recorded_accepted"], rec["conditional"]), (False, False, True))
        self.assertTrue(rec["receipt"]["verified"])
        self.assertIn("reverifies", rec["discrepancy"])
        (self.evidence / "acceptances" / "MOD-001.json").write_bytes(b"{}")
        rec = dashboard.module_records(self.repo, self.cfg)["MOD-001"]
        self.assertFalse(rec["receipt"]["verified"])
        self.assertNotIn("reverifies", rec["discrepancy"])
        self.assertFalse(dashboard.module_records(self.repo)["MOD-001"]["receipt"]["verified"])  # no cfg: never claimed
        state = dashboard.build_state({"tasks": []}, self.repo, self.cfg)
        self.assertEqual((state["accepted_count"], state["recorded_accepted_count"]), (0, 0))


class LegacyEvidenceTreeTests(TR.Env):
    """Mandatory read-only evidence tree: absent, unsafe or altered copies refuse start and dispatch."""

    def pinned(self, module="MOD-002"):
        raw = json.dumps({"module": module}).encode()
        (self.evidence / "acceptances" / f"{module}.json").write_bytes(raw)
        pin = hashlib.sha256(raw).hexdigest()
        self.cfg.cutover_proof.write_text(json.dumps({"acceptance_receipts": {module: pin}}))
        return raw, pin

    def test_the_fixture_tree_is_accepted_and_host_problem_includes_it(self):
        self.assertIsNone(R.legacy_evidence_problem(self.cfg))
        self.cfg.legacy_evidence = None
        self.assertIn("LEGACY_EVIDENCE", R.host_problem(self.cfg))
        self.assertIn("LEGACY_EVIDENCE", R.legacy_evidence_problem(self.config(legacy_evidence=None)))

    def test_a_relative_missing_file_or_symlinked_tree_is_refused(self):
        for bad in ("evidence", str(self.base_dir() / "nope"), str(self.legacy_path)):
            with self.subTest(bad=bad):
                self.cfg.legacy_evidence = Path(bad)
                self.assertIn("LEGACY_EVIDENCE", R.legacy_evidence_problem(self.cfg))
        link = self.base_dir() / "evidence-link"
        link.symlink_to(self.evidence)
        self.cfg.legacy_evidence = link
        self.assertIn("symlink", R.legacy_evidence_problem(self.cfg))

    def base_dir(self):
        return self.evidence.parent

    def test_an_evidence_tree_inside_the_checkout_or_runner_home_or_group_writable_is_refused(self):
        for where in (self.repo, self.home):
            inside = where / "evidence"
            (inside / "acceptances").mkdir(parents=True)
            (inside / "runs").mkdir()
            self.cfg.legacy_evidence = inside
            self.assertIn("agent-writable", R.legacy_evidence_problem(self.cfg))
        self.cfg.legacy_evidence = self.evidence
        (self.evidence / "reviews").mkdir()
        (self.evidence / "reviews" / "r.out").write_text("x")
        for sub in (self.evidence, self.evidence / "reviews", self.evidence / "reviews" / "r.out"):
            mode = sub.stat().st_mode & 0o777
            sub.chmod(0o775 if sub.is_dir() else 0o664)
            self.assertIn("group/other-writable", R.legacy_evidence_problem(self.cfg))
            sub.chmod(mode)
        self.assertIsNone(R.legacy_evidence_problem(self.cfg))
        (self.evidence / "reviews" / "l").symlink_to(self.legacy_path)
        self.assertIn("symlink", R.legacy_evidence_problem(self.cfg))
        (self.evidence / "reviews" / "l").unlink()
        shutil.rmtree(self.evidence / "acceptances")
        self.assertIn("acceptances", R.legacy_evidence_problem(self.cfg))

    def test_every_pinned_receipt_must_be_present_byte_for_byte_or_start_is_refused(self):
        raw, pin = self.pinned()
        self.assertIsNone(R.legacy_evidence_problem(self.cfg))
        (self.evidence / "acceptances" / "MOD-002.json").write_bytes(raw + b"\n")
        self.assertIn("byte-for-byte", R.legacy_evidence_problem(self.cfg))
        self.assertIn("byte-for-byte", R.host_problem(self.cfg))
        (self.evidence / "acceptances" / "MOD-002.json").unlink()
        self.assertIn("LEGACY_EVIDENCE", R.legacy_evidence_problem(self.cfg))
        (self.evidence / "acceptances" / "MOD-002.json").write_bytes(raw)
        self.assertIsNone(R.legacy_evidence_problem(self.cfg))

    def test_malformed_pins_never_count_as_pins(self):
        for bad in ({"acceptance_receipts": {"MOD-1": "a" * 64}}, {"acceptance_receipts": {"MOD-001": "short"}},
                    {"acceptance_receipts": []}, {}, []):
            self.cfg.cutover_proof.write_text(json.dumps(bad))
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                R.receipt_pins(self.cfg)
            self.assertIsNotNone(R.receipt_problem(self.cfg, "MOD-001"))
        self.cfg.cutover_proof.write_bytes(b"\xff not json")
        self.assertIsNotNone(R.receipt_problem(self.cfg, "MOD-001"))

    def test_the_runner_refuses_to_start_without_the_evidence_tree(self):
        self.cfg.legacy_evidence = None
        err = __import__("io").StringIO()
        with mock.patch.object(sys, "stderr", err):
            self.assertEqual(R.Runner(self.cfg).run(), R.EXIT_BOUNDARY)
        self.assertIn("LEGACY_EVIDENCE", err.getvalue())
        self.assertFalse((self.home / "v2" / "state.json").exists())  # nothing touched on a refused start

    def test_the_command_line_names_the_tree(self):
        with mock.patch.object(R, "Runner") as runner:
            runner.return_value.run.return_value = 0
            R.main(["--home", str(self.home), "--repo", str(self.repo), "--legacy-evidence", str(self.evidence), "run"])
        self.assertEqual(runner.call_args[0][0].legacy_evidence, self.evidence)


@unittest.skipUnless(os.environ.get("VEYRO_REAL_ACCEPTANCES"), "set VEYRO_REAL_ACCEPTANCES to a COPY of the v1 acceptances/ tree and the review outputs it names")
class RealCopiedReceiptTests(unittest.TestCase):
    """Smoke test against a byte-for-byte COPY of the real v1 receipts (never the live home). Pins are computed from the copy,
    so this proves the copied bytes verify against `VEYRO_REAL_REPO` (default: this checkout), not that the copy is the original."""

    def test_the_preserved_prerequisite_receipts_verify(self):
        tree = Path(os.environ["VEYRO_REAL_ACCEPTANCES"])
        repo = Path(os.environ.get("VEYRO_REAL_REPO") or R.REPO)
        for module in ("MOD-001", "MOD-002", "MOD-003"):
            with self.subTest(module=module):
                out = A.verify_receipt(tree, repo, module, A.receipt_sha256(tree, module))
                self.assertEqual(len(out["reviews"]), 2)


if __name__ == "__main__":
    unittest.main()
