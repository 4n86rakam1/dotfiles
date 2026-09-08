---
name: spawn-session
description: 独立した bg session を新規起動して task を引き継ぐ。subagent (Agent tool) や `/fork` が生む「親に task notification で返す fork」ではなく、親から切り離された独立プロセスの session が欲しいときに使う。
argument-hint: "[--cwd path] [--name 表示名] [--rc] 引き継ぎ内容"
disable-model-invocation: true
---

# /spawn-session

## 引数

`/spawn-session [--cwd <path>] [--name "表示名"] [--rc] [引き継ぎ内容]`

- `--cwd` / `--name "..."` / `--rc` は先頭に置く flag。複数指定する場合は順不同で可
- `--cwd <path>` は引き継ぎ先ディレクトリ。省略時は現在地。`@` を付けた path (`@~/Documents/logbook/`) も受ける
- `--rc` は remote control を有効化する bare flag。`--remote-control` / `-rc` / `rc` も同義として受ける (default off)
- flag は引き継ぎ内容より前の連続した token 列でのみ解釈する。末尾や中間に置かれた同じ綴りは引き継ぎ内容の一部として扱う
- 引き継ぎ内容が空: 「何を引き継ぐか、1 行で」と 1 回だけ聞き、応答を素材にする

## 手順

### Step 1: cwd を確定

