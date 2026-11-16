cmake_minimum_required(VERSION 3.16)
project(hello_qnx C)

# Cross-compile for QNX 8.0 with the generated toolchain file:
#   cmake -B build -DCMAKE_TOOLCHAIN_FILE=toolchain/qnx-toolchain-aarch64le.cmake
#   cmake --build build
# (Needs QNX SDP 8.0 with QNX_HOST / QNX_TARGET set.)

add_executable(hello_qnx src/main.c)
