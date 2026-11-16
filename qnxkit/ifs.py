"""QNX IFS (Image Filesystem) inspection and construction.

Implements the on-disk IFS format as publicly documented for QNX 8.0:

* Startup header: ``struct startup_header`` (QNX docs, "The startup
  header", com.qnx.doc.neutrino.building). 256 bytes on disk; the
  64-byte fixed prefix parsed here is::

      signature   u32  magic 0x00FF7EEB (LE bytes EB 7E FF 00)
      version     u16  == 1
      flags1      u8   bit 0x02 = big-endian; bits 0x1c = compression
                         (0x00 none, 0x04 zlib, 0x08 LZO, 0x0c UCL)
      flags2      u8   must be 0
      header_size u16  normally 256, >= 64
      machine     i16  target machine type
      startup_vaddr, paddr_bias, image_paddr, ram_paddr, ram_size : u32
      startup_size, stored_size, imagefs_paddr, imagefs_size     : u32
      preboot_size u16
      zeros       14 bytes, must be zero

* Image header: ``struct image_header`` (``sys/image.h``), fixed part
  88 bytes, followed by a NUL-terminated mountpoint string::

      signature "imagefs" (7 bytes), flags u8 (0x01 big-endian,
        0x02 read-only, 0x04 inode bits valid)
      image_size, hdr_dir_size, dir_offset : u32
      boot_ino[4], script_ino, chain_paddr : u32
      spare[10] : u32 (zero), mountflags : u32

* Directory entries: a flat chain of variable-size dirents, each
  starting with ``struct image_attr`` (24 bytes)::

      size u16, extattr_offset u16, ino u32, mode u32,
      gid u32 (stored before uid), uid u32, mtime u32

  followed, by file type, by::

      file    : u32 offset, u32 size, NUL-terminated path
                (file data lives at [header + offset, size])
      dir     : NUL-terminated path
      symlink : u16 sym_offset, u16 sym_size, path, target inline
                (sym_offset is relative to the path field)
      device  : u32 dev, u32 rdev, NUL-terminated path

  The chain ends with a zero-size entry. Dirents with ino == 0 are
  skipped by the kernel and reported as omitted. All dirent sizes
  are 4-byte aligned.

* Trailers: both the filesystem region and (for compressed images)
  the startup section end with a 4-byte trailer holding the checksum
  ``negate(sum of the region's 32-bit words, in image byte order)``
  — the rule the reference ``dumpifs`` tool applies. mkifs pads
  regions to a multiple of four bytes.

The layout above was cross-checked against the MIT-licensed
``qnx-ifs`` 0.2.0 reference parser (derived from the same public
documents) and its synthetic-image fixtures, which build images
byte-by-byte from ``sys/startup.h`` / ``sys/image.h``.

What ``ifs build`` produces: a *structurally valid* IFS image whose
startup program is a placeholder (``\\x7fELF``). It is meant for
inspection, testing and learning — a bootable image needs the real
``startup-*`` binary and ``procnto`` kernel from QNX SDP 8.0, which
this tool does not ship. The builder and the inspector are
round-trip tested against each other.
"""

from __future__ import annotations

import os
import stat
import struct
import zlib
from dataclasses import dataclass, field

from .errors import QnxKitError

STARTUP_MAGIC_LE = b"\xeb\x7e\xff\x00"
STARTUP_MAGIC_BE = b"\x00\xff\x7e\xeb"
STARTUP_HDR_VERSION = 1
STARTUP_HEADER_SIZE = 256
STARTUP_PREFIX_SIZE = 64

IMAGE_SIGNATURE = b"imagefs"
IMAGE_HEADER_FIXED = 88

S_IFMT = 0o170000
S_IFIFO = 0o010000
S_IFCHR = 0o020000
S_IFDIR = 0o040000
S_IFNAM = 0o050000
S_IFBLK = 0o060000
S_IFREG = 0o100000
S_IFLNK = 0o120000
S_IFSOCK = 0o140000

COMPRESS_NONE = 0x00
COMPRESS_ZLIB = 0x04
COMPRESS_LZO = 0x08
COMPRESS_UCL = 0x0C

_TYPE_NAMES = {
    S_IFREG: "file",
    S_IFDIR: "dir",
    S_IFLNK: "symlink",
    S_IFCHR: "char",
    S_IFBLK: "block",
    S_IFIFO: "fifo",
    S_IFNAM: "named",
    S_IFSOCK: "socket",
}

