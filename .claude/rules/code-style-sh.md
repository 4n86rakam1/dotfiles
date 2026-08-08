---
paths:
  - "/**/*.sh"
---

# Bash Script

Follow the Google Shell Style Guide.

- Shebang: `#!/bin/bash`
- Constants: `readonly UPPER_SNAKE_CASE`
- Local variables: `local lower_snake_case`
- Function names: `lower_snake_case`
- Conditionals: `[[ ]]`
- Split the work into functions and end the file with `main "$@"`
