"""End-to-end CLI tests (subprocess, real command lines)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "fixtures")


def run_cli(*args, cwd=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "qnxkit", *args],
        cwd=cwd or ROOT, env=env, capture_output=True, text=True)


class TestCliBasics(unittest.TestCase):
    def test_version(self):
        proc = run_cli("--version")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("qnxkit 0.1.0", proc.stdout)

    def test_no_args_errors(self):
        proc = run_cli()
        self.assertNotEqual(proc.returncode, 0)


class TestCliBuildfile(unittest.TestCase):
    def test_check_official_fixture(self):
        proc = run_cli("buildfile", "check",
                       os.path.join(FIXTURES, "qemu-x86_64.build"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK: no issues.", proc.stdout)

    def test_check_bad_file_fails(self):
        with tempfile.NamedTemporaryFile("w", suffix=".build",
                                         delete=False) as fh:
            fh.write("[uid=5] [gid=5] foo\n")
            path = fh.name
        try:
            proc = run_cli("buildfile", "check", path)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("split-attrs", proc.stdout)
        finally:
            os.unlink(path)

    def test_check_json(self):
        proc = run_cli("buildfile", "check", "--json",
                       os.path.join(FIXTURES, "qemu-x86_64.build"))
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(data["summary"]["bootstrap"])

    def test_new_qemu(self):
        proc = run_cli("buildfile", "new", "--target", "qemu-x86_64",
                       "--app", "hello_qnx")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("startup-x86", proc.stdout)
        self.assertIn("hello_qnx", proc.stdout)

    def test_new_bad_target(self):
        proc = run_cli("buildfile", "new", "--target", "riscv",
                       "--app", "x")
        self.assertEqual(proc.returncode, 2)


class TestCliToolchain(unittest.TestCase):
    def test_check_qt_fixture(self):
        proc = run_cli("toolchain", "check",
                       os.path.join(FIXTURES, "qnx-toolchain-aarch64le.cmake"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_new_aarch64le(self):
        proc = run_cli("toolchain", "new", "--arch", "aarch64le")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("gcc_ntoaarch64le", proc.stdout)

    def test_new_x86_64(self):
        proc = run_cli("toolchain", "new", "--arch", "x86_64")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("gcc_ntox86_64", proc.stdout)


class TestCliAnalyze(unittest.TestCase):
    def test_qnx_sample_clean(self):
        proc = run_cli("analyze", os.path.join(FIXTURES, "hello-qnx.c"))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_linux_sample_fails(self):
        proc = run_cli("analyze", os.path.join(FIXTURES, "linux-only.c"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("linux-epoll", proc.stdout)
        self.assertIn("ionotify", proc.stdout)


class TestCliIfs(unittest.TestCase):
    def test_build_and_inspect_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "root")
            os.makedirs(root)
            with open(os.path.join(root, "hello.txt"), "w") as fh:
                fh.write("hello ifs")
            image = os.path.join(tmp, "test.ifs")
            proc = run_cli("ifs", "build", "--root", root, "--output", image)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(os.path.exists(image))
            proc = run_cli("ifs", "inspect", image)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("hello.txt", proc.stdout)
            self.assertIn("Checksums:", proc.stdout)
            self.assertIn("(valid)", proc.stdout)

    def test_inspect_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "root")
            os.makedirs(root)
            with open(os.path.join(root, "a.txt"), "w") as fh:
                fh.write("a")
            image = os.path.join(tmp, "test.ifs")
            run_cli("ifs", "build", "--root", root, "--output", image)
            proc = run_cli("ifs", "inspect", "--json", image)
            self.assertEqual(proc.returncode, 0)
            data = json.loads(proc.stdout)
            self.assertEqual(data["image_header"]["mountpoint"], "/")
            self.assertEqual(data["entries"][1]["path"], "a.txt")
            self.assertTrue(data["image_checksum"][2])

    def test_build_zlib(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "root")
            os.makedirs(root)
            with open(os.path.join(root, "a.txt"), "w") as fh:
                fh.write("zlib " * 100)
            image = os.path.join(tmp, "test.ifs")
            proc = run_cli("ifs", "build", "--root", root, "--output", image,
                           "--compress", "zlib")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            proc = run_cli("ifs", "inspect", "--json", image)
            data = json.loads(proc.stdout)
            self.assertEqual(data["startup"]["compression"], "zlib")


class TestCliCheck(unittest.TestCase):
    def test_sample_project_scores_100(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Build a mini project from the generators + fixture source.
            shutil.copy(os.path.join(FIXTURES, "hello-qnx.c"),
                        os.path.join(tmp, "main.c"))
            proc = run_cli("buildfile", "new", "--target", "qemu-x86_64",
                           "--app", "hello_qnx", "--output",
                           os.path.join(tmp, "image.build"))
            self.assertEqual(proc.returncode, 0)
            proc = run_cli("toolchain", "new", "--arch", "aarch64le",
                           "--output", os.path.join(tmp, "qnx.cmake"))
            self.assertEqual(proc.returncode, 0)
            proc = run_cli("check", tmp)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("QNX readiness: 100/100", proc.stdout)

    def test_empty_dir_scores_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("check", tmp)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("QNX readiness: 40/100", proc.stdout)
            self.assertIn("no-qnx-evidence", proc.stdout)


if __name__ == "__main__":
    unittest.main()
