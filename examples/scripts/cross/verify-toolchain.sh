set -euo pipefail

test -d "${SYSROOT}/usr"
test -f /opt/toolchain/aarch64.cmake
command -v aarch64-linux-gnu-gcc >/dev/null
