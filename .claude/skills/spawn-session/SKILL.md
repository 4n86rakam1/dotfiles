---
name: spawn-session
description: 独立した bg session を新規起動して task を引き継ぐ。subagent (Agent tool) や `/fork` が生む「親に task notification で返す fork」ではなく、親から切り離された独立プロセスの session が欲しいときに使う。
argument-hint: "[--name 表示名] [--rc] 引き継ぎ内容"
disable-model-invocation: true
---

# /spawn-session

## 引数

`/spawn-session [--name "表示名"] [--rc] [引き継ぎ内容]`

- `--name "..."` と `--rc` は先頭に置く flag。両方指定する場合は順不同で可
- `--rc` は remote control を有効化する bare flag。`--remote-control` / `-rc` / `rc` も同義として受ける (default off)
- flag は引き継ぎ内容より前の連続した token 列でのみ解釈する。末尾や中間に置かれた同じ綴りは引き継ぎ内容の一部として扱う
- 引き継ぎ内容が空: 「何を引き継ぐか、1 行で」と 1 回だけ聞き、応答を素材にする

## 手順

### Step 1: cwd を確定

`pwd` で現在地を確認する。`claude --bg` は cwd 指定 flag を持たない (known issue: <https://github.com/anthropics/claude-code/issues/60975>) ため、Bash 実行時の cwd がそのまま spawn session の cwd になる。別ディレクトリで起動したければ `cd <path> && ...` を頭に付ける。

### Step 2: session 表示名を決定

Agent View と `/resume` picker で識別する短い名前を決める。優先順位は以下。

1. 引数で `--name "..."` が指定されていればそれを使う
2. なければ親 session 名から自動生成し、関連付ける

自動生成手順:

```bash
agents_json=$(claude agents --json 2>/dev/null) || exit 1
parent_name=$(printf '%s' "$agents_json" \
  | jq -r --arg id "$CLAUDE_CODE_SESSION_ID" '.[] | select(.sessionId==$id) | .name')
[ -z "$parent_name" ] && exit 1
base_name=$(printf '%s\n' "$parent_name" | sed -E 's/ #[0-9]+$//')
max_n=$(printf '%s' "$agents_json" \
  | jq -r --arg prefix "$base_name #" \
      '[.[] | .name | select(startswith($prefix)) | ltrimstr($prefix) | tonumber?] | max // 1')
candidate="$base_name #$((max_n + 1))"
```

`$candidate` を `--name` に渡す。CLI は同名 session を許容し自動連番を振らないため、番号は skill 側で採る。既存の兄弟 (`$base_name #N`) の最大値に 1 足した番号を使い、時系列と番号順を一致させる (例: 親 `foo #4`・既存 `foo #2 / foo #4` → 子 `foo #5`)。番号の空き (この例で `foo #3`) は埋めない。空き埋めは新しい兄弟を古いものより手前へ紛れ込ませて picker 上で誤読させるため、この skill では常に最新が最大番号になる方針を取る。

Fallback: 上記 script が exit 1 で抜けた場合 (`CLAUDE_CODE_SESSION_ID` 未設定・`claude agents --json` 失敗・`parent_name` 空のいずれか)、10-30 字で候補を 2-3 挙げてユーザーに選ばせる。

`--rc` 指定時は、決定した表示名を remote control session 名にも流用する。Agent View と remote control console の双方で同じ名前で識別できるよう揃える。

### Step 3: 引き継ぎ prompt を構築

新規 session は context を継承しない。以下を prompt 本文に明記する。

- 目標: 何をすべきか
- 背景: なぜ、判断済みの前提、関連会話の要点
- 参照: 関連 path・commit・PR・branch 名
- 完了条件: 何が揃えば task 終了か
- 制約: 触ってはいけない箇所、避ける手段

会話全体を圧縮したい場合は `handoff` skill を先に走らせて生成した doc を prompt 素材に使う。

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

`claude --bg` は起動直後に `backgrounded · <8-char-hex> · <name>` (ANSI escape 混在) の 1 行を stdout へ出す。ANSI を剥がした上で短 ID (`[0-9a-f]{8}`) と name を捕捉し、ユーザーに以下を返す。本文の再掲は不要。

- session 表示名
- session 短 ID (8 字)
- 起動 cwd
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
