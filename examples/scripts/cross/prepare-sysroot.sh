set -euo pipefail

test -d "${SYSROOT}/usr"
mkdir -p /opt/toolchain

sed "s|@SYSROOT@|${SYSROOT}|g" \
  /workspace/scripts/cross/toolchain.cmake.in \
  > /opt/toolchain/aarch64.cmake
