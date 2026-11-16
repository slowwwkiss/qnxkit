# qnxkit — QNX 8.0 host developer toolkit

A Linux host tool that validates and generates **mkifs buildfiles** and
**CMake toolchains** for QNX 8.0, scans C/C++ for Linux-only APIs that
will not compile on QNX, and inspects/builds **QNX IFS images** — all
from a plain Linux host, with no QNX SDP installed.

Built for the **QNX Global Hackathon 2026** (Devpost), category
**Developer Tooling & Host Tools**.

## Why this exists

Porting to QNX 8.0 usually starts with three questions that are
surprisingly hard to answer without the full SDP installed:

1. Is my buildfile even valid? (`mkifs` rejects it only at build time.)
2. Is my CMake toolchain file right for QNX? (Wrong `CMAKE_SYSTEM_NAME`
   or a mismatched `qcc -V` target fails late, with cryptic errors.)
3. Which Linux APIs in my code will never compile on QNX?

`qnxkit` answers all three offline, in seconds, and adds a real IFS
image reader/writer so you can inspect and assemble images without
`mkifs`/`dumpifs`.

## Install

Python 3.8+ and nothing else — standard library only, no dependencies.

```sh
git clone https://github.com/slowwwkiss/qnxkit.git
cd qnxkit
python3 -m qnxkit --version   # qnxkit 0.1.0
```

No install step, no virtualenv, no network access at runtime.

## Usage

### Validate a buildfile

```sh
$ python3 -m qnxkit buildfile check fixtures/qemu-x86_64.build
fixtures/qemu-x86_64.build: 2 entries, bootstrap=yes, script=yes
OK: no issues.
```

That fixture is the complete buildfile from the official QNX
walkthrough *"QNX From The Board Up #2"* — `qnxkit` checks it clean.
The validator catches the mistakes the reference documents call out,
for example split attribute groups (`[uid=5] [gid=5]`), unknown
attributes, bad `perms=`/`type=` values, `[type=link]` without a
source, duplicate targets, unclosed inline files, and a bootstrap
section whose first entry is not a `startup-*` binary.

Generate a starter buildfile:

```sh
$ python3 -m qnxkit buildfile new --target qemu-x86_64 --app hello_qnx
# qnxkit generated buildfile — QEMU x86_64 (multiboot) ...
[virtual=x86_64,multiboot] boot = {
    startup-x86 -D 8250
    procnto-smp-instr
}
[+script] init = {
    display_msg "Hello, stranger!"
    PATH=/proc/boot:/bin:/usr/bin
    LD_LIBRARY_PATH=/proc/boot:/lib:/usr/lib:/lib/dll
    [perms=0755] hello_qnx
}
[perms=0644] libc.so
```

`--target rpi4` generates a Raspberry Pi 4 template instead (labelled
best-effort in the file: it follows the RPi4 BSP pattern).

### Validate a CMake toolchain file

```sh
$ python3 -m qnxkit toolchain check fixtures/qnx-toolchain-aarch64le.cmake
fixtures/qnx-toolchain-aarch64le.cmake: QNX toolchain, arch=aarch64le
OK: no issues.
```

That fixture is Qt's real production QNX toolchain file — `qnxkit`
checks it clean. The checker verifies `CMAKE_SYSTEM_NAME QNX`,
`qcc`/`q++` compilers, a known `qcc -V` target (`gcc_ntoaarch64le`,
`gcc_ntox86_64`), architecture consistency between
`CMAKE_SYSTEM_PROCESSOR` and the compiler target, and the
`CMAKE_SYSROOT`/`QNX_TARGET` setup.

Generate one:

```sh
$ python3 -m qnxkit toolchain new --arch aarch64le   # or --arch x86_64
```

### Scan C/C++ for Linux-only APIs

```sh
$ python3 -m qnxkit analyze fixtures/hello-qnx.c
1 file(s): 0 error(s), 0 warning(s), 6 QNX API call site(s)
QNX APIs used: ChannelCreate x1, name_attach x1, MsgReceive x1, MsgReply x1, name_open x1, MsgSend x1

$ python3 -m qnxkit analyze fixtures/linux-only.c
1 file(s): 27 error(s), 2 warning(s), 0 QNX API call site(s)
ERROR: fixtures/linux-only.c:18: [linux-epoll-header] #include <sys/epoll.h> — epoll.h does not exist on QNX  -> use ionotify() — the QNX equivalent of epoll() — or poll()/select()
ERROR: fixtures/linux-only.c:39: [linux-epoll] epoll() has no QNX counterpart  -> use ionotify() — the QNX equivalent of epoll() — or poll()/select()
ERROR: fixtures/linux-only.c:45: [linux-inotify] inotify() has no QNX counterpart  -> watch files with ionotify() or poll() the directory
ERROR: fixtures/linux-only.c:49: [linux-eventfd] eventfd() has no QNX counterpart  -> signal between threads with a QNX channel + pulse (ChannelCreate/MsgSendPulse) or a pipe()
...
```

Every finding names the QNX-native replacement: `ionotify()` for
epoll, `timer_create()` for timerfd, `shm_open()` for memfd, POSIX AIO
for io_uring, `pthread_create()`/`spawn()` for `clone()`,
`ThreadCtl(_NTO_TCTL_RUNMASK)` for `sched_setaffinity()`. Comments and
string literals are stripped before matching, so a mention of `epoll`
in prose never raises a finding.

### Inspect and build IFS images

