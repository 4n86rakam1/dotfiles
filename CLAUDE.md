# CLAUDE.md

## 構造

`install` は `bootstrap/` 配下の実行可能ファイルをアルファベット順に実行する (`find | sort | xargs`)。順序制御が必要なスクリプトは `0_apt` のように数字プレフィックスを付ける。

bootstrap スクリプトのうち非自明なもの:

- `dotfiles_symlink` — `~` 配下への symlink を一元管理。新規ファイルをリポジトリ管理下に置く場合はスクリプト内の配列に追加する
- `dotfiles_symlink` の `.claude/rules/` — ファイル単位ではなくディレクトリごと symlink する。rule を増やしても配列の編集は要らないが、`~/.claude/rules/` へ置いたファイルは公開リポジトリの作業ツリー内に現れる。work 固有の rule を一時的に置く用途には使わない
- 既存の `~/.claude/rules` が実ディレクトリの場合、`ln -sfn` は置換せず内部に入れ子を作る。移行時は一度だけ `rm -r ~/.claude/rules` してから実行する
- `dconf` — `dconf.d/*.conf` を `dconf load` で KDE/GNOME 設定に適用
- `tabby` — packagecloud の noble リリースに固定 (Ubuntu 26.04 未対応のため)

## コマンド

全体ではなく特定スクリプトだけ再実行したい場合:

```bash
./bootstrap/<script-name>
```
