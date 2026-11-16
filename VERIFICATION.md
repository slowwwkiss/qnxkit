# VERIFICATION — qnxkit

Recorded run of `./scripts/verify.sh` (16 Nov 2026, Python 3.12.3,
Linux VM, no QNX SDP installed). The script runs the unit tests and
every CLI command against the fixtures, including IFS build → inspect
round-trips (uncompressed + zlib), extraction, reproducible builds,
and the whole-project audit. It exited 0: **ALL VERIFICATION PASSED**.

Summary of the results:

- Unit tests: **69 tests, all OK** (buildfile 21, toolchain 10,
  analyze 7, ifs 14, cli 17 — counts from the run below).
- Official QNX walkthrough buildfile: clean (2 entries, bootstrap +
  script).
- Qt production toolchain file: clean (arch aarch64le).
- `analyze` on `hello-qnx.c`: 0 errors, 6 QNX API call sites.
- `analyze` on `linux-only.c`: 27 errors, 2 warnings (expected fail).
- IFS build → inspect round-trip: valid checksum, entries listed
  (uncompressed and zlib); extract reproduces file contents;
  `--mtime-zero` builds are byte-identical (`cmp`).
- `qnxkit check` on `fixtures/sample-project`: **100/100**.
- Generated buildfile + both generated toolchain files pass their own
  checks.

Full log:

