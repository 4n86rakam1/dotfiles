# Shared Code Style

- Comments explain WHY only. Never write WHAT or anything self-evident.
- Never write progress output via `echo` or `print`. Errors go to stderr.
- Turn magic numbers into named constants. Leave no unused imports.
- Bash scripts: `#!/bin/bash`, Google Shell Style Guide (Python needs no shebang). Always split the work into functions and end with `main "$@"` — unconditionally, unlike the guide, which asks for it only once a script has functions.
