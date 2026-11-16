#!/bin/sh
# verify.sh — full end-to-end verification of qnxkit.
# Runs the unit tests and every CLI command against the fixtures,
# including an IFS build -> inspect round-trip (uncompressed + zlib)
# and a reproducibility check. Exits non-zero on any failure.
# Everything runs on a plain Linux host; no QNX SDP is needed.
set -eu

cd "$(dirname "$0")/.."
ROOT=$(pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

echo "== environment =="
python3 --version
echo "python: $(python3 -c 'import sys; print(sys.executable)')"
echo

echo "== 1. unit tests =="
python3 -m unittest discover -s tests -v
echo

echo "== 2. buildfile check — official QNX walkthrough buildfile =="
python3 -m qnxkit buildfile check fixtures/qemu-x86_64.build
echo

echo "== 3. toolchain check — Qt production toolchain file =="
python3 -m qnxkit toolchain check fixtures/qnx-toolchain-aarch64le.cmake
echo

echo "== 4. analyze — QNX sample clean, Linux sample flagged =="
python3 -m qnxkit analyze fixtures/hello-qnx.c
echo "--- linux-only.c is expected to FAIL (27 errors, 2 warnings):"
if python3 -m qnxkit analyze fixtures/linux-only.c; then
    echo "ERROR: linux-only.c should have failed analysis" >&2
    exit 1
fi
echo

echo "== 5. IFS build -> inspect round-trip (uncompressed) =="
mkdir -p "$TMP/root/sub"
printf 'hello ifs' > "$TMP/root/hello.txt"
printf 'inner' > "$TMP/root/sub/inner.txt"
python3 -m qnxkit ifs build --root "$TMP/root" --output "$TMP/test.ifs"
python3 -m qnxkit ifs inspect "$TMP/test.ifs"
echo

echo "== 6. IFS build -> inspect round-trip (zlib) =="
python3 -m qnxkit ifs build --root "$TMP/root" --output "$TMP/test-z.ifs" \
    --compress zlib
python3 -m qnxkit ifs inspect --json "$TMP/test-z.ifs" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); \
        assert d['startup']['compression']=='zlib', d['startup']; \
        assert d['image_checksum'][2], d['image_checksum']; \
        print('zlib image: compression=zlib, image checksum valid')"
echo

echo "== 7. IFS extract =="
python3 -m qnxkit ifs inspect "$TMP/test.ifs" --extract "$TMP/out"
test "$(cat "$TMP/out/hello.txt")" = "hello ifs"
test "$(cat "$TMP/out/sub/inner.txt")" = "inner"
echo "extract OK"
echo

echo "== 8. reproducible builds =="
python3 -m qnxkit ifs build --root "$TMP/root" --output "$TMP/a.ifs" \
    --mtime-zero
python3 -m qnxkit ifs build --root "$TMP/root" --output "$TMP/b.ifs" \
    --mtime-zero
cmp "$TMP/a.ifs" "$TMP/b.ifs" && echo "identical bytes"
echo

echo "== 9. whole-project audit on the sample project =="
python3 -m qnxkit check fixtures/sample-project
echo

echo "== 10. generated artifacts pass their own checks =="
python3 -m qnxkit buildfile new --target qemu-x86_64 --app hello_qnx \
    --output "$TMP/gen.build"
python3 -m qnxkit buildfile check "$TMP/gen.build"
python3 -m qnxkit toolchain new --arch aarch64le \
    --output "$TMP/gen.cmake"
python3 -m qnxkit toolchain check "$TMP/gen.cmake"
python3 -m qnxkit toolchain new --arch x86_64 \
    --output "$TMP/gen64.cmake"
python3 -m qnxkit toolchain check "$TMP/gen64.cmake"
echo

echo "ALL VERIFICATION PASSED"
