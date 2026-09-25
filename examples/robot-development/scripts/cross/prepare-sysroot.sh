set -euo pipefail

test -d "${SYSROOT}/usr"
mkdir -p /opt/rigyard

sed "s|@SYSROOT@|${SYSROOT}|g" \
  /workspace/scripts/cross/rigyard.cmake.in \
  > /opt/rigyard/aarch64.cmake