# mkifs' placeholder startup program used by the reference fixtures:
# the first four bytes of an ELF file. The builder writes exactly this
# so the startup section has the documented shape; it is NOT a real
# QNX startup program (see the module docstring).
_PLACEHOLDER_PROGRAM = b"\x7fELF"


def _align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


def checksum_region(data: bytes, endian: str) -> int:
    """Negated sum of the region's 32-bit words (the dumpifs rule).

    ``data`` must be a multiple of four bytes long.
    """
    if len(data) % 4:
        raise QnxKitError("checksum region is not a multiple of 4 bytes")
    fmt = "<I" if endian == "little" else ">I"
    total = 0
    for off in range(0, len(data), 4):
        total = (total + struct.unpack_from(fmt, data, off)[0]) & 0xFFFFFFFF
    return (-total) & 0xFFFFFFFF


@dataclass
class StartupHeader:
    header_size: int = STARTUP_HEADER_SIZE
    machine: int = 0
    startup_vaddr: int = 0
    paddr_bias: int = 0
    image_paddr: int = 0
    ram_paddr: int = 0
    ram_size: int = 0
    startup_size: int = 0
    stored_size: int = 0
    imagefs_paddr: int = 0
    imagefs_size: int = 0
    preboot_size: int = 0
    endian: str = "little"
    compress: int = COMPRESS_NONE
    flags1: int = 0

    @property
    def compression_name(self) -> str:
        return {COMPRESS_NONE: "none", COMPRESS_ZLIB: "zlib",
                COMPRESS_LZO: "lzo", COMPRESS_UCL: "ucl"}.get(
                    self.compress, f"unknown(0x{self.compress:02x})")


@dataclass
class ImageHeader:
    image_size: int = 0
    hdr_dir_size: int = 0
    dir_offset: int = 0
    boot_ino: tuple = (0, 0, 0, 0)
    script_ino: int = 0
    chain_paddr: int = 0
    mountflags: int = 0
    flags: int = 0
    mountpoint: str = "/"


@dataclass
class Entry:
    path: str
    kind: str  # file | dir | symlink | char | block | fifo | named | socket
    ino: int
    mode: int
    uid: int
    gid: int
    mtime: int
    dirent_offset: int  # offset of this dirent, relative to the image header
    dirent_size: int
    offset: int = 0     # file data offset, relative to the image header
    size: int = 0       # file data size
    target: str = ""    # symlink target
    dev: int = 0
    rdev: int = 0
    extattr_offset: int = 0

    @property
    def permissions(self) -> int:
        return self.mode & 0o7777

    def type_name(self) -> str:
        return self.kind


def _parse_startup_header(data: bytes, offset: int) -> StartupHeader:
    raw = data[offset:offset + STARTUP_PREFIX_SIZE]
    if len(raw) < STARTUP_PREFIX_SIZE:
        raise QnxKitError(f"truncated startup header at offset {offset}")
    magic = raw[0:4]
    if magic == STARTUP_MAGIC_LE:
        endian = "little"
    elif magic == STARTUP_MAGIC_BE:
        endian = "big"
    else:
        raise QnxKitError(
            f"bad startup signature at offset {offset}: {magic.hex()}")
    fmt = "<" if endian == "little" else ">"
    version, flags1, flags2, header_size, machine = struct.unpack_from(
        fmt + "HBBHh", raw, 4)
    if version != STARTUP_HDR_VERSION:
        raise QnxKitError(f"unsupported startup header version {version}")
    if flags2 != 0:
        raise QnxKitError(f"startup header flags2 is {flags2:#x}, expected 0")
    if header_size < STARTUP_PREFIX_SIZE:
        raise QnxKitError(f"startup header_size {header_size} < 64")
    if any(raw[50:64]):
        raise QnxKitError("startup header zero field is not zero")
    (startup_vaddr, paddr_bias, image_paddr, ram_paddr, ram_size,
     startup_size, stored_size, imagefs_paddr, imagefs_size) = \
        struct.unpack_from(fmt + "9I", raw, 12)
    (preboot_size,) = struct.unpack_from(fmt + "H", raw, 48)
    if startup_size < header_size:
        raise QnxKitError("startup_size is smaller than header_size")
    if stored_size < startup_size:
        raise QnxKitError("stored_size is smaller than startup_size")
    compress = flags1 & 0x1C
    if compress not in (COMPRESS_NONE, COMPRESS_ZLIB, COMPRESS_LZO, COMPRESS_UCL):
        raise QnxKitError(f"unknown startup compression flag 0x{compress:02x}")
    return StartupHeader(
        header_size=header_size, machine=machine,
        startup_vaddr=startup_vaddr, paddr_bias=paddr_bias,
        image_paddr=image_paddr, ram_paddr=ram_paddr, ram_size=ram_size,
        startup_size=startup_size, stored_size=stored_size,
        imagefs_paddr=imagefs_paddr, imagefs_size=imagefs_size,
        preboot_size=preboot_size, endian=endian, compress=compress,
        flags1=flags1)


