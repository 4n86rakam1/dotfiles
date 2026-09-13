# CLAUDE.md

## コンテキスト管理

ファイルは必要な箇所だけ読む。広い探索は subagent に出し、結果だけを main context に残す。複数ファイルの変更・大量読み込み・agent 起動が要るときは着手前に方針を 1 行述べてから進む。読み込みや探索の段取りで確認待ちに入るのは、取り返しのつかない変更のときだけ。

委譲先の成果はファイルへ書かせ、パスを報告に含めさせる。報告が返らなくても結果を回収できるようにする。

## worktree の base

`EnterWorktree` の直後に `git log --oneline HEAD..main` を確認し、空でなければ `git rebase main`。既定の base は `origin/<default-branch>` なので、ローカル main が先行していると欠けた状態で始まる。

## 曖昧な指示への対応

Prompt から対象・完了条件・制約のいずれも読み取れない場合、まず最重要の 1 点を 1 行質問で確認する (skill は起動しない)。曖昧さ解消後、中規模以上のタスク (複数ファイル変更、新規機能設計、調査結果に依存する判断) では `superpowers:brainstorming` を起動する。`grilling` skill はユーザーが明示的に起動要求した時のみ使う (`/spec` 経由の grilling 呼び出しは明示要求扱い)。

## ルール違反指摘の記録

CLAUDE.md および `~/.claude/rules/*.md` 由来のルール違反は、ユーザーからの trigger 語 (`違反ログ追記` / `違反ログ` / `違反追記` / `obs-log` / `ログして`) による指示があったときのみ `~/.claude/logs/claude-md-observations.md` へ追記する。自動追記はしない。context 汚染を避けるなら `/fork "違反ログ追記"` を使う (fork は main 会話を継承するため trigger 語だけで違反を特定できる)。判定に迷う場合も記録する (取りこぼしより過剰記録を優先)。追記形式は log 冒頭の定義に従う (Read で確認)。
