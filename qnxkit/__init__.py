"""qnxkit — a QNX 8.0 host developer toolkit.

Runs on a Linux host (Python 3.8+, standard library only) and helps
developers build, inspect, and audit software that targets QNX 8.0:

* ``buildfile`` — validate and generate mkifs image buildfiles
* ``toolchain`` — generate and check QNX 8.0 CMake toolchain files
* ``analyze``   — scan C/C++ sources for Linux-only APIs that QNX lacks
* ``ifs``       — inspect and build QNX IFS (Image Filesystem) images
* ``check``     — whole-project QNX-readiness audit

The tool needs no QNX SDP install to run; it works from the publicly
documented QNX 8.0 formats (see docs/DESIGN.md for the sources each
format was grounded in). Building a *bootable* image still needs the
real startup binary and kernel from QNX SDP 8.0 (free via QNX
Everywhere), which this tool does not ship.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
