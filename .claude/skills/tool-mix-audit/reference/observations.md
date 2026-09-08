# 観測記録

前後比較を取るときだけ読めばよい。数値はモデル世代ごとに陳腐化する。

## THRIFTY_SONIC 無効化の前後比較

`.claude/settings.json` の `env` で `CLAUDE_CODE_THRIFTY_SONIC` を `"0"` にした前後を比べる手順。

適用前の基準値 (2026-09-05、opus-5 の steer あり・なしを合算、2 台合算)。

- read: 専用ツール 618 / Bash 1706 で bash 率 73.4%
- edit: 専用ツール 1455 / Bash 562 で bash 率 27.9%

適用後は `--since <適用日>` で切って同じ数字を出し、この値と比べる。

steer ラベルでは切れない。無効化すると `steerOnly` なセッションでは `auto_mode` attachment 自体が出なくなるため (`if (steerOnly && !bashFirst) return []`)、auto モードのセッションも `no-auto` に落ちる。適用後は `no-auto` の中身が「元 steer セッション + 元から通常モードのセッション」に変わり、母集団の構成がずれる。ラベルではなく日付で区切ること。

## 過去の観測から言えること

2026-09-05 時点、2 ホスト (host A / host B) での read 系統の bash 置換率。

- claude-opus-4-7: steer なし 21.1% (host B、44 セッション)。steer あり該当なし
- claude-opus-4-8: steer なし 7.1% (host B)。steer あり該当なし
- claude-sonnet-5: steer なし 44.6〜48.5% (host B)。steer あり該当なし
- claude-opus-5: steer なし 54.0% (host A) / 67.5% (host B)、steer あり 84.9% (host A) / 98.0% (host B)

効果は 2 段ある。モデルを opus-4-7 から opus-5 に替えるだけで 21% から 54〜68% に上がり、そこに bash-first steer が乗ると 85〜98% まで上がる。

auto モードそのものは原因ではない。opus-4-7 は auto モードでも 21.1% に留まる。steer を受け取らないためである。

edit 系統も同じ方向で、opus-4-7 の 3.4% に対し opus-5 は steer なし 20%、steer あり 39〜50%。`Write|Edit|MultiEdit` にマッチする PostToolUse フックはこの割合で素通りする。

限界として、steer あり・なしの比較は交絡している。steer が乗るのは auto / bypass モードのセッションで、その多くはバックグラウンドジョブであり、通常の対話セッションとは作業内容そのものが違う。因果を確定させたいなら `CLAUDE_CODE_THRIFTY_SONIC` を明示的に切り替えて同種のタスクを走らせる必要がある。

なお opus-4-7 系の数値は parser 修正前の集計。修正で `remote` と複数行コマンドの扱いが変わったため、opus-5 の値と厳密には比較できない。再取得するなら transcript が残っているうちに行うこと。
