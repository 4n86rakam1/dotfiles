---
name: tool-mix-audit
description: Read/Edit などの専用ツールと、cat/sed/grep といった Bash 等価物のどちらでファイル操作が行われたかを全 transcript から集計する。モデル別・bash-first steer の有無別に置換率を出す。モデル変更後の回帰確認、CLAUDE_CODE_THRIFTY_SONIC の効果測定、path スコープ付き rule が発火しているかの検証に使う。
---

# tool-mix-audit — ファイル操作のツール構成監査

`~/.claude/projects/*/*.jsonl` を走査し、ファイル操作が専用ツール (Read / Edit / Write) と Bash 等価物 (`cat` / `sed -i` / `grep`) のどちらで行われたかを集計する。

目的は path スコープ付き rule の生死確認。`.claude/rules/*.md` の `paths:` frontmatter と、サブディレクトリの `CLAUDE.md` は Read ツールでファイルを読んだときにしか読み込まれない。`cat` で読むと発火しないため、Bash 置換率がそのまま「rule が沈黙している割合」の上限になる。

## 使い方

```bash
python3 ~/.claude/skills/tool-mix-audit/audit.py
python3 ~/.claude/skills/tool-mix-audit/audit.py --model opus-5 --sessions
python3 ~/.claude/skills/tool-mix-audit/audit.py --since 2026-09-01 --project dotfiles
```

- `--model <部分一致>`: セッション開始時のモデルで絞る
- `--project <部分一致>`: プロジェクトディレクトリ名で絞る
- `--since YYYY-MM-DD`: 指定日以降のみ
- `--exclude-session <ID>`: セッションを除外する (複数指定可)
- `--include-subagent`: subagent (`isSidechain`) の tool_use も含める
- `--sessions`: セッション単位の内訳を追加で出す
- `--rules`: transcript ではなく hook のログから rule の発火率を出す (後述)
- `--rule-dir <dir>`: rule を探すディレクトリを追加する

リモートホストで走らせる場合は転送不要。

```bash
ssh <host> 'python3 -' < ~/.claude/skills/tool-mix-audit/audit.py
```

編集したら必ずテストを通す。

```bash
python3 -m unittest discover ~/.claude/skills/tool-mix-audit
```

## 出力の読み方

行は `モデル × steer ラベル`。steer ラベルは `auto_mode` attachment から取る。

- `steer`: `bashFirst: true`。Bash 優先の指示がシステムプロンプトに入ったセッション
- `auto-no-steer`: auto / bypass モードだが `bashFirst: false`
- `no-auto`: `auto_mode` attachment 自体がない。通常の permission mode

`bash率 = Bash 等価物 / (専用ツール + Bash 等価物)`。比較は率で見る。transcript は約 30 日で自動削除される (`cleanupPeriodDays` デフォルト) ため、絶対件数の母数は日ごとに変わる。

## 判定ロジックと限界

Bash コマンドはヒアドキュメント本文と `<<DELIM` 導入部を除去し、引用符の外の改行を `;` に置換したうえで shlex でトークン化する。`;` `&&` `||` と `|` でパイプラインに分解し、各セグメントの先頭コマンド名で分類する。`sudo` `timeout` `nice` などのラッパは、値を取るフラグと位置引数を数えて読み飛ばす。

パイプの下流はファイル操作として数えない。`git log | head -40` の `head` はページャであってファイル読み取りではないため、ファイル名オペランドを持つ場合のみ計上する。`grep` と `sed` は第 1 オペランドがパターンなので除外し、`find` は最初のフラグより前のオペランドだけをパスとして扱う。値を取るフラグはコマンドごとに違う (`head -n 40` の `-n` は値を取るが `sed -n` は真偽値) ため、コマンド別のテーブルで持つ。

リダイレクト (`>` `>>` `>|` `&>`) の書き込み先は edit として数えるが、`/dev/*` と `tmp/` 配下は除外する。`2>&1` の記述子と `< in` の入力側はオペランドから外す。

別枠にしているもの。

