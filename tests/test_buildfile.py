"""Tests for the mkifs buildfile parser, validator and generator."""

import os
import unittest

from qnxkit import buildfile

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


class TestBuildfileFixtures(unittest.TestCase):
    def test_official_qemu_buildfile_is_clean(self):
        # The official QNX walkthrough buildfile (FTBU #2) must pass.
        result = buildfile.check_buildfile(
            fixture("qemu-x86_64.build"), "qemu-x86_64.build")
        self.assertEqual(result.errors, [], [str(i) for i in result.issues])
        self.assertTrue(result.summary["bootstrap"])
        self.assertTrue(result.summary["script"])

    def test_generated_qemu_buildfile_is_clean(self):
        text = buildfile.generate_buildfile("qemu-x86_64", "hello_qnx")
        result = buildfile.check_buildfile(text, "generated.build")
        self.assertEqual(result.errors, [], [str(i) for i in result.issues])
        self.assertIn("startup-x86", text)
        self.assertIn("procnto-smp-instr", text)
        self.assertIn("hello_qnx", text)

    def test_generated_rpi4_buildfile_is_clean(self):
        text = buildfile.generate_buildfile("rpi4", "hello_qnx")
        result = buildfile.check_buildfile(text, "generated.build")
        self.assertEqual(result.errors, [], [str(i) for i in result.issues])
        self.assertIn("startup-rpi4", text)
        self.assertIn("aarch64le", text)

    def test_unknown_target_rejected(self):
        with self.assertRaises(ValueError):
            buildfile.generate_buildfile("qemu-riscv", "app")


class TestBuildfileValidation(unittest.TestCase):
    def test_split_attribute_groups_are_an_error(self):
        # The reference explicitly calls [uid=5] [gid=5] the wrong way.
        result = buildfile.check_buildfile(
            "[uid=5] [gid=5] filename\n", "t.build")
        self.assertTrue(any(i.code == "split-attrs" for i in result.errors))

    def test_combined_attribute_group_ok(self):
        result = buildfile.check_buildfile(
            "[uid=5 gid=5 perms=0666] filename\n", "t.build")
        self.assertFalse(any(i.code == "split-attrs" for i in result.errors))

    def test_unknown_attribute(self):
        result = buildfile.check_buildfile("[frobnicate=1] foo\n", "t.build")
        self.assertTrue(any(i.code == "unknown-attr" for i in result.errors))

    def test_boolean_attribute_with_value(self):
        result = buildfile.check_buildfile("[script=1] foo\n", "t.build")
        self.assertTrue(any(i.code == "bad-attr" for i in result.errors))

    def test_bad_perms(self):
        result = buildfile.check_buildfile("[perms=banana] foo\n", "t.build")
        self.assertTrue(any(i.code == "bad-attr-value" for i in result.errors))

    def test_symbolic_perms_ok(self):
        result = buildfile.check_buildfile("[perms=a+xr] foo\n", "t.build")
        self.assertFalse(any(i.code == "bad-attr-value" for i in result.errors))

    def test_unknown_type(self):
        result = buildfile.check_buildfile("[type=weird] foo\n", "t.build")
        self.assertTrue(any(i.code == "bad-attr-value" for i in result.errors))

    def test_link_without_source(self):
        result = buildfile.check_buildfile(
            "[type=link] /dev/console\n", "t.build")
        self.assertTrue(any(i.code == "link-without-source"
                            for i in result.errors))

    def test_duplicate_target(self):
        result = buildfile.check_buildfile("foo\nfoo\n", "t.build")
        self.assertTrue(any(i.code == "duplicate-target"
                            for i in result.errors))

    def test_unclosed_inline(self):
        result = buildfile.check_buildfile(
            "[+script] .script = {\n    hello\n", "t.build")
        self.assertTrue(any(i.code == "unclosed-inline"
                            for i in result.errors))

    def test_bootstrap_first_entry_warning(self):
        text = ("[virtual=x86_64,multiboot] boot = {\n"
                "    procnto-smp-instr\n"
                "    startup-x86\n"
                "}\n")
        result = buildfile.check_buildfile(text, "t.build")
        self.assertTrue(any(i.code == "bootstrap-order"
                            for i in result.warnings))

    def test_no_bootstrap_warning(self):
        result = buildfile.check_buildfile("libc.so\n", "t.build")
        self.assertTrue(any(i.code == "no-bootstrap" for i in result.warnings))
        self.assertTrue(any(i.code == "no-script" for i in result.warnings))

    def test_sticky_attributes_apply(self):
        text = "[perms=0666]\nfoo\nbar\n"
        bf, _ = buildfile.parse_buildfile(text, "t.build")
        self.assertEqual(bf.entries[0].attrs.get("perms"), "0666")
        self.assertEqual(bf.entries[1].attrs.get("perms"), "0666")

    def test_conditional_attribute(self):
        text = "[?perms=0666]\n[perms=0600] foo\nbar\n"
        bf, _ = buildfile.parse_buildfile(text, "t.build")
        self.assertEqual(bf.entries[0].attrs.get("perms"), "0600")
        self.assertEqual(bf.entries[1].attrs.get("perms"), "0666")

    def test_comments_ignored(self):
        text = "# a comment\nfoo # trailing comment\n"
        bf, result = buildfile.parse_buildfile(text, "t.build")
        self.assertEqual(len(bf.entries), 1)
        self.assertEqual(bf.entries[0].target, "foo")

    def test_inline_contents_not_parsed(self):
        text = ("[+script] .script = {\n"
                "    # not a comment inside inline files\n"
                "    display_msg \"hi # there\"\n"
                "}\n")
        bf, result = buildfile.parse_buildfile(text, "t.build")
        self.assertEqual(len(bf.entries), 1)
        self.assertIn("# not a comment", bf.entries[0].inline)

    def test_unknown_cpu_warning(self):
        text = ("[virtual=riscv64,multiboot] boot = {\n"
                "    startup-x86\n"
                "}\n")
        result = buildfile.check_buildfile(text, "t.build")
        self.assertTrue(any(i.code == "unknown-cpu" for i in result.warnings))


if __name__ == "__main__":
    unittest.main()
