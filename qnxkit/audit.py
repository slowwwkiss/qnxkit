"""Whole-project QNX-readiness audit (``qnxkit check``).

Walks a project directory and runs every qnxkit check that applies:

* ``*.build`` files  -> buildfile validation
* ``*.cmake`` / ``CMakeLists.txt`` mentioning QNX -> toolchain validation
* ``*.c`` / ``*.cc`` / ``*.cpp`` / ``*.cxx`` / ``*.h`` / ``*.hpp``
  -> portability analysis
* ``*.ifs`` files -> IFS inspection (structure + checksums)

Scores the project 0-100: start at 100, -10 per error, -2 per
warning (floor 0). A project with no QNX evidence at all (no
buildfile, no toolchain, no QNX API use, no IFS image) is capped
at 40 — it may be fine code, but it does not demonstrate a QNX
connection.
"""

from __future__ import annotations

import os

from . import analyze, buildfile, ifs, toolchain
from .errors import CheckResult

SOURCE_EXTS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh"}


def _is_toolchain_file(path: str, text: str) -> bool:
    """True if a .cmake / CMakeLists.txt file is a QNX toolchain file.

    A plain CMakeLists.txt may mention QNX in comments or in the
    -DCMAKE_TOOLCHAIN_FILE=... command; only a file that actually
    sets toolchain variables counts.
    """
    name = os.path.basename(path).lower()
    if name.endswith(".cmake") or name == "cmakelists.txt":
        return ("CMAKE_SYSTEM_NAME" in text
                or "CMAKE_C_COMPILER_TARGET" in text
                or "CMAKE_SYSROOT" in text)
    return False


def audit_project(root: str) -> CheckResult:
    """Audit a project directory; returns a combined CheckResult."""
    if not os.path.isdir(root):
        result = CheckResult()
        result.add("error", "not-a-dir", f"not a directory: {root}", root, 0)
        return result
    result = CheckResult()
    evidence: list = []
    buildfiles: list = []
    toolchains: list = []
    sources: list = []
    images: list = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in (".git", "build", "__pycache__"))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            ext = os.path.splitext(name)[1].lower()
            if name.endswith(".build"):
                buildfiles.append(path)
            elif ext == ".ifs":
                images.append(path)
            elif ext in SOURCE_EXTS:
                sources.append(path)
            elif name.endswith(".cmake") or name.lower() == "cmakelists.txt":
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                if _is_toolchain_file(path, text):
                    toolchains.append(path)

    for path in buildfiles:
        with open(path, encoding="utf-8", errors="replace") as fh:
            sub = buildfile.check_buildfile(fh.read(), path)
        result.issues.extend(sub.issues)
        result.ok = result.ok and sub.ok
        evidence.append(f"buildfile {os.path.basename(path)}")

    for path in toolchains:
        with open(path, encoding="utf-8", errors="replace") as fh:
            sub = toolchain.check_toolchain(fh.read(), path)
        result.issues.extend(sub.issues)
        result.ok = result.ok and sub.ok
        evidence.append(f"toolchain {os.path.basename(path)}")

    if sources:
        sub = analyze.analyze_files(sources)
        result.issues.extend(sub.issues)
        result.ok = result.ok and sub.ok
        if sub.summary.get("qnx_api_total"):
            evidence.append(
                f"QNX APIs used ({sub.summary['qnx_api_total']} call sites)")
    else:
        sub = None

    for path in images:
        try:
            with open(path, "rb") as fh:
                image = ifs.Image.parse(fh.read())
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            result.add("error", "ifs-parse-failed",
                       f"cannot parse IFS image: {exc}", path, 0)
            continue
        evidence.append(
            f"IFS image {os.path.basename(path)} "
            f"({len(image.entries)} entries, mountpoint "
            f"{image.image_header.mountpoint})")
        cks = image.image_checksum()
        if cks is not None and not cks[2]:
            result.add("error", "ifs-bad-checksum",
                       f"IFS image checksum INVALID (stored 0x{cks[0]:08x}, "
                       f"computed 0x{cks[1]:08x})", path, 0)

    errors = len(result.errors)
    warnings = len(result.warnings)
    score = max(0, 100 - 10 * errors - 2 * warnings)
    if not evidence:
        score = min(score, 40)
        result.add("warning", "no-qnx-evidence",
                   "no QNX evidence found (no buildfile, toolchain, QNX "
                   "API use, or IFS image) — the project does not "
                   "demonstrate a QNX connection", root, 0)
    result.summary = {
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "buildfiles": len(buildfiles),
        "toolchains": len(toolchains),
        "sources": len(sources),
        "images": len(images),
        "evidence": evidence,
        "qnx_api_total": (sub.summary.get("qnx_api_total", 0)
                          if sub else 0),
    }
    result.ok = errors == 0
    return result