def _parse_image_header(data: bytes, offset: int) -> tuple:
    raw = data[offset:offset + IMAGE_HEADER_FIXED]
    if len(raw) < IMAGE_HEADER_FIXED:
        raise QnxKitError(f"truncated image header at offset {offset}")
    if raw[0:7] != IMAGE_SIGNATURE:
        raise QnxKitError(
            f"bad imagefs signature at offset {offset}: {raw[0:7]!r}")
    flags = raw[7]
    endian = "big" if flags & 0x01 else "little"
    fmt = "<" if endian == "little" else ">"
    (image_size, hdr_dir_size, dir_offset) = struct.unpack_from(fmt + "3I", raw, 8)
    boot_ino = struct.unpack_from(fmt + "4I", raw, 20)
    script_ino, chain_paddr = struct.unpack_from(fmt + "2I", raw, 36)
    (mountflags,) = struct.unpack_from(fmt + "I", raw, 84)
    # Mountpoint: NUL-terminated string after the fixed fields, bounded
    # by dir_offset (a dir_offset equal to the fixed size means none).
    end = min(dir_offset, len(data) - offset)
    mount_raw = data[offset + IMAGE_HEADER_FIXED:offset + end]
    nul = mount_raw.find(b"\x00")
    mount = mount_raw if nul < 0 else mount_raw[:nul]
    header = ImageHeader(
        image_size=image_size, hdr_dir_size=hdr_dir_size,
        dir_offset=dir_offset, boot_ino=boot_ino, script_ino=script_ino,
        chain_paddr=chain_paddr, mountflags=mountflags, flags=flags,
        mountpoint=mount.decode("utf-8", "replace"))
    if dir_offset < IMAGE_HEADER_FIXED or dir_offset > hdr_dir_size:
        raise QnxKitError(
            f"image header dir_offset {dir_offset} out of range "
            f"(hdr_dir_size {hdr_dir_size})")
    if image_size < hdr_dir_size + 4 or image_size > len(data) - offset:
        raise QnxKitError(
            f"image header image_size {image_size} out of range")
    return header, endian


def _cstring(blob: bytes) -> str:
    nul = blob.find(b"\x00")
    raw = blob if nul < 0 else blob[:nul]
    return raw.decode("utf-8", "replace")


def _parse_dirents(data: bytes, base: int, dir_pos: int, dir_end: int,
                   endian: str) -> tuple:
    fmt = "<" if endian == "little" else ">"
    entries: list = []
    omitted: list = []
    pos = dir_pos
    while True:
        if pos + 2 > dir_end or pos + 2 > len(data):
            raise QnxKitError(f"unterminated dirent chain at offset {pos}")
        (size,) = struct.unpack_from(fmt + "H", data, pos)
        if size == 0:
            return entries, omitted
        if size < 24:
            raise QnxKitError(f"bad dirent size {size} at offset {pos}")
        end = pos + size
        if end > dir_end or end > len(data):
            raise QnxKitError(f"dirent at offset {pos} runs past the directory area")
        blob = data[pos:end]
        # attr block: u16 size (already read), u16 extattr_offset,
        # u32 ino, u32 mode, u32 gid, u32 uid, u32 mtime.
        (extattr_offset, ino, mode, gid, uid, mtime) = struct.unpack_from(
            fmt + "HIIIII", blob, 2)
        if ino == 0:
            # The kernel skips zero-inode dirents; record and continue.
            omitted.append({"offset": pos - base, "size": size, "mode": mode})
            pos = end
            continue
        ftype = mode & S_IFMT
        kind = _TYPE_NAMES.get(ftype)
        if kind is None:
            raise QnxKitError(
                f"unknown dirent type 0o{ftype:06o} at offset {pos}")
        entry = Entry(path="", kind=kind, ino=ino, mode=mode, uid=uid,
                      gid=gid, mtime=mtime, dirent_offset=pos - base,
                      dirent_size=size, extattr_offset=extattr_offset)
        if kind == "file":
            if len(blob) < 32:
                raise QnxKitError(f"truncated file dirent at offset {pos}")
            offset, fsize = struct.unpack_from(fmt + "2I", blob, 24)
            entry.offset, entry.size = offset, fsize
            entry.path = _cstring(blob[32:])
            if base + offset + fsize > len(data):
                raise QnxKitError(
                    f"file {entry.path!r} data runs past the end of the image")
        elif kind == "dir":
            entry.path = _cstring(blob[24:])
        elif kind == "symlink":
            if len(blob) < 28:
                raise QnxKitError(f"truncated symlink dirent at offset {pos}")
            sym_offset, sym_size = struct.unpack_from(fmt + "2H", blob, 24)
            path_end = 28 + sym_offset
            entry.path = _cstring(blob[28:path_end])
            if sym_size:
                entry.target = _cstring(blob[path_end:path_end + sym_size])
        else:  # char / block / fifo / named / socket
            if len(blob) < 32:
                raise QnxKitError(f"truncated device dirent at offset {pos}")
            entry.dev, entry.rdev = struct.unpack_from(fmt + "2I", blob, 24)
            entry.path = _cstring(blob[32:])
        entries.append(entry)
        pos = end


