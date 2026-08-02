# スキル作成

スキルを作成する際は `.claude/commands/` ではなく `.claude/skills/<name>/SKILL.md` を使う。

副作用のある操作（commit, deploy, send 等）には `disable-model-invocation: true` を付ける。