`claude --bg` は cwd 指定 flag を持たない (known issue: <https://github.com/anthropics/claude-code/issues/60975>) ため、Bash 実行時の cwd がそのまま spawn session の cwd になる。`cd <path> && ...` を頭に付けて制御する。

Step 2 以降は解決済みの絶対 path を `<target-cwd>` という literal で参照する。Bash tool は呼び出し間で shell 変数を保持しないため、Step をまたぐ値は変数ではなく literal で埋める。環境変数 (`$HOME` / `$CLAUDE_CODE_SESSION_ID`) だけは各呼び出しで有効。

`--cwd` 省略時は `pwd -P` の出力を `<target-cwd>` とする。`-P` を付けるのは指定時の `realpath -m` と正規形を揃えるため。symlink 経由で入ったディレクトリでは `pwd` が論理 path を、`realpath -m` が物理 path を返して食い違う。

指定時は `--cwd` に渡された文字列を以下で正規化し、その stdout を `<target-cwd>` とする。

```bash
raw='<raw-arg>'
raw="${raw#@}"
case "$raw" in
  '~' | '~/'*) raw="$HOME${raw#\~}" ;;
esac
realpath -m "$raw"
```

`@` 付きを受けるのは、入力時に path 補完が効くのが `@` 経路のみのため。`realpath -m` を通すのは、相対 path・`..`・末尾スラッシュ・重複スラッシュ・symlink を畳んで絶対形に揃えるため。Step 2 の cwd 比較は単純な文字列比較であり、両辺が正規形でないと同一ディレクトリを別物と誤判定する。`~user` 形式は展開しない (存在しない path として次の検証で弾かれる)。path 自体にシングルクォートが含まれる場合は 1 行目の埋め込みが壊れるため、その場合のみ `raw` への代入を heredoc に置き換える。`@` mention はディレクトリ一覧を context へ注入する副作用があるが、起動先には影響しない。

指定時は以下で存在を検証し、`missing` なら中断して正規化後の path をユーザーに返す。

```bash
[ -d '<target-cwd>' ] && printf 'ok\n' || printf 'missing\n'
```

trust の事前確認は行わない。`~/.claude.json` の `.projects` に未登録で、trust 済みの祖先も持たない dir を `--cwd` に渡しても、bg session は trust dialog で停止せず起動して完走する (`/tmp` 配下で実測)。起動後に `hasTrustDialogAccepted: false` のまま `.projects` へ登録される。`.projects` を引いて警告を出すと、git worktree や未訪問の dir すべてに起きない停止を警告することになる。

### Step 2: session 表示名を決定

Agent View と `/resume` picker で識別する短い名前を決める。優先順位は以下。

1. 引数で `--name "..."` が指定されていればそれを使う
2. なければ target-cwd から自動生成する。親と同じ cwd なら親 session 名に、異なるなら target-cwd の basename に関連付ける

自動生成手順:

```bash
agents_json=$(claude agents --json 2>/dev/null) || exit 1
parent=$(printf '%s' "$agents_json" \
  | jq -r --arg id "$CLAUDE_CODE_SESSION_ID" '.[] | select(.sessionId==$id) | "\(.name)\t\(.cwd)"')
[ -z "$parent" ] && exit 1
parent_name=${parent%%$'\t'*}
parent_cwd=$(realpath -m "${parent##*$'\t'}")
if [ "<target-cwd>" = "$parent_cwd" ]; then
  base_name=$(printf '%s\n' "$parent_name" | sed -E 's/ #[0-9]+$//')
  floor=1
else
  base_name=$(basename "<target-cwd>")
  floor=0
fi
max_n=$(printf '%s' "$agents_json" \
  | jq -r --arg prefix "$base_name #" --argjson floor "$floor" \
      '[.[] | .name | select(startswith($prefix)) | ltrimstr($prefix) | tonumber?] | max // $floor')
printf '%s #%s\n' "$base_name" "$((max_n + 1))"
```

出力された名前を `--name` に渡す。CLI は同名 session を許容し自動連番を振らないため、番号は skill 側で採る。既存の兄弟 (`$base_name #N`) の最大値に 1 足した番号を使い、時系列と番号順を一致させる (例: 親 `foo #4`・既存 `foo #2 / foo #4` → 子 `foo #5`)。番号の空き (この例で `foo #3`) は埋めない。空き埋めは新しい兄弟を古いものより手前へ紛れ込ませて picker 上で誤読させるため、この skill では常に最新が最大番号になる方針を取る。

base_name は `<target-cwd>` が親 session の cwd と一致するかで切り替える。一致する場合は親名から番号を落としたもの、異なる場合は `<target-cwd>` の `basename` を使う。別プロジェクトへ渡した session に引き継ぎ元の名前を付けると、picker 上で名前と cwd がずれて読めなくなるため。max+1 の規則は両者共通で、親 `resume #4` から `~/Documents/logbook` へ渡す場合、既存 `logbook #N` が無ければ子は `logbook #1`、`logbook #1 / #2` があれば `logbook #3` になる。

`parent_cwd` も `realpath -m` を通す。`claude agents --json` が返す cwd は正規化されておらず、`<target-cwd>` だけ物理 path に揃えると、symlink 経由で入った session が自分自身の cwd を別ディレクトリと誤判定する。

`floor` の差は、親自身をその系列の 1 番目として数えるかどうかを表す。同一 cwd では親が系列に含まれるので `1` から、別 cwd では親が無関係なので `0` から数える。

basename が同じ別プロジェクト (`~/Documents/logbook` と `~/dev/logbook` など) は番号系列を共有する。分けたい場合は `--name` で明示する。

Fallback: 上記 script が exit 1 で抜けた場合 (`CLAUDE_CODE_SESSION_ID` 未設定・`claude agents --json` 失敗・親 session の行が空のいずれか)、10-30 字で候補を 2-3 挙げてユーザーに選ばせる。

`--rc` 指定時は、決定した表示名を remote control session 名にも流用する。Agent View と remote control console の双方で同じ名前で識別できるよう揃える。

### Step 3: 引き継ぎ prompt を構築

新規 session は context を継承しない。以下を prompt 本文に明記する。

- 目標: 何をすべきか
- 背景: なぜ、判断済みの前提、関連会話の要点
- 参照: 関連 path・commit・PR・branch 名
- 完了条件: 何が揃えば task 終了か
- 制約: 触ってはいけない箇所、避ける手段

会話全体を圧縮したい場合は `handoff` skill を先に走らせて生成した doc を prompt 素材に使う。

`--cwd` で別プロジェクトへ渡す場合、新 session は引き継ぎ元の CLAUDE.md も会話も持たない。引き継ぎ元のファイルを参照させるなら、絶対 path で「参照」項に明記する。

### Step 4: 実行

Bash tool で以下を実行する。

```bash
cd "<target-cwd>" && claude --bg --name "<name>" "<prompt>"
```

`--rc` 指定時は `--remote-control "<name>"` を追加する。

```bash
cd "<target-cwd>" && claude --bg --name "<name>" --remote-control "<name>" "<prompt>"
```

prompt に shell metachar (`$`, `` ` ``, `\`, `"`) が含まれる場合、ダブルクォート内での escape に注意する。長文や複雑な引用符が絡む場合は heredoc やファイル経由も検討する。

### Step 5: 報告

`claude --bg` は起動直後に `backgrounded · <8-char-hex> · <name>` (ANSI escape 混在) の 1 行を stdout へ出す。ANSI を剥がした上で短 ID (`[0-9a-f]{8}`) と name を捕捉する。cwd は意図値ではなく実測を返す。

```bash
claude agents --json | jq -r --arg id "<短 ID>" '.[] | select(.id==$id) | .cwd'
```

出力が空の場合 (登録が間に合わない等)、`<target-cwd>` を未確認の値として明示した上で報告する。cwd 行を省かない。

ユーザーに以下を返す。本文の再掲は不要。

- session 表示名
- session 短 ID (8 字)
- 起動 cwd (実測値)
- 状態確認: `claude agents --json` (script 向け)・`claude agents` (TUI)
- 追加指示: `SendMessage(to: "<name>", message: "...")` (name / full UUID を受ける)

full UUID が必要な場面は `claude agents --json | jq -r '.[] | select(.id=="<短 ID>") | .sessionId'` で解決する。

## 注意事項

起動 session の model / effort は Agent View の default (`claude agents --model ...` / `--effort ...`) が適用される。想定 model を強制したい場合は prompt 冒頭に明記する。

## Out of scope (yagni)

- 起動後の完了 poll。`SendMessage` と `ListAgents` はユーザー判断で使う
- prompt 内容の自動生成。引き継ぎ内容はユーザーまたは呼び出し元 skill が組み立てる
- fork 系 (`/fork` / `Agent(subagent_type:"fork")`) の呼び分け。別 skill または直接呼び出しに委ねる

## 関連

- `handoff` skill: 会話を doc に圧縮して次 session に渡す。この skill と組み合わせて prompt 素材を作れる
- `/fork` slash command / `Agent(subagent_type:"fork")`: 親に task notification で返す bg subagent (fork)。独立 session ではないため、この skill が想定する用途とは別物
