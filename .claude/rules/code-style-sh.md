---
paths:
  - "/**/*.sh"
---

# Bash Script

Google Shell Style Guide に従う。

- Shebang: `#!/bin/bash`
- 定数: `readonly UPPER_SNAKE_CASE`
- ローカル変数: `local lower_snake_case`
- 関数名: `lower_snake_case`
- 条件式: `[[ ]]`
- 処理は関数に分割し末尾に `main "$@"`
