"""Tests for the IFS image parser, builder and checksums."""

import os
import struct
import tempfile
import unittest

from qnxkit import ifs
from qnxkit.errors import QnxKitError


def file_spec(path, data, ino, mode=0o100644, mtime=1700000000):
    return {"path": path, "kind": "file", "mode": mode, "uid": 1000,
            "gid": 1000, "mtime": mtime, "ino": ino, "data": data}


class TestIfsRoundTrip(unittest.TestCase):
    def test_uncompressed_round_trip(self):
        specs = [
            file_spec(".bootstrap", b"\x7fELFBOOT", 2, 0o100755),
            file_spec("proc/hello", b"hello world", 3),
            {"path": "etc", "kind": "dir", "mode": 0o040755, "uid": 0,
             "gid": 0, "mtime": 0, "ino": 4},
            file_spec("etc/config", b"key=value\n", 5),
        ]
        image = ifs.Image.parse(ifs.build_image(
            ifs.build_filesystem(specs, mountpoint="/"), compress="none"))
        self.assertEqual(image.image_header.mountpoint, "/")
        self.assertEqual(len(image.entries), 5)  # root + 4 specs
        hello = image.lookup("proc/hello")
        self.assertIsNotNone(hello)
        self.assertEqual(image.file_bytes(hello), b"hello world")
        self.assertEqual(image.file_bytes(image.lookup("etc/config")),
                         b"key=value\n")
        self.assertEqual(image.lookup("etc").kind, "dir")
        self.assertTrue(image.image_checksum()[2])
        self.assertIsNone(image.startup_checksum())

    def test_zlib_round_trip(self):
        specs = [file_spec("a.txt", b"zlib me please " * 40, 2)]
        blob = ifs.build_image(ifs.build_filesystem(specs),
                                compress="zlib")
        image = ifs.Image.parse(blob)
        self.assertEqual(image.startup.compression_name, "zlib")
        self.assertEqual(image.file_bytes(image.lookup("a.txt")),
                         b"zlib me please " * 40)
        self.assertTrue(image.image_checksum()[2])
        self.assertIsNotNone(image.startup_checksum())
        self.assertTrue(image.startup_checksum()[2])

    def test_build_from_dir_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "sub"))
            with open(os.path.join(root, "top.txt"), "wb") as fh:
                fh.write(b"top")
            with open(os.path.join(root, "sub", "inner.txt"), "wb") as fh:
                fh.write(b"inner")
            os.symlink("top.txt", os.path.join(root, "link.txt"))
            blob = ifs.build_from_dir(root, mtime_zero=True)
            image = ifs.Image.parse(blob)
            self.assertEqual(image.file_bytes(image.lookup("top.txt")),
                             b"top")
            self.assertEqual(image.file_bytes(image.lookup("sub/inner.txt")),
                             b"inner")
            link = image.lookup("link.txt")
            self.assertEqual(link.kind, "symlink")
            self.assertEqual(link.target, "top.txt")
            self.assertEqual(image.lookup("sub").kind, "dir")
            self.assertTrue(image.image_checksum()[2])

    def test_reproducible_build(self):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "f.txt"), "wb") as fh:
                fh.write(b"same")
            a = ifs.build_from_dir(root, mtime_zero=True)
            b = ifs.build_from_dir(root, mtime_zero=True)
        self.assertEqual(a, b)

    def test_empty_dir_builds(self):
        with tempfile.TemporaryDirectory() as root:
            blob = ifs.build_from_dir(root, mtime_zero=True)
        image = ifs.Image.parse(blob)
        self.assertEqual(len(image.entries), 1)  # just the root dir
        self.assertTrue(image.image_checksum()[2])

    def test_dump_text_lists_entries(self):
        specs = [file_spec("hello.txt", b"hi", 2)]
        image = ifs.Image.parse(ifs.build_image(
            ifs.build_filesystem(specs), compress="none"))
        text = image.dump_text()
        self.assertIn("hello.txt", text)
        self.assertIn("imagefs", text)
        self.assertIn("Checksums:", text)
        self.assertIn("(valid)", text)


class TestIfsErrors(unittest.TestCase):
    def test_bad_magic_rejected(self):
        with self.assertRaises(QnxKitError):
            ifs.Image.parse(b"NOPE" + b"\x00" * 300)

    def test_truncated_rejected(self):
        specs = [file_spec("a.txt", b"data", 2)]
        blob = ifs.build_image(ifs.build_filesystem(specs), compress="none")
        with self.assertRaises(QnxKitError):
            ifs.Image.parse(blob[:100])

    def test_empty_rejected(self):
        with self.assertRaises(QnxKitError):
            ifs.Image.parse(b"")

    def test_corrupt_file_data_breaks_checksum(self):
        specs = [file_spec("a.txt", b"payload-data", 2)]
        blob = bytearray(ifs.build_image(
            ifs.build_filesystem(specs), compress="none"))
        # Corrupt the last data byte (inside the imagefs region, before
        # the 4-byte trailer).
        blob[-5] ^= 0xFF
        image = ifs.Image.parse(bytes(blob))
        cks = image.image_checksum()
        self.assertIsNotNone(cks)
        self.assertFalse(cks[2])

    def test_file_bytes_on_dir_raises(self):
        specs = [{"path": "d", "kind": "dir", "mode": 0o040755, "uid": 0,
                  "gid": 0, "mtime": 0, "ino": 2}]
        image = ifs.Image.parse(ifs.build_image(
            ifs.build_filesystem(specs), compress="none"))
        with self.assertRaises(QnxKitError):
            image.file_bytes(image.lookup("d"))

    def test_lookup_missing_returns_none(self):
        specs = [file_spec("a.txt", b"x", 2)]
        image = ifs.Image.parse(ifs.build_image(
            ifs.build_filesystem(specs), compress="none"))
        self.assertIsNone(image.lookup("nope.txt"))


class TestIfsHelpers(unittest.TestCase):
    def test_checksum_region_known_value(self):
        # checksum is the negation of the word sum; 4 zero bytes -> 0.
        self.assertEqual(ifs.checksum_region(b"\x00" * 4, "little"), 0)
        # One word 0x00000001 -> checksum 0xFFFFFFFF.
        self.assertEqual(ifs.checksum_region(struct.pack("<I", 1), "little"),
                         0xFFFFFFFF)

    def test_compression_names(self):
        self.assertEqual(
            ifs.StartupHeader(compress=ifs.COMPRESS_NONE).compression_name,
            "none")
        self.assertEqual(
            ifs.StartupHeader(compress=ifs.COMPRESS_ZLIB).compression_name,
            "zlib")
        self.assertEqual(
            ifs.StartupHeader(compress=ifs.COMPRESS_LZO).compression_name,
            "lzo")
        self.assertEqual(
            ifs.StartupHeader(compress=ifs.COMPRESS_UCL).compression_name,
            "ucl")
        self.assertEqual(
            ifs.StartupHeader(compress=9).compression_name, "unknown(0x09)")


if __name__ == "__main__":
    unittest.main()