```
== environment ==
Python 3.12.3
python: /usr/bin/python3

== 1. unit tests ==
test_linux_only_sample (test_analyze.TestAnalyzerFixtures.test_linux_only_sample) ... ok
test_qnx_sample_is_clean (test_analyze.TestAnalyzerFixtures.test_qnx_sample_is_clean) ... ok
test_code_finding_survives (test_analyze.TestStripper.test_code_finding_survives) ... ok
test_comment_mention_is_ignored (test_analyze.TestStripper.test_comment_mention_is_ignored) ... ok
test_line_comment_mention_is_ignored (test_analyze.TestStripper.test_line_comment_mention_is_ignored) ... ok
test_qnx_suggestion_names_ionotify (test_analyze.TestStripper.test_qnx_suggestion_names_ionotify) ... ok
test_string_mention_is_ignored (test_analyze.TestStripper.test_string_mention_is_ignored) ... ok
test_generated_qemu_buildfile_is_clean (test_buildfile.TestBuildfileFixtures.test_generated_qemu_buildfile_is_clean) ... ok
test_generated_rpi4_buildfile_is_clean (test_buildfile.TestBuildfileFixtures.test_generated_rpi4_buildfile_is_clean) ... ok
test_official_qemu_buildfile_is_clean (test_buildfile.TestBuildfileFixtures.test_official_qemu_buildfile_is_clean) ... ok
test_unknown_target_rejected (test_buildfile.TestBuildfileFixtures.test_unknown_target_rejected) ... ok
test_bad_perms (test_buildfile.TestBuildfileValidation.test_bad_perms) ... ok
test_boolean_attribute_with_value (test_buildfile.TestBuildfileValidation.test_boolean_attribute_with_value) ... ok
test_bootstrap_first_entry_warning (test_buildfile.TestBuildfileValidation.test_bootstrap_first_entry_warning) ... ok
test_combined_attribute_group_ok (test_buildfile.TestBuildfileValidation.test_combined_attribute_group_ok) ... ok
test_comments_ignored (test_buildfile.TestBuildfileValidation.test_comments_ignored) ... ok
test_conditional_attribute (test_buildfile.TestBuildfileValidation.test_conditional_attribute) ... ok
test_duplicate_target (test_buildfile.TestBuildfileValidation.test_duplicate_target) ... ok
test_inline_contents_not_parsed (test_buildfile.TestBuildfileValidation.test_inline_contents_not_parsed) ... ok
test_link_without_source (test_buildfile.TestBuildfileValidation.test_link_without_source) ... ok
test_no_bootstrap_warning (test_buildfile.TestBuildfileValidation.test_no_bootstrap_warning) ... ok
test_split_attribute_groups_are_an_error (test_buildfile.TestBuildfileValidation.test_split_attribute_groups_are_an_error) ... ok
test_sticky_attributes_apply (test_buildfile.TestBuildfileValidation.test_sticky_attributes_apply) ... ok
test_symbolic_perms_ok (test_buildfile.TestBuildfileValidation.test_symbolic_perms_ok) ... ok
test_unclosed_inline (test_buildfile.TestBuildfileValidation.test_unclosed_inline) ... ok
test_unknown_attribute (test_buildfile.TestBuildfileValidation.test_unknown_attribute) ... ok
test_unknown_cpu_warning (test_buildfile.TestBuildfileValidation.test_unknown_cpu_warning) ... ok
test_unknown_type (test_buildfile.TestBuildfileValidation.test_unknown_type) ... ok
test_linux_sample_fails (test_cli.TestCliAnalyze.test_linux_sample_fails) ... ok
test_qnx_sample_clean (test_cli.TestCliAnalyze.test_qnx_sample_clean) ... ok
test_no_args_errors (test_cli.TestCliBasics.test_no_args_errors) ... ok
test_version (test_cli.TestCliBasics.test_version) ... ok
test_check_bad_file_fails (test_cli.TestCliBuildfile.test_check_bad_file_fails) ... ok
test_check_json (test_cli.TestCliBuildfile.test_check_json) ... ok
test_check_official_fixture (test_cli.TestCliBuildfile.test_check_official_fixture) ... ok
test_new_bad_target (test_cli.TestCliBuildfile.test_new_bad_target) ... ok
test_new_qemu (test_cli.TestCliBuildfile.test_new_qemu) ... ok
test_empty_dir_scores_low (test_cli.TestCliCheck.test_empty_dir_scores_low) ... ok
test_sample_project_scores_100 (test_cli.TestCliCheck.test_sample_project_scores_100) ... ok
test_build_and_inspect_round_trip (test_cli.TestCliIfs.test_build_and_inspect_round_trip) ... ok
test_build_zlib (test_cli.TestCliIfs.test_build_zlib) ... ok
test_inspect_json (test_cli.TestCliIfs.test_inspect_json) ... ok
test_check_qt_fixture (test_cli.TestCliToolchain.test_check_qt_fixture) ... ok
test_new_aarch64le (test_cli.TestCliToolchain.test_new_aarch64le) ... ok
test_new_x86_64 (test_cli.TestCliToolchain.test_new_x86_64) ... ok
test_bad_magic_rejected (test_ifs.TestIfsErrors.test_bad_magic_rejected) ... ok
test_corrupt_file_data_breaks_checksum (test_ifs.TestIfsErrors.test_corrupt_file_data_breaks_checksum) ... ok
test_empty_rejected (test_ifs.TestIfsErrors.test_empty_rejected) ... ok
test_file_bytes_on_dir_raises (test_ifs.TestIfsErrors.test_file_bytes_on_dir_raises) ... ok
test_lookup_missing_returns_none (test_ifs.TestIfsErrors.test_lookup_missing_returns_none) ... ok
test_truncated_rejected (test_ifs.TestIfsErrors.test_truncated_rejected) ... ok
test_checksum_region_known_value (test_ifs.TestIfsHelpers.test_checksum_region_known_value) ... ok
test_compression_names (test_ifs.TestIfsHelpers.test_compression_names) ... ok
test_build_from_dir_round_trip (test_ifs.TestIfsRoundTrip.test_build_from_dir_round_trip) ... ok
test_dump_text_lists_entries (test_ifs.TestIfsRoundTrip.test_dump_text_lists_entries) ... ok
test_empty_dir_builds (test_ifs.TestIfsRoundTrip.test_empty_dir_builds) ... ok
test_reproducible_build (test_ifs.TestIfsRoundTrip.test_reproducible_build) ... ok
test_uncompressed_round_trip (test_ifs.TestIfsRoundTrip.test_uncompressed_round_trip) ... ok
test_zlib_round_trip (test_ifs.TestIfsRoundTrip.test_zlib_round_trip) ... ok
test_generated_aarch64le_is_clean (test_toolchain.TestToolchainFixtures.test_generated_aarch64le_is_clean) ... ok
test_generated_x86_64_is_clean (test_toolchain.TestToolchainFixtures.test_generated_x86_64_is_clean) ... ok
test_qt_production_toolchain_is_clean (test_toolchain.TestToolchainFixtures.test_qt_production_toolchain_is_clean) ... ok
test_unknown_arch_rejected (test_toolchain.TestToolchainFixtures.test_unknown_arch_rejected) ... ok
test_arch_mismatch (test_toolchain.TestToolchainValidation.test_arch_mismatch) ... ok
test_missing_sysroot_is_warning (test_toolchain.TestToolchainValidation.test_missing_sysroot_is_warning) ... ok
test_missing_system_name (test_toolchain.TestToolchainValidation.test_missing_system_name) ... ok
test_unknown_target (test_toolchain.TestToolchainValidation.test_unknown_target) ... ok
test_wrong_c_compiler (test_toolchain.TestToolchainValidation.test_wrong_c_compiler) ... ok
test_wrong_system_name (test_toolchain.TestToolchainValidation.test_wrong_system_name) ... ok

----------------------------------------------------------------------
Ran 69 tests in 2.632s

OK

== 2. buildfile check — official QNX walkthrough buildfile ==
fixtures/qemu-x86_64.build: 2 entries, bootstrap=yes, script=yes
OK: no issues.

== 3. toolchain check — Qt production toolchain file ==
fixtures/qnx-toolchain-aarch64le.cmake: QNX toolchain, arch=aarch64le
OK: no issues.

== 4. analyze — QNX sample clean, Linux sample flagged ==
1 file(s): 0 error(s), 0 warning(s), 6 QNX API call site(s)
QNX APIs used: ChannelCreate x1, name_attach x1, MsgReceive x1, MsgReply x1, name_open x1, MsgSend x1
OK: no issues.
--- linux-only.c is expected to FAIL (27 errors, 2 warnings):
1 file(s): 27 error(s), 2 warning(s), 0 QNX API call site(s)
ERROR: fixtures/linux-only.c:18: [linux-epoll-header] #include <sys/epoll.h> — epoll.h does not exist on QNX  -> use ionotify() — the QNX equivalent of epoll() — or poll()/select()
ERROR: fixtures/linux-only.c:19: [linux-inotify-header] #include <sys/inotify.h> — inotify.h does not exist on QNX  -> watch files with ionotify() or poll() the directory
ERROR: fixtures/linux-only.c:20: [linux-eventfd-header] #include <sys/eventfd.h> — eventfd.h does not exist on QNX  -> signal between threads with a QNX channel + pulse or a pipe()
ERROR: fixtures/linux-only.c:21: [linux-timerfd-header] #include <sys/timerfd.h> — timerfd.h does not exist on QNX  -> use POSIX timer_create()/timer_settime(), which QNX libc provides
ERROR: fixtures/linux-only.c:22: [linux-memfd-header] #include <sys/memfd.h> — memfd.h does not exist on QNX  -> use shm_open() (POSIX shared memory, provided by QNX libc)
ERROR: fixtures/linux-only.c:23: [linux-prctl-header] #include <sys/prctl.h> — prctl.h does not exist on QNX  -> control threads/processes with ThreadCtl() and procmgr_*()
ERROR: fixtures/linux-only.c:24: [raw-syscall-header] #include <sys/syscall.h> — raw syscall numbers do not exist on QNX  -> call the libc function instead of syscall(SYS_...)
ERROR: fixtures/linux-only.c:25: [linux-io-uring-header] io_uring headers do not exist on QNX  -> use POSIX AIO (aio_read()/aio_write()) or a worker thread pool
ERROR: fixtures/linux-only.c:26: [linux-kernel-headers] Linux kernel headers (<linux/...>) do not exist on QNX  -> use the QNX/POSIX headers (<sys/neutrino.h>, <pthread.h>, ...)
ERROR: fixtures/linux-only.c:39: [linux-epoll] epoll() has no QNX counterpart  -> use ionotify() — the QNX equivalent of epoll() — or poll()/select()
ERROR: fixtures/linux-only.c:42: [linux-epoll] epoll() has no QNX counterpart  -> use ionotify() — the QNX equivalent of epoll() — or poll()/select()
ERROR: fixtures/linux-only.c:43: [linux-epoll] epoll() has no QNX counterpart  -> use ionotify() — the QNX equivalent of epoll() — or poll()/select()
ERROR: fixtures/linux-only.c:45: [linux-inotify] inotify() has no QNX counterpart  -> watch files with ionotify() or poll() the directory
ERROR: fixtures/linux-only.c:46: [linux-inotify] inotify() has no QNX counterpart  -> watch files with ionotify() or poll() the directory
ERROR: fixtures/linux-only.c:47: [linux-inotify] inotify() has no QNX counterpart  -> watch files with ionotify() or poll() the directory
ERROR: fixtures/linux-only.c:49: [linux-eventfd] eventfd() has no QNX counterpart  -> signal between threads with a QNX channel + pulse (ChannelCreate/MsgSendPulse) or a pipe()
ERROR: fixtures/linux-only.c:52: [linux-timerfd] timerfd() has no QNX counterpart  -> use POSIX timer_create()/timer_settime(), which QNX libc provides
ERROR: fixtures/linux-only.c:55: [linux-memfd] memfd_create() has no QNX counterpart  -> use shm_open() (POSIX shared memory, provided by QNX libc)
ERROR: fixtures/linux-only.c:59: [linux-io-uring] io_uring has no QNX counterpart  -> use POSIX AIO (aio_read()/aio_write()) or a worker thread pool
ERROR: fixtures/linux-only.c:60: [linux-io-uring] io_uring has no QNX counterpart  -> use POSIX AIO (aio_read()/aio_write()) or a worker thread pool
ERROR: fixtures/linux-only.c:62: [linux-prctl] prctl() has no QNX counterpart  -> control threads/processes with ThreadCtl() and procmgr_*()
ERROR: fixtures/linux-only.c:66: [linux-clone] clone() has no QNX counterpart  -> create threads with pthread_create() or processes with spawn()
ERROR: fixtures/linux-only.c:71: [linux-sched-affinity] sched_setaffinity()/CPU_SET have no QNX counterpart  -> set a thread runmask with ThreadCtl(_NTO_TCTL_RUNMASK, ...)
ERROR: fixtures/linux-only.c:72: [linux-sched-affinity] sched_setaffinity()/CPU_SET have no QNX counterpart  -> set a thread runmask with ThreadCtl(_NTO_TCTL_RUNMASK, ...)
ERROR: fixtures/linux-only.c:73: [linux-sched-affinity] sched_setaffinity()/CPU_SET have no QNX counterpart  -> set a thread runmask with ThreadCtl(_NTO_TCTL_RUNMASK, ...)
WARNING: fixtures/linux-only.c:76: [glibc-guard] __GLIBC__ guards do not apply: QNX libc is not glibc  -> guard QNX-specific code with __QNX__ / __QNXNTO__ instead
WARNING: fixtures/linux-only.c:77: [glibc-guard] __GLIBC__ guards do not apply: QNX libc is not glibc  -> guard QNX-specific code with __QNX__ / __QNXNTO__ instead
ERROR: fixtures/linux-only.c:86: [raw-syscall] raw Linux syscall numbers (SYS_*) do not exist on QNX  -> call the libc function instead of syscall(SYS_...)
ERROR: fixtures/linux-only.c:82: [proc-self] /proc/self/exe, /proc/self/maps and friends are not in the QNX /proc  -> resolve the executable path from argv[0] or the QNX process manager
27 error(s), 2 warning(s).

== 5. IFS build -> inspect round-trip (uncompressed) ==
wrote /tmp/tmp.l7a3nnGSM7/test.ifs (528 bytes, compression=none)
NOTE: the startup program in this image is a placeholder. A bootable image needs the real startup-* binary and procnto kernel from QNX SDP 8.0.
/tmp/tmp.l7a3nnGSM7/test.ifs (528 bytes)
Startup-header flags1=0x00 flags2=0 paddr_bias=0x00000000
  signature=0x00ff7eeb version=1 endian=little compression=none header_size=256 startup_size=264 stored_size=528 imagefs_size=264
Image-header mountpoint=/ flags=0x00 image_size=264 hdr_dir_size=244 dir_offset=92 boot_ino=[0, 0, 0, 0] script_ino=0
  Offset   Size  Name
      5c     1c  / [dir 0770 uid=0 gid=0 ino=1]
      78     1c  sub [dir 0770 uid=0 gid=0 ino=2]
      94     2c  hello.txt [file 0660 uid=0 gid=0 ino=3]  [9 bytes @ 244]
      c0     30  sub/inner.txt [file 0660 uid=0 gid=0 ino=4]  [5 bytes @ 253]
Checksums: image=0xb870f183 (valid)

== 6. IFS build -> inspect round-trip (zlib) ==
wrote /tmp/tmp.l7a3nnGSM7/test-z.ifs (374 bytes, compression=zlib)
NOTE: the startup program in this image is a placeholder. A bootable image needs the real startup-* binary and procnto kernel from QNX SDP 8.0.
zlib image: compression=zlib, image checksum valid

== 7. IFS extract ==
/tmp/tmp.l7a3nnGSM7/test.ifs (528 bytes)
Startup-header flags1=0x00 flags2=0 paddr_bias=0x00000000
  signature=0x00ff7eeb version=1 endian=little compression=none header_size=256 startup_size=264 stored_size=528 imagefs_size=264
Image-header mountpoint=/ flags=0x00 image_size=264 hdr_dir_size=244 dir_offset=92 boot_ino=[0, 0, 0, 0] script_ino=0
  Offset   Size  Name
      5c     1c  / [dir 0770 uid=0 gid=0 ino=1]
      78     1c  sub [dir 0770 uid=0 gid=0 ino=2]
      94     2c  hello.txt [file 0660 uid=0 gid=0 ino=3]  [9 bytes @ 244]
      c0     30  sub/inner.txt [file 0660 uid=0 gid=0 ino=4]  [5 bytes @ 253]
Checksums: image=0xb870f183 (valid)
extracted 2 file(s) to /tmp/tmp.l7a3nnGSM7/out
extract OK

== 8. reproducible builds ==
wrote /tmp/tmp.l7a3nnGSM7/a.ifs (528 bytes, compression=none)
NOTE: the startup program in this image is a placeholder. A bootable image needs the real startup-* binary and procnto kernel from QNX SDP 8.0.
wrote /tmp/tmp.l7a3nnGSM7/b.ifs (528 bytes, compression=none)
NOTE: the startup program in this image is a placeholder. A bootable image needs the real startup-* binary and procnto kernel from QNX SDP 8.0.
identical bytes

== 9. whole-project audit on the sample project ==
QNX readiness: 100/100
  evidence: buildfile image.build
  evidence: toolchain qnx-toolchain-aarch64le.cmake
  evidence: QNX APIs used (6 call sites)
  1 buildfile(s), 1 toolchain file(s), 1 source file(s), 0 IFS image(s), 6 QNX API call site(s)
OK: no issues.

== 10. generated artifacts pass their own checks ==
wrote /tmp/tmp.l7a3nnGSM7/gen.build
/tmp/tmp.l7a3nnGSM7/gen.build: 6 entries, bootstrap=yes, script=yes
OK: no issues.
wrote /tmp/tmp.l7a3nnGSM7/gen.cmake
/tmp/tmp.l7a3nnGSM7/gen.cmake: QNX toolchain, arch=aarch64le
OK: no issues.
wrote /tmp/tmp.l7a3nnGSM7/gen64.cmake
/tmp/tmp.l7a3nnGSM7/gen64.cmake: QNX toolchain, arch=x86_64
OK: no issues.

ALL VERIFICATION PASSED
```
