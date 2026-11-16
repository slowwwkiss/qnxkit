"""Tests for the QNX CMake toolchain generator and checker."""

import os
import unittest

from qnxkit import toolchain

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


class TestToolchainFixtures(unittest.TestCase):
    def test_qt_production_toolchain_is_clean(self):
        # Qt's real qnx-toolchain-aarch64le.cmake must pass with no errors.
        result = toolchain.check_toolchain(
            fixture("qnx-toolchain-aarch64le.cmake"),
            "qnx-toolchain-aarch64le.cmake")
        self.assertEqual(result.errors, [], [str(i) for i in result.issues])
        self.assertEqual(result.summary["arch"], "aarch64le")

    def test_generated_aarch64le_is_clean(self):
        text = toolchain.generate_toolchain("aarch64le")
        result = toolchain.check_toolchain(text, "generated.cmake")
        self.assertEqual(result.errors, [], [str(i) for i in result.issues])
        self.assertEqual(result.summary["arch"], "aarch64le")
        self.assertIn("gcc_ntoaarch64le", text)

    def test_generated_x86_64_is_clean(self):
        text = toolchain.generate_toolchain("x86_64")
        result = toolchain.check_toolchain(text, "generated.cmake")
        self.assertEqual(result.errors, [], [str(i) for i in result.issues])
        self.assertEqual(result.summary["arch"], "x86_64")
        self.assertIn("gcc_ntox86_64", text)

    def test_unknown_arch_rejected(self):
        with self.assertRaises(ValueError):
            toolchain.generate_toolchain("riscv64")


class TestToolchainValidation(unittest.TestCase):
    def test_missing_system_name(self):
        result = toolchain.check_toolchain(
            "set(CMAKE_C_COMPILER qcc)\n", "t.cmake")
        self.assertTrue(any(i.code == "no-system-name"
                            for i in result.errors))

    def test_wrong_system_name(self):
        result = toolchain.check_toolchain(
            "set(CMAKE_SYSTEM_NAME Linux)\nset(CMAKE_C_COMPILER qcc)\n",
            "t.cmake")
        self.assertTrue(any(i.code == "wrong-system-name"
                            for i in result.errors))

    def test_wrong_c_compiler(self):
        result = toolchain.check_toolchain(
            "set(CMAKE_SYSTEM_NAME QNX)\nset(CMAKE_C_COMPILER gcc)\n",
            "t.cmake")
        self.assertTrue(any(i.code == "wrong-c-compiler"
                            for i in result.errors))

    def test_arch_mismatch(self):
        text = (
            "set(CMAKE_SYSTEM_NAME QNX)\n"
            "set(CMAKE_SYSTEM_PROCESSOR aarch64le)\n"
            "set(CMAKE_C_COMPILER qcc)\n"
            "set(CMAKE_C_COMPILER_TARGET gcc_ntox86_64)\n"
            "set(CMAKE_CXX_COMPILER q++)\n"
            "set(CMAKE_CXX_COMPILER_TARGET gcc_ntox86_64)\n"
            "set(CMAKE_SYSROOT $ENV{QNX_TARGET})\n")
        result = toolchain.check_toolchain(text, "t.cmake")
        self.assertTrue(any(i.code == "arch-mismatch"
                            for i in result.errors))

    def test_unknown_target(self):
        text = (
            "set(CMAKE_SYSTEM_NAME QNX)\n"
            "set(CMAKE_C_COMPILER qcc)\n"
            "set(CMAKE_C_COMPILER_TARGET gcc_ntoriscv)\n"
            "set(CMAKE_CXX_COMPILER q++)\n"
            "set(CMAKE_CXX_COMPILER_TARGET gcc_ntoriscv)\n")
        result = toolchain.check_toolchain(text, "t.cmake")
        self.assertTrue(any(i.code == "unknown-target"
                            for i in result.errors))

    def test_missing_sysroot_is_warning(self):
        text = toolchain.generate_toolchain("aarch64le")
        text = text.replace("set(CMAKE_SYSROOT $ENV{QNX_TARGET})\n", "")
        result = toolchain.check_toolchain(text, "t.cmake")
        self.assertFalse(result.errors)
        self.assertTrue(any(i.code == "no-sysroot" for i in result.warnings))


if __name__ == "__main__":
    unittest.main()