@dataclass
class Image:
    """A parsed QNX IFS image."""

    startup: StartupHeader | None = None
    startup_offset: int = 0
    header_offset: int = 0
    image_header: ImageHeader = field(default_factory=ImageHeader)
    entries: list = field(default_factory=list)
    omitted: list = field(default_factory=list)
    endian: str = "little"
    filesystem: bytes = b""  # decompressed imagefs region
    raw: bytes = b""

    def file_bytes(self, entry: Entry) -> bytes:
        if entry.kind != "file":
            raise QnxKitError(f"{entry.path!r} is not a regular file")
        start = entry.offset
        return self.filesystem[start:start + entry.size]

    def lookup(self, path: str) -> Entry | None:
        """First entry with this path (the root dir is \".\"), or None."""
        for entry in self.entries:
            if entry.path == path:
                return entry
        return None

    def total_size(self) -> int:
        if self.startup is not None:
            return self.startup_offset + self.startup.stored_size
        return self.header_offset + self.image_header.image_size

    def image_checksum(self):
        """(stored, computed, valid) for the filesystem trailer, or None."""
        total = self.image_header.image_size
        if total < 8 or total % 4:
            return None
        region = self.filesystem[:total - 4]
        fmt = "<I" if self.endian == "little" else ">I"
        stored = struct.unpack_from(fmt, self.filesystem, total - 4)[0]
        return stored, checksum_region(region, self.endian), \
            stored == checksum_region(region, self.endian)

    def startup_checksum(self):
        """(stored, computed, valid) for the startup trailer, or None.

        mkifs writes a startup trailer only for compressed images, so
        for uncompressed images this is not applicable.
        """
        if self.startup is None or self.startup.compress == COMPRESS_NONE:
            return None
        size = self.startup.startup_size
        if size < 8 or size % 4:
            return None
        fmt = "<I" if self.startup.endian == "little" else ">I"
        region = self.raw[self.startup_offset:self.startup_offset + size - 4]
        stored = struct.unpack_from(
            fmt, self.raw, self.startup_offset + size - 4)[0]
        computed = checksum_region(region, self.startup.endian)
        return stored, computed, stored == computed

    @classmethod
    def parse(cls, data: bytes) -> "Image":
        """Parse a whole IFS image (bootable image or bare imagefs)."""
        # Bare imagefs at the very start takes precedence, mirroring the
        # reference parser: an embedded look-alike deeper in the buffer
        # must not hijack the parse.
        if data[:7] == IMAGE_SIGNATURE:
            header, endian = _parse_image_header(data, 0)
            fs = data[0:header.image_size]
            entries, omitted = _parse_dirents(
                fs, 0, header.dir_offset, header.hdr_dir_size, endian)
            return cls(startup=None, startup_offset=0, header_offset=0,
                       image_header=header, entries=entries, omitted=omitted,
                       endian=endian, filesystem=fs, raw=data)
        # Otherwise scan for a startup header.
        magic_le = data.find(STARTUP_MAGIC_LE)
        magic_be = data.find(STARTUP_MAGIC_BE)
        candidates = [o for o in (magic_le, magic_be) if o >= 0]
        if not candidates:
            raise QnxKitError(
                "no QNX startup header (0x00FF7EEB) and no imagefs "
                "signature found — not an IFS image")
        last_error = None
        for off in sorted(candidates):
            try:
                startup = _parse_startup_header(data, off)
            except QnxKitError as exc:  # try the next candidate
                last_error = exc
                continue
            fs_off = off + startup.startup_size
            if startup.compress == COMPRESS_NONE:
                fs_end = off + startup.stored_size
                fs = data[fs_off:fs_end]
                if len(fs) < startup.imagefs_size:
                    raise QnxKitError("truncated imagefs region")
                fs = fs[:startup.imagefs_size]
            elif startup.compress == COMPRESS_ZLIB:
                comp = data[fs_off:off + startup.stored_size]
                try:
                    fs = zlib.decompress(comp)
                except zlib.error:
                    try:
                        fs = zlib.decompress(comp, 16 + zlib.MAX_WBITS)
                    except zlib.error as exc:
                        raise QnxKitError(
                            f"zlib decompression of the imagefs region "
                            f"failed: {exc}")
                if len(fs) != startup.imagefs_size:
                    raise QnxKitError(
                        f"decompressed imagefs is {len(fs)} bytes, header "
                        f"says {startup.imagefs_size}")
            else:
                raise QnxKitError(
                    f"imagefs region uses {startup.compression_name} "
                    f"compression, which needs the QNX SDP to decompress")
            header, endian = _parse_image_header(fs, 0)
            entries, omitted = _parse_dirents(
                fs, 0, header.dir_offset, header.hdr_dir_size, endian)
            return cls(startup=startup, startup_offset=off,
                       header_offset=fs_off, image_header=header,
                       entries=entries, omitted=omitted, endian=endian,
                       filesystem=fs, raw=data)
        raise QnxKitError(
            f"no valid startup header found ({last_error})")

    def dump_text(self) -> str:
        """dumpifs-style listing."""
        lines = []
        img = self.image_header
        if self.startup is not None:
            s = self.startup
            lines.append(
                f"Startup-header flags1=0x{s.flags1:02x} flags2=0 "
                f"paddr_bias=0x{s.paddr_bias:08x}")
            lines.append(
                f"  signature=0x00ff7eeb version=1 endian={s.endian} "
                f"compression={s.compression_name} header_size={s.header_size} "
                f"startup_size={s.startup_size} stored_size={s.stored_size} "
                f"imagefs_size={s.imagefs_size}")
        lines.append(
            f"Image-header mountpoint={img.mountpoint} "
            f"flags=0x{img.flags:02x} image_size={img.image_size} "
            f"hdr_dir_size={img.hdr_dir_size} dir_offset={img.dir_offset} "
            f"boot_ino={list(img.boot_ino)} script_ino={img.script_ino}")
        lines.append(f"{'Offset':>8} {'Size':>6}  Name")
        for e in self.entries:
            extra = ""
            if e.kind == "file":
                extra = f"  [{e.size} bytes @ {e.offset}]"
            elif e.kind == "symlink":
                extra = f"  -> {e.target}"
            elif e.kind in ("char", "block", "fifo", "named", "socket"):
                extra = f"  dev=0x{e.dev:x} rdev=0x{e.rdev:x}"
            lines.append(
                f"{e.dirent_offset:8x} {e.dirent_size:6x}  "
                f"{e.path or '/'} [{e.kind} {e.permissions:04o} "
                f"uid={e.uid} gid={e.gid} ino={e.ino}]{extra}")
        for o in self.omitted:
            lines.append(
                f"{o['offset']:8x} {o['size']:6x}  <omitted dirent, ino=0>")
        cks = self.image_checksum()
        if cks is not None:
            lines.append(
                f"Checksums: image=0x{cks[0]:08x} "
                f"({'valid' if cks[2] else 'INVALID, computed 0x' + format(cks[1], '08x')})")
        sc = self.startup_checksum()
        if sc is not None:
            lines.append(
                f"            startup=0x{sc[0]:08x} "
                f"({'valid' if sc[2] else 'INVALID, computed 0x' + format(sc[1], '08x')})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _dirent_size(fixed_extra: int, path: str, target: str | None) -> int:
    size = 24 + fixed_extra + len(path.encode("utf-8")) + 1
    if target is not None:
        size += len(target.encode("utf-8")) + 1
    return _align(size, 4)


def _pack_dirent(endian: str, ino: int, mode: int, uid: int, gid: int,
                 mtime: int, extra: bytes, path: str,
                 target: str | None) -> bytes:
    fmt = "<" if endian == "little" else ">"
    size = _dirent_size(len(extra), path, target)
    blob = struct.pack(fmt + "HHIIIII", size, 0, ino, mode, gid, uid, mtime)
    blob += extra
    blob += path.encode("utf-8") + b"\x00"
    if target is not None:
        blob += target.encode("utf-8") + b"\x00"
    blob += b"\x00" * (size - len(blob))
    return blob


def build_filesystem(specs: list, mountpoint: str = "/",
                     endian: str = "little") -> bytes:
    """Build an imagefs region from entry specs.

    Each spec is a dict: path, kind (file/dir/symlink/char/block/fifo/
    named/socket), mode, uid, gid, mtime, ino, data (bytes, for files),
    target (for symlinks), dev/rdev (for devices). A root dir entry
    (path "") is added automatically when absent.
    """
    fmt = "<" if endian == "little" else ">"
    specs = list(specs)
    if not any(s["path"] == "" and s["kind"] == "dir" for s in specs):
        specs.insert(0, {"path": "", "kind": "dir", "mode": 0o040755,
                         "uid": 0, "gid": 0, "mtime": 0, "ino": 1})
    header_len = _align(IMAGE_HEADER_FIXED + len(mountpoint.encode()) + 1, 4)

    # First pass: dirent sizes, so file entries know their data offsets.
    prepared = []
    dir_area = 0
    for s in specs:
        kind = s["kind"]
        if kind == "file":
            extra = struct.pack(fmt + "2I", 0, len(s.get("data", b"")))
            size = _dirent_size(8, s["path"], None)
        elif kind == "symlink":
            target = s.get("target", "")
            sym_offset = len(s["path"].encode()) + 1
            sym_size = len(target.encode()) + 1
            extra = struct.pack(fmt + "2H", sym_offset, sym_size)
            size = _dirent_size(4, s["path"], target)
        elif kind == "dir":
            extra, size = b"", _dirent_size(0, s["path"], None)
        else:
            extra = struct.pack(fmt + "2I", s.get("dev", 0), s.get("rdev", 0))
            size = _dirent_size(8, s["path"], None)
        prepared.append((s, extra, size))
        dir_area += size

    data_offset = header_len + dir_area + 4  # +4: dirent-chain terminator
    cursor = data_offset
    blobs = []
    boot_ino = [0, 0, 0, 0]
    script_ino = 0
    for s, extra, size in prepared:
        if s["kind"] == "file":
            data = s.get("data", b"")
            extra = struct.pack(fmt + "2I", cursor, len(data))
            cursor += len(data)
        if s["path"] == ".bootstrap" and s["kind"] == "file":
            boot_ino[0] = s["ino"]
        if s["path"] == ".script" and s["kind"] == "file":
            script_ino = s["ino"]
        blobs.append(_pack_dirent(endian, s["ino"], s["mode"], s["uid"],
                                  s["gid"], s["mtime"], extra, s["path"],
                                  s.get("target") if s["kind"] == "symlink"
                                  else None))
    data_end = cursor
    image_size = _align(data_end, 4) + 4  # +4: trailer
    hdr_dir_size = header_len + dir_area + 4

    header = bytearray()
    header += IMAGE_SIGNATURE
    header += bytes([0x00 if endian == "little" else 0x01])
    header += struct.pack(fmt + "3I", image_size, hdr_dir_size, header_len)
    header += struct.pack(fmt + "4I", *boot_ino)
    header += struct.pack(fmt + "2I", script_ino, 0)
    header += struct.pack(fmt + "10I", *([0] * 10))
    header += struct.pack(fmt + "I", 0)
    header += mountpoint.encode() + b"\x00"
    header += b"\x00" * (header_len - len(header))
    assert len(header) == header_len

    fs = bytes(header)
    for b in blobs:
        fs += b
    fs += b"\x00" * 4  # dirent-chain terminator
    for s, _, _ in prepared:
        if s["kind"] == "file":
            fs += s.get("data", b"")
    fs += b"\x00" * (_align(len(fs), 4) - len(fs))
    assert len(fs) == image_size - 4
    trailer = struct.pack(fmt + "I", checksum_region(fs, endian))
    return fs + trailer


def _startup_header_bytes(endian: str, flags1: int, header_size: int,
                          machine: int, paddr_bias: int, startup_size: int,
                          stored_size: int, imagefs_size: int) -> bytes:
    fmt = "<" if endian == "little" else ">"
    magic = STARTUP_MAGIC_LE if endian == "little" else STARTUP_MAGIC_BE
    out = bytearray()
    out += magic
    out += struct.pack(fmt + "HBBHh", STARTUP_HDR_VERSION, flags1, 0,
                       header_size, machine)
    out += struct.pack(fmt + "9I", 0, paddr_bias, 0, 0, 0,
                       startup_size, stored_size, 0, imagefs_size)
    out += struct.pack(fmt + "H", 0)
    out += b"\x00" * 14
    assert len(out) == STARTUP_PREFIX_SIZE
    out += b"\x00" * (header_size - STARTUP_PREFIX_SIZE)
    return bytes(out)


def build_image(filesystem: bytes, compress: str = "none", machine: int = 0,
                paddr_bias: int = 0, endian: str = "little") -> bytes:
    """Wrap an imagefs region in a startup section (bootable image)."""
    if endian != "little":
        raise QnxKitError("the builder only produces little-endian images")
    if compress == "none":
        startup_size = _align(STARTUP_HEADER_SIZE + len(_PLACEHOLDER_PROGRAM), 8)
        program = _PLACEHOLDER_PROGRAM + b"\x00" * (
            startup_size - STARTUP_HEADER_SIZE - len(_PLACEHOLDER_PROGRAM))
        stored_size = startup_size + len(filesystem)
        header = _startup_header_bytes(
            endian, COMPRESS_NONE, STARTUP_HEADER_SIZE, machine,
            paddr_bias, startup_size, stored_size, len(filesystem))
        return header + program + filesystem
    if compress == "zlib":
        payload = zlib.compress(filesystem)
        startup_size = STARTUP_HEADER_SIZE + 4  # header + startup trailer
        stored_size = startup_size + len(payload)
        header = _startup_header_bytes(
            endian, COMPRESS_ZLIB, STARTUP_HEADER_SIZE, machine,
            paddr_bias, startup_size, stored_size, len(filesystem))
        trailer = struct.pack(
            "<I", checksum_region(header, endian))
        return header + trailer + payload
    raise QnxKitError(
        f"unsupported compression {compress!r} (use none or zlib)")


def build_from_dir(root: str, mountpoint: str = "/", compress: str = "none",
                   machine: int = 0, paddr_bias: int = 0,
                   mtime_zero: bool = False) -> bytes:
    """Build an IFS image from a directory tree on the host.

    Directories become dir entries, regular files become file entries,
    symlinks become symlink entries. Device nodes, FIFOs and sockets
    in the tree are skipped (they cannot be staged from a plain
    directory). File modes come from the host stat() call.
    """
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise QnxKitError(f"not a directory: {root}")
    specs: list = []
    ino = 1

    def entry_for(path: str, rel: str) -> dict | None:
        nonlocal ino
        st = os.lstat(path)
        mtime = 0 if mtime_zero else int(st.st_mtime)
        mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISDIR(st.st_mode):
            kind, fmode = "dir", 0o040000 | mode
            data = None
        elif stat.S_ISLNK(st.st_mode):
            kind, fmode = "symlink", 0o120000 | 0o777
            data = os.readlink(path)
        elif stat.S_ISREG(st.st_mode):
            kind, fmode = "file", 0o100000 | mode
            with open(path, "rb") as fh:
                data = fh.read()
        else:
            return None
        spec = {"path": rel, "kind": kind, "mode": fmode, "uid": 0,
                "gid": 0, "mtime": mtime, "ino": ino}
        ino += 1
        if kind == "file":
            spec["data"] = data
        elif kind == "symlink":
            spec["target"] = data
        return spec

    root_spec = entry_for(root, "")
    specs.append(root_spec)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        for name in dirnames:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            spec = entry_for(os.path.join(dirpath, name), rel)
            if spec:
                specs.append(spec)
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            spec = entry_for(os.path.join(dirpath, name), rel)
            if spec:
                specs.append(spec)
    filesystem = build_filesystem(specs, mountpoint=mountpoint)
    return build_image(filesystem, compress=compress, machine=machine,
                       paddr_bias=paddr_bias)
