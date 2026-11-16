# QNX Global Hackathon 2026 — submission draft (DO NOT SUBMIT YET)

Devpost: https://qnx.devpost.com/ — deadline 15 Dec 2026 14:00 EST
(16 Dec 2026 02:00 WIB). Winners announced ~4 Feb 2027.

## Title

**qnxkit — QNX 8.0 host developer toolkit**

## Tagline

Validate mkifs buildfiles and CMake toolchains, find Linux-only APIs,
and inspect/build IFS images — from a plain Linux host, no SDP needed.

## Category

**Developer Tooling & Host Tools** (host-based tool on Linux that
builds, tests, analyzes, and otherwise supports software targeting
QNX 8.0 — explicitly allowed by the rules).

## Description (draft)

Porting to QNX 8.0 starts with three questions that are hard to
answer without the full SDP installed: is my buildfile valid, is my
CMake toolchain file right, and which Linux APIs in my code will
never compile on QNX? qnxkit answers all three offline, in seconds,
and adds a real IFS image reader/writer on top.

What it does:

- **buildfile check / new** — validates mkifs buildfiles against the
  documented syntax and attribute set (split attribute groups, unknown
  attributes, bad perms/type values, link without source, duplicate
  targets, unclosed inline files, bootstrap ordering) and generates
  working starters. The QEMU x86_64 template is taken verbatim from
  the official QNX walkthrough "QNX From The Board Up #2".
- **toolchain check / new** — validates CMake toolchain files for
  QNX 8.0 (`CMAKE_SYSTEM_NAME QNX`, `qcc`/`q++`, known `qcc -V`
  targets, arch consistency, `CMAKE_SYSROOT`/`QNX_TARGET`) and
  generates aarch64le / x86_64 files. Checked clean against Qt's
  real production QNX toolchain file.
- **analyze** — scans C/C++ for Linux-only APIs (epoll, inotify,
  eventfd, timerfd, memfd, io_uring, prctl, clone, sched_setaffinity,
  `<linux/...>` headers, `__GLIBC__`, `/proc/self/*`, raw
  `syscall(SYS_*)`) and names the QNX-native replacement for each
  (`ionotify()`, `timer_create()`, `shm_open()`, POSIX AIO,
  `pthread_create()`/`spawn()`, `ThreadCtl(_NTO_TCTL_RUNMASK)`).
  Comments and strings are stripped first, so prose mentions never
  raise findings. It also counts QNX API use as targeting evidence.
- **ifs inspect / build** — a real IFS image parser and builder:
  256-byte startup header, image header, dirents, trailer checksums,
  zlib compression, `--extract`, `--json`, reproducible builds
  (`--mtime-zero` gives byte-identical output). Build → inspect
  round-trips are verified by tests.
- **check** — whole-project QNX-readiness audit scoring 0–100 with
  the evidence listed.

Technical grounding: QNX 7.1 `mkifs` reference, CMake
`cmake-toolchains(7)`, QNX 8.0 "startup header" documentation, the
QNX `ionotify()` reference, Qt's production toolchain file, the
official QNX QEMU walkthrough, and the MIT-licensed `qnx-ifs` Rust
crate (cross-checked parser behaviour).

Honest limits, stated in the README and on every `ifs build` run:
built images are structurally valid but NOT bootable — the startup
program is a placeholder, and a bootable image needs the real
`startup-*` binary and `procnto` kernel from QNX SDP 8.0. No SDP
was used to build this tool; it is deliberately a host tool that
needs no SDP. With SDP installed, the generated artifacts are used
exactly as documented (`mkifs image.build image.ifs`,
`qemu-system-x86_64 ... -kernel image.ifs -serial stdio`).

Built with Python 3 stdlib only — zero dependencies. 69 unit tests,
all passing; `./scripts/verify.sh` runs the full end-to-end
verification (see VERIFICATION.md).

## Repo

https://github.com/slowwwkiss/qnxkit (public, MIT license)

## Video (<3 min) — script

Total ~2:20. Screen-recorded terminal, no facecam.

| Time | Shot | Narration |
| --- | --- | --- |
| 0:00–0:15 | Title card: qnxkit, "QNX 8.0 host developer toolkit" | "Porting to QNX 8.0 starts with three questions: is my buildfile valid, is my toolchain right, and which Linux APIs will never compile?" |
| 0:15–0:40 | `buildfile check` on the official QNX walkthrough buildfile → clean; then on a broken buildfile → split-attrs error | "qnxkit validates mkifs buildfiles — the official QNX walkthrough file passes, and a split attribute group is caught with the exact fix." |
| 0:40–1:00 | `toolchain check` on Qt's real toolchain file → clean; `toolchain new --arch aarch64le` | "It checks CMake toolchain files too — Qt's production file passes, and it generates aarch64le and x86_64 files." |
| 1:00–1:30 | `analyze` on hello-qnx.c (clean, 6 QNX API sites) then linux-only.c (27 errors, each with its QNX replacement) | "The analyzer finds Linux-only APIs and names the QNX replacement for each one — ionotify for epoll, timer_create for timerfd, and so on." |
| 1:30–1:55 | `ifs build` then `ifs inspect` — header, dirents, valid checksum; zlib variant | "It also reads and writes real IFS images — headers, dirents, checksums — with zlib compression and reproducible builds." |
| 1:55–2:20 | `qnxkit check` on the sample project → 100/100; test suite green | "One command audits a whole project. Sixty-nine tests, all green, stdlib only, no SDP needed. qnxkit." |

## Pre-submit checklist

- [x] Public repo with MIT LICENSE
- [x] README with install / usage / real outputs / honest limits
- [x] 69 unit tests green + scripts/verify.sh end-to-end green
- [x] Fixtures are real artifacts (QNX blog buildfile, Qt toolchain)
- [ ] Demo video recorded (<3 min) and uploaded to YouTube
- [ ] Devpost submission form filled (title, tagline, description, repo link, video link, category)
- [ ] Final read-through of the description for accuracy
