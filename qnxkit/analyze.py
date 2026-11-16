"""Linux-to-QNX portability analyzer for C/C++ sources.

Flags Linux-only APIs that have no counterpart in the QNX 8.0 C
library, and points at the QNX-native alternative. Every rule is
grounded in the QNX 8.0 documentation:

* ``epoll`` — QNX has no epoll(); the ``ionotify()`` reference says
  "This function corresponds to the Linux epoll() function and BSD's
  kqueue(). The QNX Neutrino implementations of select() and poll()
  are built on top of ionotify()."
* ``inotify`` / ``eventfd`` / ``signalfd`` / ``timerfd`` / ``memfd``
  / ``io_uring`` / ``kqueue`` / ``prctl`` / ``clone`` /
  ``sched_setaffinity`` — Linux- (or BSD-) specific facilities with
  no entry in the QNX Library Reference; the QNX alternatives named
  here are QNX-documented calls (``ionotify()``, ``timer_create()``,
  ``shm_open()``, POSIX AIO, ``sigwait()``, ``ThreadCtl()`` with
  ``_NTO_TCTL_RUNMASK``, ``pthread_create()``).
* ``#include <linux/...>`` — Linux kernel headers do not exist on QNX.
* ``__GLIBC__`` — QNX libc is not glibc; QNX code is guarded with
  ``__QNX__`` / ``__QNXNTO__``.
* ``/proc/self/exe`` and ``/proc/self/maps`` — not present in the
  QNX ``/proc`` filesystem.
* ``syscall(SYS_...)`` — raw Linux syscall numbers do not exist on QNX.

Comments and string literals are stripped before matching, so a
mention in a comment does not raise a finding. The analyzer also
counts QNX-native API usage (``ChannelCreate``, ``MsgSend``,
``name_attach``, ``ThreadCtl``, ...) as positive evidence that the
code genuinely targets QNX.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import CheckResult

# (rule id, severity, regex, message, suggestion)
RULES = [
    ("linux-epoll", "error",
     r"\b(epoll_create1?|epoll_ctl|epoll_wait|epoll_pwait2?)\s*\(",
     "epoll() has no QNX counterpart",
     "use ionotify() — the QNX equivalent of epoll() — or poll()/select()"),
    ("linux-epoll-header", "error",
     r"#\s*include\s*<\s*sys/epoll\.h\s*>",
     "#include <sys/epoll.h> — epoll.h does not exist on QNX",
     "use ionotify() — the QNX equivalent of epoll() — or poll()/select()"),
    ("linux-inotify", "error",
     r"\b(inotify_init1?|inotify_add_watch|inotify_rm_watch)\s*\(",
     "inotify() has no QNX counterpart",
     "watch files with ionotify() or poll() the directory"),
    ("linux-inotify-header", "error",
     r"#\s*include\s*<\s*sys/inotify\.h\s*>",
     "#include <sys/inotify.h> — inotify.h does not exist on QNX",
     "watch files with ionotify() or poll() the directory"),
    ("linux-eventfd", "error",
     r"\b(eventfd|eventfd_read|eventfd_write)\s*\(",
     "eventfd() has no QNX counterpart",
     "signal between threads with a QNX channel + pulse "
     "(ChannelCreate/MsgSendPulse) or a pipe()"),
    ("linux-eventfd-header", "error",
     r"#\s*include\s*<\s*sys/eventfd\.h\s*>",
     "#include <sys/eventfd.h> — eventfd.h does not exist on QNX",
     "signal between threads with a QNX channel + pulse or a pipe()"),
    ("linux-signalfd", "error",
     r"\b(signalfd|signalfd4)\s*\(",
     "signalfd() has no QNX counterpart",
     "wait for signals with sigwait() in a dedicated thread"),
    ("linux-signalfd-header", "error",
     r"#\s*include\s*<\s*sys/signalfd\.h\s*>",
     "#include <sys/signalfd.h> — signalfd.h does not exist on QNX",
     "wait for signals with sigwait() in a dedicated thread"),
    ("linux-timerfd", "error",
     r"\b(timerfd_create|timerfd_gettime|timerfd_settime)\s*\(",
     "timerfd() has no QNX counterpart",
     "use POSIX timer_create()/timer_settime(), which QNX libc provides"),
    ("linux-timerfd-header", "error",
     r"#\s*include\s*<\s*sys/timerfd\.h\s*>",
     "#include <sys/timerfd.h> — timerfd.h does not exist on QNX",
     "use POSIX timer_create()/timer_settime(), which QNX libc provides"),
    ("linux-memfd", "error",
     r"\bmemfd_create\s*\(",
     "memfd_create() has no QNX counterpart",
     "use shm_open() (POSIX shared memory, provided by QNX libc)"),
    ("linux-memfd-header", "error",
     r"#\s*include\s*<\s*sys/memfd\.h\s*>",
     "#include <sys/memfd.h> — memfd.h does not exist on QNX",
     "use shm_open() (POSIX shared memory, provided by QNX libc)"),
    ("linux-io-uring", "error",
     r"\b(io_uring_setup|io_uring_enter|io_uring_register|io_uring_queue_init|io_uring_queue_exit)\s*\(",
     "io_uring has no QNX counterpart",
     "use POSIX AIO (aio_read()/aio_write()) or a worker thread pool"),
    ("linux-io-uring-header", "error",
     r"#\s*include\s*<\s*(liburing\.h|linux/io_uring\.h)\s*>",
     "io_uring headers do not exist on QNX",
     "use POSIX AIO (aio_read()/aio_write()) or a worker thread pool"),
    ("bsd-kqueue", "error",
     r"\b(kqueue|kevent)\s*\(",
     "kqueue()/kevent() are BSD-only",
     "use ionotify() — the QNX equivalent of kqueue() — or poll()"),
    ("bsd-kqueue-header", "error",
     r"#\s*include\s*<\s*sys/event\.h\s*>",
     "#include <sys/event.h> (kqueue) does not exist on QNX",
     "use ionotify() — the QNX equivalent of kqueue() — or poll()"),
    ("linux-prctl", "error",
     r"\bprctl\s*\(",
     "prctl() has no QNX counterpart",
     "control threads/processes with ThreadCtl() and procmgr_*()"),
    ("linux-prctl-header", "error",
     r"#\s*include\s*<\s*sys/prctl\.h\s*>",
     "#include <sys/prctl.h> — prctl.h does not exist on QNX",
     "control threads/processes with ThreadCtl() and procmgr_*()"),
    ("linux-clone", "error",
     r"\bclone3?\s*\(",
     "clone() has no QNX counterpart",
     "create threads with pthread_create() or processes with spawn()"),
    ("linux-sched-affinity", "error",
     r"\b(sched_setaffinity|sched_getaffinity|CPU_SET|CPU_ZERO|CPU_ISSET)\b",
     "sched_setaffinity()/CPU_SET have no QNX counterpart",
     "set a thread runmask with ThreadCtl(_NTO_TCTL_RUNMASK, ...)"),
    ("linux-kernel-headers", "error",
     r"#\s*include\s*<\s*linux/[^>]+>",
     "Linux kernel headers (<linux/...>) do not exist on QNX",
     "use the QNX/POSIX headers (<sys/neutrino.h>, <pthread.h>, ...)"),
    ("glibc-guard", "warning",
     r"\b(__GLIBC__|__GLIBC_MINOR__)\b",
     "__GLIBC__ guards do not apply: QNX libc is not glibc",
     "guard QNX-specific code with __QNX__ / __QNXNTO__ instead"),
    ("proc-self", "error",
     r"/proc/self/(exe|maps|fd|task)\b",
     "/proc/self/exe, /proc/self/maps and friends are not in the QNX /proc",
     "resolve the executable path from argv[0] or the QNX process manager"),
    ("raw-syscall", "error",
     r"\bsyscall\s*\(\s*SYS_[A-Za-z0-9_]+\b",
     "raw Linux syscall numbers (SYS_*) do not exist on QNX",
     "call the libc function instead of syscall(SYS_...)"),
    ("raw-syscall-header", "error",
     r"#\s*include\s*<\s*sys/syscall\.h\s*>",
     "#include <sys/syscall.h> — raw syscall numbers do not exist on QNX",
     "call the libc function instead of syscall(SYS_...)"),
]

# QNX-native APIs counted as positive targeting evidence.
QNX_APIS = [
    "ChannelCreate", "ChannelDestroy", "ConnectAttach", "ConnectDetach",
    "MsgSend", "MsgSendv", "MsgReceive", "MsgReply", "MsgError",
    "MsgSendPulse", "MsgRegisterEvent",
    "name_attach", "name_open", "name_close",
    "ThreadCtl", "ThreadCreate",
    "procmgr_daemon", "procmgr_session", "procmgr_getsid",
    "SchedSet", "SchedGet", "SchedYield",
    "ClockCycles", "ClockPeriod", "ClockAdjust",
    "TimerTimeout", "TimerCreate", "timer_create",
    "ionotify", "InterruptAttach", "InterruptAttachEvent",
    "dispatch_create", "dispatch_context_alloc", "resmgr_attach",
    "mmap_device_io", "mmap_device_memory",
    "shm_open", "SyncMutexLock", "SyncCondvarWait",
    "slogf", "TraceEvent",
]

_QNX_API_RE = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in QNX_APIS) + r")\b")


def strip_comments_and_strings(text: str) -> str:
    """Blank out comments and string/char literals, keeping line numbers."""
    out = []
    i = 0
    n = len(text)
    state = "code"
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                state = "line-comment"
                out.append("  ")
                i += 2
            elif ch == "/" and nxt == "*":
                state = "block-comment"
                out.append("  ")
                i += 2
            elif ch == '"':
                state = "string"
                out.append(" ")
                i += 1
            elif ch == "'":
                state = "char"
                out.append(" ")
                i += 1
            else:
                out.append(ch)
                i += 1
        elif state == "line-comment":
            if ch == "\n":
                state = "code"
                out.append("\n")
            else:
                out.append(" ")
            i += 1
        elif state == "block-comment":
            if ch == "*" and nxt == "/":
                state = "code"
                out.append("  ")
                i += 2
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
        elif state == "string":
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
            elif ch == '"':
                state = "code"
                out.append(" ")
                i += 1
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
        else:  # char
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
            elif ch == "'":
                state = "code"
                out.append(" ")
                i += 1
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
    return "".join(out)


@dataclass
class Finding:
    file: str
    line: int
    rule: str
    severity: str
    message: str
    suggestion: str
    snippet: str = ""


@dataclass
class AnalyzeResult:
    findings: list = field(default_factory=list)
    qnx_api_hits: dict = field(default_factory=dict)

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def qnx_api_total(self) -> int:
        return sum(self.qnx_api_hits.values())


def analyze_text(text: str, fname: str) -> AnalyzeResult:
    """Analyze one C/C++ source text."""
    result = AnalyzeResult()
    clean = strip_comments_and_strings(text)
    lines = clean.splitlines()
    raw_lines = text.splitlines()
    # Rules that match string contents (filesystem paths) run on the raw
    # text; every other rule runs on the comment/string-stripped text.
    raw_rules = {"proc-self"}
    compiled = [(rid, sev, re.compile(pat), msg, sugg)
                for rid, sev, pat, msg, sugg in RULES]
    for lineno, line in enumerate(lines, 1):
        for rid, sev, pat, msg, sugg in compiled:
            if rid in raw_rules:
                continue
            for m in pat.finditer(line):
                result.findings.append(Finding(
                    file=fname, line=lineno, rule=rid, severity=sev,
                    message=msg, suggestion=sugg,
                    snippet=raw_lines[lineno - 1].strip()[:100]))
    for lineno, line in enumerate(raw_lines, 1):
        for rid, sev, pat, msg, sugg in compiled:
            if rid not in raw_rules:
                continue
            for m in pat.finditer(line):
                result.findings.append(Finding(
                    file=fname, line=lineno, rule=rid, severity=sev,
                    message=msg, suggestion=sugg,
                    snippet=line.strip()[:100]))
    for m in _QNX_API_RE.finditer(clean):
        name = m.group(1)
        result.qnx_api_hits[name] = result.qnx_api_hits.get(name, 0) + 1
    return result


def analyze_files(paths: list) -> CheckResult:
    """Analyze files; returns a CheckResult plus QNX-API evidence."""
    result = CheckResult()
    total_hits: dict = {}
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            result.add("error", "read-failed", f"cannot read {path}: {exc}",
                       path, 0)
            continue
        res = analyze_text(text, path)
        for f in res.findings:
            result.add(f.severity, f.rule, f.message, f.file, f.line,
                       f.suggestion)
        for name, count in res.qnx_api_hits.items():
            total_hits[name] = total_hits.get(name, 0) + count
    result.summary = {
        "files": len(paths),
        "errors": len(result.errors),
        "warnings": len(result.warnings),
        "qnx_api_hits": total_hits,
        "qnx_api_total": sum(total_hits.values()),
    }
    return result