```sh
$ python3 -m qnxkit ifs build --root rootfs --output test.ifs --mtime-zero
wrote test.ifs (528 bytes, compression=none)

$ python3 -m qnxkit ifs inspect test.ifs
test.ifs (528 bytes)
Startup-header flags1=0x00 flags2=0 paddr_bias=0x00000000
  signature=0x00ff7eeb version=1 endian=little compression=none header_size=256 startup_size=264 stored_size=528 imagefs_size=264
Image-header mountpoint=/ flags=0x00 image_size=264 hdr_dir_size=244 dir_offset=92 boot_ino=[0, 0, 0, 0] script_ino=0
  Offset   Size  Name
      5c     1c  / [dir 0770 uid=0 gid=0 ino=1]
      78     1c  sub [dir 0770 uid=0 gid=0 ino=2]
      94     2c  hello.txt [file 0660 uid=0 gid=0 ino=3]  [9 bytes @ 244]
      c0     30  sub/inner.txt [file 0660 uid=0 gid=0 ino=4]  [5 bytes @ 253]
Checksums: image=0x645d218f (valid)
```

`ifs build` also supports `--compress zlib` (the image is then
compressed with real zlib and the startup trailer checksum is
verified), `--mountpoint`, `--machine`, `--paddr-bias`, and
`--mtime-zero` for byte-identical reproducible builds. `ifs inspect
--json` emits machine-readable output and `--extract DIR` pulls the
file entries out.

### Whole-project audit

```sh
$ python3 -m qnxkit check fixtures/sample-project
QNX readiness: 100/100
  evidence: buildfile image.build
  evidence: toolchain qnx-toolchain-aarch64le.cmake
  evidence: QNX APIs used (6 call sites)
  1 buildfile(s), 1 toolchain file(s), 1 source file(s), 0 IFS image(s), 6 QNX API call site(s)
OK: no issues.
```

`qnxkit check` walks a project, runs every check that applies, and
scores it 0–100 (−10 per error, −2 per warning; capped at 40 when no
QNX evidence is found at all). Add `--json` to any check command for
machine-readable output.

## What this genuinely does for QNX 8.0

- Validates real mkifs buildfiles against the documented syntax and
  attribute set (QNX 7.1 `mkifs` reference; the format is unchanged
  in 8.0), and generates working starters — the QEMU x86_64 one is
  taken from the official QNX walkthrough.
- Validates real CMake toolchain files against the documented QNX
  pattern (CMake `cmake-toolchains(7)` + Qt's production file).
- Flags Linux-only APIs with QNX-native replacements, grounded in the
  QNX `ionotify()` reference (QNX has no `epoll()`; `ionotify()` is
  the equivalent).
- Reads and writes real IFS images: the 256-byte startup header, the
  image header, dirents, and the trailer checksums — implemented
  from the QNX 8.0 "startup header" documentation and cross-checked
  against the MIT-licensed `qnx-ifs` Rust crate's parser. Images
  built by `qnxkit` parse back with valid checksums, and
  build → inspect round-trips are covered by tests.

## Honest limits

- **`ifs build` images are structurally valid but NOT bootable.**
  The startup program in a built image is a placeholder; a bootable
  image needs the real `startup-*` binary and the `procnto` kernel,
  which only ship with QNX SDP 8.0. The tool says so on every build.
  Nothing here pretends to have booted QNX.
- **No SDP was used to build this tool.** QNX SDP 8.0 requires a
  myQNX account (email + confirmation) and a non-commercial licence
  request; that signup is a user step an agent cannot complete, so
  this tool was deliberately built as a host tool that needs no SDP
  at all. With SDP installed, the generated artifacts are used
  exactly as documented:

  ```sh
  mkifs image.build image.ifs
  qemu-system-x86_64 -cpu max -smp 1 -display none -kernel image.ifs -serial stdio
  cmake -B build -DCMAKE_TOOLCHAIN_FILE=qnx-toolchain-aarch64le.cmake
  cmake --build build
  ```

- The rpi4 buildfile template follows the RPi4 BSP pattern and is
  labelled best-effort; the qemu-x86_64 template is verbatim from
  the official QNX walkthrough.
- The IFS builder emits little-endian images; the inspector accepts
  both byte orders. LZO/UCL-compressed images can be *identified*
  but not decompressed (that needs the SDP codecs).

## Project layout

```
qnxkit/            the tool (stdlib only)
  buildfile.py     mkifs buildfile parser / validator / generator
  toolchain.py     CMake QNX toolchain generator / checker
  analyze.py       Linux-only API scanner with QNX replacements
  ifs.py           IFS image parser / builder / checksums
  audit.py         whole-project readiness audit (qnxkit check)
  cli.py           argparse CLI
fixtures/          real QNX artifacts + sample sources
  qemu-x86_64.build            official QNX walkthrough buildfile
  qnx-toolchain-aarch64le.cmake  Qt's production toolchain file
  hello-qnx.c                  QNX message-passing demo (clean)
  linux-only.c                 Linux-only code (27 errors, 2 warnings)
  sample-project/              mini project scoring 100/100
tests/             stdlib unittest, 69 tests
scripts/verify.sh  full end-to-end verification
docs/DESIGN.md     format sources and design decisions
```

## Tests

```sh
./scripts/verify.sh   # unit tests + every CLI path + IFS round-trips
python3 -m unittest discover -s tests -v
```

See [VERIFICATION.md](VERIFICATION.md) for the full recorded run.

## License

MIT — see [LICENSE](LICENSE).
