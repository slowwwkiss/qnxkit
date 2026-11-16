"""mkifs image buildfile parsing, validation and generation.

The grammar implemented here follows the QNX 7.1/8.0 ``mkifs``
reference (Utilities Reference) and the "Making an OS Image" chapter
of Building Embedded Systems:

* Each line is ``[attributes] file_specification``; either part may
  be absent. A line with attributes only sets "sticky" attributes
  for the files that follow it.
* A ``#`` starts a comment when it is at the start of a line or
  preceded by a space. Inside inline files ``#`` is literal.
* Attributes live in one ``[...]`` group; combining two groups on one
  line (``[uid=5] [gid=5]``) is an error — they must be combined
  inside one pair of brackets (``[uid=5 gid=5]``).
* Boolean attributes take a ``+``/``-`` prefix; value attributes take
  ``name=value`` with no spaces around ``=``. A leading ``?`` makes
  an attribute conditional (set only if not already set).
* File specifications are ``path``, ``target=host`` or
  ``target={ inline contents }``. Inline contents span lines; the
  opening and closing braces must each be alone on their line, and
  ``}`` / ``\\`` inside must be escaped.
* The bootstrap section is a ``[virtual=...]`` / ``[physical=...]``
  inline file whose first entry must be a ``startup-*`` program;
  the ``[+script]`` inline file holds the commands procnto runs
  after startup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import CheckResult

# Boolean attributes (mkifs reference, "Attributes" section).
BOOLEAN_ATTRS = {
    "autolink", "big_pages", "bigendian", "compress", "followlink",
    "include", "keeplinked", "optional", "page_align", "raw", "script",
}
# Value attributes (mkifs reference, "Attributes" section).
VALUE_ATTRS = {
    "autoso", "cd", "chain", "cksum", "data", "dperms", "drop", "filter",
    "gid", "image", "keepsection", "linker", "module", "mount", "mtime",
    "pagesizes", "perms", "phys_align", "physical", "prefix", "ram",
    "search", "sha256", "type", "uid", "virtual",
}
KNOWN_ATTRS = BOOLEAN_ATTRS | VALUE_ATTRS

# QNX 8.0 CPUs a buildfile virtual/physical attribute may name.
KNOWN_CPUS = {"x86_64", "aarch64le", "armle-v7", "armle", "x86"}

# Values the mkifs ``type=`` attribute accepts for an image entry.
KNOWN_TYPES = {
    "link", "dir", "file", "symlink", "fifo", "device", "char", "block",
    "socket", "named",
}

_ATTR_RE = re.compile(r"^\[([^\]]*)\]\s*(.*)$")
_TOKEN_RE = re.compile(r"^\??[+-]?[A-Za-z0-9_]+(=[^ \t]+)?$")
_OCTAL_PERMS_RE = re.compile(r"^0?[0-7]{1,4}$")
_SYMBOLIC_PERMS_RE = re.compile(
    r"^([ugoa]*[+-=][rwxXstugo]*)(,[ugoa]*[+-=][rwxXstugo]*)*$")
_HEX_RE = re.compile(r"^0[xX][0-9a-fA-F]+$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass
class BuildfileEntry:
    """One parsed buildfile line (a file to place in the image)."""

    target: str
    host: str = ""          # "" when the spec is a bare path
    inline: str | None = None  # inline contents, when target={...}
    attrs: dict = field(default_factory=dict)
    line: int = 0
    is_bootstrap: bool = False
    is_script: bool = False


@dataclass
class Buildfile:
    entries: list = field(default_factory=list)
    sticky: dict = field(default_factory=dict)


def _split_comment(line: str) -> str:
    """Strip a buildfile comment (``#`` at line start or after a space)."""
    if line.startswith("#"):
        return ""
    idx = line.find(" #")
    if idx >= 0:
        return line[:idx]
    return line


def _validate_attr_value(name: str, value: str, result: CheckResult,
                         line_no: int, fname: str) -> None:
    if name in ("uid", "gid"):
        if not re.match(r"^(\d+|[A-Za-z_][A-Za-z0-9_-]*)$", value):
            result.add("error", "bad-attr-value",
                       f"{name}={value!r} is not a user/group id",
                       fname, line_no)
    elif name in ("perms", "dperms"):
        if not (_OCTAL_PERMS_RE.match(value)
                or _SYMBOLIC_PERMS_RE.match(value)):
            result.add("error", "bad-attr-value",
                       f"{name}={value!r} is not an octal or symbolic mode",
                       fname, line_no,
                       "use e.g. perms=0666 or perms=a+xr")
    elif name == "type":
        if value not in KNOWN_TYPES:
            result.add("error", "bad-attr-value",
                       f"type={value!r} is not a known image entry type",
                       fname, line_no,
                       f"known types: {', '.join(sorted(KNOWN_TYPES))}")
    elif name in ("virtual", "physical"):
        parts = value.split(None, 1)
        first = parts[0] if parts else ""
        cpu = first.split(",")[0] if "," in first else ""
        bootfile = first.split(",", 1)[1] if "," in first else first
        if not bootfile:
            result.add("error", "bad-attr-value",
                       f"{name}={value!r} names no boot file",
                       fname, line_no)
        elif cpu and cpu not in KNOWN_CPUS:
            result.add("warning", "unknown-cpu",
                       f"{name} names CPU {cpu!r}, not a known QNX 8.0 CPU",
                       fname, line_no,
                       f"known CPUs: {', '.join(sorted(KNOWN_CPUS))}")
    elif name in ("image", "ram", "chain"):
        ok = bool(_HEX_RE.match(value) or value.isdigit()
                  or re.match(r"^0[xX][0-9a-fA-F]+-0[xX][0-9a-fA-F]+$", value))
        if not ok:
            result.add("error", "bad-attr-value",
                       f"{name}={value!r} is not an address",
                       fname, line_no, "use e.g. image=0x10000")
    elif name == "search":
        if any(not p for p in value.split(":")):
            result.add("error", "bad-attr-value",
                       f"search={value!r} has an empty path element",
                       fname, line_no)
    elif name == "sha256":
        if not _SHA256_RE.match(value):
            result.add("error", "bad-attr-value",
                       "sha256= must be 64 hex characters", fname, line_no)
    elif name == "data":
        if value != "copy":
            result.add("warning", "unknown-data",
                       f"data={value!r} is not a documented data mode",
                       fname, line_no, "documented: data=copy")
    elif name == "pagesizes":
        if not re.match(r"^(\d+[kKmMgG]?)(,\d+[kKmMgG]?)*$", value):
            result.add("error", "bad-attr-value",
                       f"pagesizes={value!r} is not a size list",
                       fname, line_no, "use e.g. pagesizes=4k,2M")
    elif name == "cksum":
        if not value.isdigit():
            result.add("error", "bad-attr-value",
                       f"cksum={value!r} is not a number", fname, line_no)


def _parse_attrs(text: str, result: CheckResult, line_no: int,
                 fname: str) -> dict:
    attrs = {}
    for token in text.split():
        if not _TOKEN_RE.match(token):
            result.add("error", "bad-attr",
                       f"malformed attribute token {token!r}",
                       fname, line_no)
            continue
        conditional = token.startswith("?")
        body = token[1:] if conditional else token
        if "=" in body:
            name, value = body.split("=", 1)
            if name not in VALUE_ATTRS:
                if name in BOOLEAN_ATTRS:
                    result.add("error", "bad-attr",
                               f"boolean attribute {name!r} takes no value",
                               fname, line_no)
                else:
                    result.add("error", "unknown-attr",
                               f"unknown attribute {name!r}", fname, line_no,
                               f"known attributes: {', '.join(sorted(KNOWN_ATTRS))}")
                continue
            _validate_attr_value(name, value, result, line_no, fname)
            attrs[name] = value
        else:
            name = body.lstrip("+-")
            if name not in BOOLEAN_ATTRS:
                if name in VALUE_ATTRS:
                    result.add("error", "bad-attr",
                               f"value attribute {name!r} needs =value",
                               fname, line_no)
                else:
                    result.add("error", "unknown-attr",
                               f"unknown attribute {name!r}", fname, line_no,
                               f"known attributes: {', '.join(sorted(KNOWN_ATTRS))}")
                continue
            attrs[name] = body.startswith("-") is False
        if conditional:
            attrs[f"?{name}"] = attrs.pop(name)
    return attrs


def parse_buildfile(text: str, fname: str = "<buildfile>") -> tuple:
    """Parse buildfile text into (Buildfile, CheckResult)."""
    result = CheckResult()
    bf = Buildfile()
    sticky: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line_no = i + 1
        i += 1
        # Line continuation with backslash-newline (outside inline files).
        while raw.rstrip("\n").endswith("\\") and i < len(lines):
            raw = raw.rstrip("\n")[:-1] + lines[i]
            i += 1
        line = _split_comment(raw).strip()
        if not line:
            continue
        m = _ATTR_RE.match(line)
        attrs: dict = {}
        rest = line
        if m:
            attrs = _parse_attrs(m.group(1), result, line_no, fname)
            rest = m.group(2).strip()
            # A second bracket group on the same line is an error: the
            # reference says attributes must be combined in one pair.
            if rest.startswith("["):
                result.add("error", "split-attrs",
                           "attributes must be combined in one [...] group",
                           fname, line_no,
                           "write [uid=5 gid=5], not [uid=5] [gid=5]")
                continue
        if not rest:
            # Attributes-only line: sticky for the files that follow.
            for key, val in attrs.items():
                if key.startswith("?"):
                    if key[1:] not in sticky:
                        sticky[key[1:]] = val
                else:
                    sticky[key] = val
            continue
        # Merge sticky attributes (per-file attributes win).
        merged = dict(sticky)
        for key, val in attrs.items():
            if key.startswith("?"):
                if key[1:] not in merged:
                    merged[key[1:]] = val
            else:
                merged[key] = val
        # Inline file: target = { ... } — braces alone on their lines.
        if "=" in rest and rest.rstrip().endswith("="):
            result.add("error", "bad-spec",
                       f"line ends with '=' but no inline block follows: {rest!r}",
                       fname, line_no)
            continue
        inline = None
        target = rest
        host = ""
        if "=" in rest:
            target, _, rhs = rest.partition("=")
            target = target.strip()
            rhs = rhs.strip()
            if rhs.startswith("{"):
                if rhs != "{":
                    result.add("error", "bad-inline",
                               "inline contents must start on the line after "
                               f"'{{': {rest!r}", fname, line_no)
                    continue
                body = []
                closed = False
                while i < len(lines):
                    inner = lines[i]
                    i += 1
                    if inner.strip() == "}":
                        closed = True
                        break
                    body.append(inner)
                if not closed:
                    result.add("error", "unclosed-inline",
                               f"inline file {target!r} is never closed",
                               fname, line_no)
                    continue
                inline = "\n".join(body)
            else:
                host = rhs
        if not target:
            result.add("error", "bad-spec",
                       f"empty target path on line {line_no}", fname, line_no)
            continue
        entry = BuildfileEntry(target=target, host=host, inline=inline,
                               attrs=merged, line=line_no)
        if "virtual" in merged or "physical" in merged:
            entry.is_bootstrap = True
        if merged.get("script") is True:
            entry.is_script = True
        bf.entries.append(entry)
    bf.sticky = sticky
    return bf, result


def check_buildfile(text: str, fname: str = "<buildfile>") -> CheckResult:
    """Validate a buildfile; returns errors and warnings."""
    bf, result = parse_buildfile(text, fname)
    seen: dict = {}
    has_bootstrap = False
    has_script = False
    for e in bf.entries:
        if e.target in seen and e.inline is None:
            result.add("error", "duplicate-target",
                       f"target {e.target!r} is listed twice "
                       f"(first at line {seen[e.target]})",
                       fname, e.line)
        else:
            seen[e.target] = e.line
        if e.is_bootstrap:
            has_bootstrap = True
            if e.inline is not None:
                first = next((ln.strip() for ln in e.inline.splitlines()
                              if ln.strip()), "")
                if first and not first.split()[0].startswith("startup-"):
                    result.add("warning", "bootstrap-order",
                               "the first bootstrap entry should be a "
                               f"startup-* program, got {first.split()[0]!r}",
                               fname, e.line)
        if e.is_script:
            has_script = True
        if e.attrs.get("type") == "link" and not e.host and e.inline is None:
            result.add("error", "link-without-source",
                       f"[type=link] {e.target!r} needs target=source form",
                       fname, e.line,
                       "write [type=link] /dev/console=/dev/ser1")
        # Bare names (libc.so, hello_qnx) are normal: mkifs resolves them
        # via the search path. Only a relative path with a directory
        # component looks like a path that should have been absolute.
        if ("/" in e.target and not e.target.startswith("/")
                and e.inline is None and not e.is_bootstrap
                and not e.is_script and not e.target.startswith(".")):
            result.add("warning", "relative-target",
                       f"target {e.target!r} is a relative path; image "
                       "paths are usually absolute", fname, e.line)
    if bf.entries and not has_bootstrap:
        result.add("warning", "no-bootstrap",
                   "no [virtual=...]/[physical=...] bootstrap section; "
                   "mkifs can build the image but it cannot boot",
                   fname, 0)
    if bf.entries and not has_script:
        result.add("warning", "no-script",
                   "no [+script] block; the image boots but runs nothing",
                   fname, 0)
    if not bf.entries and not result.errors:
        result.add("error", "empty-buildfile",
                   "the buildfile lists no files", fname, 0)
    result.summary = {
        "entries": len(bf.entries),
        "bootstrap": has_bootstrap,
        "script": has_script,
    }
    return result


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

QEMU_X86_64_TEMPLATE = """\
# QNX 8.0 image buildfile for QEMU x86_64 (multiboot).
# Generated by qnxkit. Structure follows the official QNX walkthrough
# "QNX From The Board Up #2 - Create a Basic Image"
# (https://qnx.software/en/blog/2026/qnxe-ftbu-2).
# Build with QNX SDP 8.0:  mkifs {name}.build {name}.ifs
# Boot with QEMU:  qemu-system-x86_64 -cpu max -smp 1 -display none \\
#                    -kernel {name}.ifs -serial stdio

[virtual=x86_64,multiboot] boot = {{
    startup-x86 -D 8250
    procnto-smp-instr
}}
[+script] init = {{
    display_msg "Hello from {app} on QNX 8.0!"
    {app} &
    reopen /dev/console
}}
[type=link] /dev/console=/dev/ser1
[type=link] /tmp=/dev/shmem
libc.so
[perms=0775] {app}
"""

RPI4_TEMPLATE = """\
# QNX 8.0 image buildfile for Raspberry Pi 4 (aarch64le).
# Generated by qnxkit. Follows the documented Raspberry Pi 4 BSP
# pattern (startup-rpi4 + procnto-smp-instr); validate against the
# QNX SDP 8.0 BSP before flashing real hardware.
# Build with QNX SDP 8.0:  mkifs {name}.build {name}.ifs

[virtual=aarch64le,elf] .bootstrap = {{
    startup-rpi4
    PATH=/proc/boot procnto-smp-instr
}}
[+script] .script = {{
    display_msg "Hello from {app} on QNX 8.0!"
    {app} &
    reopen /dev/console
}}
[type=link] /dev/console=/dev/ser1
[type=link] /tmp=/dev/shmem
libc.so
[perms=0775] {app}
"""

TARGETS = {
    "qemu-x86_64": QEMU_X86_64_TEMPLATE,
    "rpi4": RPI4_TEMPLATE,
}


def generate_buildfile(target: str, app: str, name: str | None = None) -> str:
    """Generate a starter buildfile for a QNX 8.0 target."""
    if target not in TARGETS:
        raise ValueError(
            f"unknown target {target!r}; known targets: "
            f"{', '.join(sorted(TARGETS))}")
    if not re.match(r"^[A-Za-z0-9_.-]+$", app):
        raise ValueError(f"bad app name {app!r}")
    return TARGETS[target].format(app=app, name=name or app)
