set -euo pipefail

test -d "${SYSROOT}/usr"
test -f /opt/rigyard/aarch64.cmake
command -v aarch64-linux-gnu-gcc >/dev/null