- `ssh` `scp` `rsync` `docker` `kubectl`: 別マシンでの実行なので `remote`
- `python3` `node` `perl` などのインタプリタ: コマンド行からは読み書きのどちらか判らないので `script`
- `wc` `git show` `diff`: 専用ツールに対応物がないので `other`。ただし `git show <rev>:<path>` は実際にはファイル全文を context に載せる読み取りであり、path スコープ rule を素通りする。現状は捕捉できていない

search 系統は現状ほぼ無意味。この環境では `Grep` / `Glob` ツールが提供されておらず、専用ツール側の母数がほぼ 0 になる。native が 0 の系統は出力に警告が出る。read と edit を見ること。

`other` が全セグメントの 6 割を占めるが、その大半は `git` `echo` `systemctl` `curl` などファイル操作でないコマンド。分類漏れではない。カバレッジ表の `unparsed` が増えていたら parser の劣化を疑う。

## hook で rule の発火率を直接測る

transcript 集計の Bash 置換率は代理指標にすぎない。`--rules` は 2 つの hook が残したログを突き合わせ、path スコープ付き rule が実際に読み込まれた割合を出す。

```bash
python3 ~/.claude/skills/tool-mix-audit/audit.py --rules
python3 ~/.claude/skills/tool-mix-audit/audit.py --rules --since 2026-09-10
```

- `~/.claude/logs/instructions-loaded.jsonl`: `InstructionsLoaded` hook が書く。分子。rule が載ったセッションと引き金ファイル
- `~/.claude/logs/bash-file-access.jsonl`: `PreToolUse(Bash)` hook が書く。分母側。Bash が触れたファイルのパス

`InstructionsLoaded` は成功しか記録しない。`cat` で読んだときは何も鳴らないため、Bash 側のログがなければ「沈黙した回数」が分からない。両方揃って初めて率になる。

数えているのはセッション数。`InstructionsLoaded` はセッションごと rule ごとに 1 回しか発火しないため、操作回数では比べられない。

### 判定の限界

glob の照合は `PurePosixPath.full_match` による近似で、Python 3.13 以降が要る。Claude Code 本体は gitignore 風の照合器を使っており、先頭の `/` の扱いなど細部が違う。`**/*.md` や `/**/*.sh` のような単純な形なら一致する。

Bash 側のログはコマンド本文を残さず、パスに見えるオペランドだけを絶対パスに解決して書く。コマンド行にトークンや鍵が載りうるため、glob 記号・シェル展開・拡張子もスラッシュも持たない語は捨てる。`find . -name '*.md' -exec grep -l <secret> {} +` から記録されるパスは 0 件になる。捨てすぎる方向に倒してあるので、`Makefile` のような拡張子なしのファイルは記録されない。

ユーザレベル rule (`~/.claude/rules`) の miss は全セッションから数えるが、プロジェクト rule (`<root>/.claude/rules`) は `<root>` 配下で動いたセッションだけから数える。

### 運用上の注意

`PreToolUse` hook のスクリプトが存在しないと、Bash 呼び出しが全部ブロックされる。`python3` が終了コード 2 を返し、`PreToolUse` ではそれが拒否を意味するため。観測用の hook が作業を止めるのは誤りなので、登録は `|| true` を付けてある。settings.json と hook スクリプトは同じコミットに入れること。

Bash 呼び出しごとに Python プロセスが 1 つ増える (実測 約 20ms)。`InstructionsLoaded` 側は matcher を `path_glob_match|nested_traversal|compact` に絞ってある。`session_start` を含めると起動のたびに rule と CLAUDE.md の本数だけ発火し、起動が遅くなる。起動時のベースラインも要るなら matcher を外す。

hook を 1 つも登録していなければ `InstructionsLoaded` イベントは発行されない。使わないなら登録を外すだけでコストは消える。

ログは所有者のみ読める権限 (`0600`) で作る。全プロジェクトの絶対パスが入るため。

## 過去の観測

モデル別の実測値、`CLAUDE_CODE_THRIFTY_SONIC` 前後比較の手順と基準値、比較上の交絡は `reference/observations.md` にある。前後比較を取るときだけ読めばよい。
