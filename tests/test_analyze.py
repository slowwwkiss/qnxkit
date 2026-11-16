"""Tests for the Linux-only API analyzer."""

import os
import unittest

from qnxkit import analyze

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


class TestAnalyzerFixtures(unittest.TestCase):
    def test_qnx_sample_is_clean(self):
        # The QNX message-passing demo must have zero portability findings.
        result = analyze.analyze_text(fixture("hello-qnx.c"), "hello-qnx.c")
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.qnx_api_total, 6)
        self.assertEqual(result.qnx_api_hits["ChannelCreate"], 1)
        self.assertEqual(result.qnx_api_hits["MsgReceive"], 1)
        self.assertEqual(result.qnx_api_hits["MsgReply"], 1)
        self.assertEqual(result.qnx_api_hits["name_attach"], 1)
        self.assertEqual(result.qnx_api_hits["name_open"], 1)
        self.assertEqual(result.qnx_api_hits["MsgSend"], 1)

    def test_linux_only_sample(self):
        result = analyze.analyze_text(fixture("linux-only.c"),
                                      "linux-only.c")
        # 27 errors: 9 header findings + 18 code findings.
        self.assertEqual(len(result.errors), 27,
                         [f"{f.rule}:{f.line}" for f in result.errors])
        self.assertEqual(len(result.warnings), 2)
        by_rule = {}
        for f in result.findings:
            by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
        self.assertEqual(by_rule["linux-epoll"], 3)
        self.assertEqual(by_rule["linux-epoll-header"], 1)
        self.assertEqual(by_rule["linux-inotify"], 3)
        self.assertEqual(by_rule["linux-eventfd"], 1)
        self.assertEqual(by_rule["linux-timerfd"], 1)
        self.assertEqual(by_rule["linux-memfd"], 1)
        self.assertEqual(by_rule["linux-io-uring"], 2)
        self.assertEqual(by_rule["linux-prctl"], 1)
        self.assertEqual(by_rule["linux-clone"], 1)
        self.assertEqual(by_rule["linux-sched-affinity"], 3)
        self.assertEqual(by_rule["linux-kernel-headers"], 1)
        self.assertEqual(by_rule["proc-self"], 1)
        self.assertEqual(by_rule["raw-syscall"], 1)
        self.assertEqual(by_rule["glibc-guard"], 2)
        # The file has no signalfd / kqueue use.
        self.assertNotIn("linux-signalfd", by_rule)
        self.assertNotIn("bsd-kqueue", by_rule)
        # Comment and string mentions of epoll must NOT produce findings.
        self.assertEqual(by_rule.get("linux-epoll", 0), 3)


class TestStripper(unittest.TestCase):
    def test_comment_mention_is_ignored(self):
        text = "/* epoll_create(0); */\nint main(void) { return 0; }\n"
        result = analyze.analyze_text(text, "t.c")
        self.assertEqual(result.findings, [])

    def test_string_mention_is_ignored(self):
        text = ('const char *s = "epoll_create is Linux-only";\n'
                "int main(void) { return 0; }\n")
        result = analyze.analyze_text(text, "t.c")
        self.assertEqual(result.findings, [])

    def test_line_comment_mention_is_ignored(self):
        text = "// inotify_init1(0)\nint main(void) { return 0; }\n"
        result = analyze.analyze_text(text, "t.c")
        self.assertEqual(result.findings, [])

    def test_code_finding_survives(self):
        text = "int main(void) { int fd = epoll_create1(0); return fd; }\n"
        result = analyze.analyze_text(text, "t.c")
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0].rule, "linux-epoll")

    def test_qnx_suggestion_names_ionotify(self):
        text = "int fd = epoll_create1(0);\n"
        result = analyze.analyze_text(text, "t.c")
        self.assertIn("ionotify", result.errors[0].suggestion)


if __name__ == "__main__":
    unittest.main()
