# 言語共通の基本方針

- コメントは「なぜ (WHY)」だけ。WHAT や自明な内容は書かない。
- `echo` / `print` による進捗出力は書かない。エラーは stderr に出力する。
- マジックナンバーは定数化する。未使用のインポートは残さない。
- Bash スクリプトには shebang を付与する (Python は不要)。shebang 付きスクリプトには `~/.claude/rules/code-style-sh.md` を適用する。
