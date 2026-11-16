# DESIGN.md — sources and decisions

## Sources (all fetched and read during development)

| Area | Source | What was taken from it |
| --- | --- | --- |
| mkifs buildfile syntax | QNX 7.1 `mkifs` reference (china.qnx.com/developers/docs/7.1/com.qnx.doc.neutrino.utilities/topic/m/mkifs.html) | Full attribute list (boolean: autolink, big_pages, bigendian, compress, followlink, include, keeplinked, optional, page_align, raw, script; value: autoso, cd, chain, cksum, data, dperms, drop, filter, gid, image, keepsection, linker, module, mount, mtime, pagesizes, perms, phys_align, physical, prefix, ram, search, sha256, type, uid, virtual); `[attrs] file` line form; `#` comment needs a preceding space; two bracket groups on one line is an error; `?` conditional prefix; inline files `target={...}` with braces alone on their lines; `[+script]`, `[virtual=...]`/`[physical=...]` bootstrap; sticky attributes |
| CMake QNX toolchain | CMake `cmake-toolchains(7)` docs + Qt's production file (code.qt.io/cgit/qt/qt5.git/plain/coin/provisioning/common/shared/cmake_toolchain_files/qnx-toolchain-aarch64le.cmake) | `CMAKE_SYSTEM_NAME QNX`, `CMAKE_SYSTEM_PROCESSOR`, FIND_ROOT_PATH modes NEVER/ONLY/ONLY/ONLY, `CMAKE_FIND_ROOT_PATH $ENV{QNX_TARGET};$ENV{QNX_TARGET}/${CMAKE_SYSTEM_PROCESSOR}`, `qcc`/`q++` with `gcc_ntoaarch64le`, `ntoaarch64-*` binutils, `CMAKE_SYSROOT $ENV{QNX_TARGET}` |
| qcc targets | QNX 8.0 gcc/qcc docs | `qcc -Vgcc_ntoaarch64le` (AArch64), `qcc -Vgcc_ntox86_64` (x86_64) |
| IFS binary format | QNX 8.0 docs ("The startup header") + MIT-licensed `qnx-ifs` 0.2.0 crate source (crates.io, src/startup.rs, src/image.rs, src/lib.rs, tests/common/fixtures.rs) | Startup header 256 bytes: 64-byte prefix (magic LE bytes EB 7E FF 00 = 0x00FF7EEB, version u16=1, flags1 u8: bit 0x02 big-endian, bits 0x1c compression 0x00 none/0x04 zlib/0x08 LZO/0x0c UCL; flags2=0; header_size u16 normally 256; machine i16; 9x u32: startup_vaddr, paddr_bias, image_paddr, ram_paddr, ram_size, startup_size, stored_size, imagefs_paddr, imagefs_size; preboot_size u16; 14 zero bytes). Image header fixed 88 bytes: "imagefs" (7B), flags u8 (0x01 big-endian, 0x02 readonly, 0x04 ino bits), image_size, hdr_dir_size, dir_offset (u32), boot_ino[4], script_ino, chain_paddr, spare[10]=0, mountflags, then NUL-terminated mountpoint. Dirent attr 24 bytes: u16 size, u16 extattr_offset, u32 ino, u32 mode, u32 gid (before uid), u32 uid, u32 mtime; file: u32 offset + u32 size + path; dir: path; symlink: u16 sym_offset + u16 sym_size + path + target inline; device: u32 dev + u32 rdev + path; chain ends with zero-size entry; ino==0 skipped by kernel; dirent sizes 4-byte aligned. Trailer checksum rule: negate(sum of the region's 32-bit words in image byte order); mkifs pads regions to multiples of 4; filesystem trailer always present; startup trailer only for compressed images |
| QEMU buildfile | QNX blog "QNX From The Board Up #2" (qnx.software/en/blog/2026/qnxe-ftbu-2) | `[virtual=x86_64,multiboot] boot = { startup-x86 -D 8250; procnto-smp-instr }`, `[+script] init = { display_msg "Hello, stranger!" }`, `qemu-system-x86_64 -cpu max -smp 1 -display none -kernel image.ifs -serial stdio` |
| epoll equivalent | QNX `ionotify()` reference | "This function corresponds to the Linux epoll() function and BSD's kqueue(). The QNX Neutrino implementations of select() and poll() are built on top of ionotify()." — QNX has NO epoll(); ionotify() is the equivalent |

## Design decisions

- **Stdlib only.** No dependencies, so the tool runs on any Linux
  host with Python 3.8+ and the verification is trivially
  reproducible. Tests use stdlib `unittest`.
- **Host tool, not a fake QNX run.** QNX SDP 8.0 requires a myQNX
  account + licence request — a user step an agent cannot complete.
  Rather than faking a boot, the tool is a host tool (an explicitly
  allowed hackathon route) and every `ifs build` run says the image
  is not bootable without SDP binaries.
- **Fixtures are real artifacts, not invented ones.** The QEMU
  buildfile is verbatim from the official QNX walkthrough; the
  toolchain fixture is Qt's real production file. Both are checked
  clean by the tool, which is the strongest available evidence that
  the validators accept real-world input.
- **Parser and builder share the layout code.** `ifs.py` builds
  images with the same field order the parser reads, and the
  round-trip tests (uncompressed + zlib, plus checksum-corruption
  detection) pin the behaviour. The parser was written against the
  `qnx-ifs` crate's reader, including the ino==0 skip rule and the
  zero-size dirent terminator.
- **Checksum rule implemented exactly:** negate the sum of the
  region's 32-bit words in image byte order, stored as the 4-byte
  trailer. Verified by corrupting one data byte and watching the
  check fail (test `test_corrupt_file_data_breaks_checksum`).
- **Analyzer strips comments and strings first.** A mention of
  `epoll` in prose must never raise a finding; only code counts.
  One exception: `/proc/self/*` paths live in string literals, so
  that single rule runs on the raw text.
- **Audit scoring is evidence-based.** A project with no QNX
  evidence (no buildfile, toolchain, QNX API use, or IFS image) is
  capped at 40/100 even if it has zero errors — it may be fine code,
  but it does not demonstrate a QNX connection.
- **Deterministic builds.** `--mtime-zero` zeroes all mtimes so two
  builds of the same tree are byte-identical (tested with `cmp`).

## Known limitations

- The IFS builder emits little-endian images only; the inspector
  accepts both byte orders (big-endian parsing is implemented but
  has no builder-produced fixture — it is exercised only by code
  review, not by a test).
- LZO/UCL-compressed images can be identified (flags) but not
  decompressed — those codecs need the SDP.
- The rpi4 buildfile template follows the RPi4 BSP pattern and is
  labelled best-effort in its header; the qemu-x86_64 template is
  verbatim from the official QNX walkthrough.
- The analyzer is regex-based, not a full C parser: it can miss
  APIs hidden behind macros and can in principle false-positive on
  unusual code shapes. The comment/string stripper covers the
  common false-positive sources.
- `qnxkit check` treats a `.cmake`/`CMakeLists.txt` file as a
  toolchain file only when it sets toolchain variables
  (`CMAKE_SYSTEM_NAME`, `CMAKE_C_COMPILER_TARGET`, or
  `CMAKE_SYSROOT`), so a plain `CMakeLists.txt` that merely mentions
  QNX is not mis-checked.
