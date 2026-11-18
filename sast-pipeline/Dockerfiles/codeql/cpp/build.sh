#!/bin/bash
set -euo pipefail

# The project supplies executable configuration, as it already does for init.
exec /bin/bash -euo pipefail -c "${SAST_BUILD_COMMAND:?Project build command is required}"
