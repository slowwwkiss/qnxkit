"""Command-line interface for qnxkit."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, analyze, audit, buildfile, ifs, toolchain
from .errors import QnxKitError


def _print_issues(result, json_out: bool) -> int:
    if json_out:
        print(json.dumps({
            "ok": result.ok,
            "summary": result.summary,
            "issues": [
                {"level": i.level, "code": i.code, "message": i.message,
                 "file": i.file, "line": i.line,
                 "suggestion": i.suggestion}
                for i in result.issues],
        }, indent=2))
    else:
        for issue in result.issues:
            print(issue)
        if not result.issues:
            print("OK: no issues.")
        else:
            n_err = len(result.errors)
            n_warn = len(result.warnings)
            print(f"{n_err} error(s), {n_warn} warning(s).")
    return 0 if result.ok else 1


def _cmd_buildfile_check(args) -> int:
    with open(args.file, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    result = buildfile.check_buildfile(text, args.file)
    if not args.json:
        print(f"{args.file}: {result.summary['entries']} entries, "
              f"bootstrap={'yes' if result.summary['bootstrap'] else 'no'}, "
              f"script={'yes' if result.summary['script'] else 'no'}")
    return _print_issues(result, args.json)


def _cmd_buildfile_new(args) -> int:
    try:
        text = buildfile.generate_buildfile(args.target, args.app,
                                            args.name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.output}")
    else:
        print(text, end="")
    return 0


def _cmd_toolchain_new(args) -> int:
    try:
        text = toolchain.generate_toolchain(args.arch)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.output}")
    else:
        print(text, end="")
    return 0


def _cmd_toolchain_check(args) -> int:
    with open(args.file, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    result = toolchain.check_toolchain(text, args.file)
    if not args.json:
        arch = result.summary.get("arch") or "unknown"
        print(f"{args.file}: QNX toolchain, arch={arch}")
    return _print_issues(result, args.json)


def _cmd_analyze(args) -> int:
    result = analyze.analyze_files(args.files)
    if not args.json:
        print(f"{result.summary['files']} file(s): "
              f"{result.summary['errors']} error(s), "
              f"{result.summary['warnings']} warning(s), "
              f"{result.summary['qnx_api_total']} QNX API call site(s)")
        if result.summary["qnx_api_hits"]:
            hits = ", ".join(
                f"{k} x{v}" for k, v in sorted(
                    result.summary["qnx_api_hits"].items(),
                    key=lambda kv: -kv[1]))
            print(f"QNX APIs used: {hits}")
    return _print_issues(result, args.json)


def _cmd_ifs_inspect(args) -> int:
    with open(args.file, "rb") as fh:
        data = fh.read()
    try:
        image = ifs.Image.parse(data)
    except QnxKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({
            "file": args.file,
            "size": len(data),
            "startup": None if image.startup is None else {
                "endian": image.startup.endian,
                "compression": image.startup.compression_name,
                "header_size": image.startup.header_size,
                "startup_size": image.startup.startup_size,
                "stored_size": image.startup.stored_size,
                "imagefs_size": image.startup.imagefs_size,
                "paddr_bias": image.startup.paddr_bias,
            },
            "image_header": {
                "mountpoint": image.image_header.mountpoint,
                "image_size": image.image_header.image_size,
                "hdr_dir_size": image.image_header.hdr_dir_size,
                "dir_offset": image.image_header.dir_offset,
                "boot_ino": list(image.image_header.boot_ino),
                "script_ino": image.image_header.script_ino,
                "flags": image.image_header.flags,
            },
            "entries": [
                {"path": e.path, "kind": e.kind, "ino": e.ino,
                 "mode": e.mode, "uid": e.uid, "gid": e.gid,
                 "mtime": e.mtime, "offset": e.offset, "size": e.size,
                 "target": e.target, "dev": e.dev, "rdev": e.rdev}
                for e in image.entries],
            "omitted": image.omitted,
            "image_checksum": image.image_checksum(),
            "startup_checksum": image.startup_checksum(),
        }, indent=2))
    else:
        print(f"{args.file} ({len(data)} bytes)")
        print(image.dump_text())
    if args.extract:
        os.makedirs(args.extract, exist_ok=True)
        for e in image.entries:
            if e.kind != "file":
                continue
            dest = os.path.join(args.extract, e.path)
            if os.path.commonpath([args.extract, os.path.abspath(dest)]) != \
                    os.path.abspath(args.extract):
                print(f"warning: skipping unsafe path {e.path!r}",
                      file=sys.stderr)
                continue
            os.makedirs(os.path.dirname(dest) or args.extract, exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(image.file_bytes(e))
        print(f"extracted {sum(1 for e in image.entries if e.kind == 'file')} "
              f"file(s) to {args.extract}")
    return 0


def _cmd_ifs_build(args) -> int:
    try:
        blob = ifs.build_from_dir(
            args.root, mountpoint=args.mountpoint, compress=args.compress,
            machine=args.machine, paddr_bias=args.paddr_bias,
            mtime_zero=args.mtime_zero)
    except QnxKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    with open(args.output, "wb") as fh:
        fh.write(blob)
    print(f"wrote {args.output} ({len(blob)} bytes, "
          f"compression={args.compress})")
    print("NOTE: the startup program in this image is a placeholder. "
          "A bootable image needs the real startup-* binary and procnto "
          "kernel from QNX SDP 8.0.")
    return 0


def _cmd_check(args) -> int:
    result = audit.audit_project(args.dir)
    if args.json:
        return _print_issues(result, True)
    print(f"QNX readiness: {result.summary['score']}/100")
    for ev in result.summary["evidence"]:
        print(f"  evidence: {ev}")
    print(f"  {result.summary['buildfiles']} buildfile(s), "
          f"{result.summary['toolchains']} toolchain file(s), "
          f"{result.summary['sources']} source file(s), "
          f"{result.summary['images']} IFS image(s), "
          f"{result.summary['qnx_api_total']} QNX API call site(s)")
    return _print_issues(result, False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="qnxkit",
        description="QNX 8.0 host developer toolkit: validate and "
                    "generate mkifs buildfiles and CMake toolchains, "
                    "scan C/C++ for Linux-only APIs, and inspect/build "
                    "QNX IFS images — all from a Linux host, no SDP needed.")
    parser.add_argument("--version", action="version",
                        version=f"qnxkit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("buildfile", help="mkifs buildfile tools")
    bf = p.add_subparsers(dest="bf_command", required=True)
    q = bf.add_parser("check", help="validate a buildfile")
    q.add_argument("file")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=_cmd_buildfile_check)
    q = bf.add_parser("new", help="generate a starter buildfile")
    q.add_argument("--target", required=True,
                   choices=sorted(buildfile.TARGETS),
                   help="qemu-x86_64 (from the official QNX walkthrough) "
                        "or rpi4 (Raspberry Pi 4)")
    q.add_argument("--app", required=True, help="application binary name")
    q.add_argument("--name", help="image base name (default: app name)")
    q.add_argument("--output", "-o", help="write to file instead of stdout")
    q.set_defaults(func=_cmd_buildfile_new)

    p = sub.add_parser("toolchain", help="CMake toolchain tools")
    tc = p.add_subparsers(dest="tc_command", required=True)
    q = tc.add_parser("new", help="generate a QNX 8.0 toolchain file")
    q.add_argument("--arch", required=True, choices=sorted(toolchain.ARCHES))
    q.add_argument("--output", "-o", help="write to file instead of stdout")
    q.set_defaults(func=_cmd_toolchain_new)
    q = tc.add_parser("check", help="validate a toolchain file")
    q.add_argument("file")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=_cmd_toolchain_check)

    p = sub.add_parser("analyze", help="scan C/C++ for Linux-only APIs")
    p.add_argument("files", nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_analyze)

    p = sub.add_parser("ifs", help="QNX IFS image tools")
    ip = p.add_subparsers(dest="ifs_command", required=True)
    q = ip.add_parser("inspect", help="list an IFS image (dumpifs-style)")
    q.add_argument("file")
    q.add_argument("--json", action="store_true")
    q.add_argument("--extract", help="extract file entries to a directory")
    q.set_defaults(func=_cmd_ifs_inspect)
    q = ip.add_parser("build", help="build an IFS image from a directory")
    q.add_argument("--root", required=True)
    q.add_argument("--output", "-o", required=True)
    q.add_argument("--mountpoint", default="/")
    q.add_argument("--compress", choices=["none", "zlib"], default="none")
    q.add_argument("--machine", type=int, default=0)
    q.add_argument("--paddr-bias", type=lambda v: int(v, 0), default=0)
    q.add_argument("--mtime-zero", action="store_true",
                   help="set all mtimes to 0 for reproducible builds")
    q.set_defaults(func=_cmd_ifs_build)

    p = sub.add_parser("check", help="whole-project QNX-readiness audit")
    p.add_argument("dir")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except QnxKitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
