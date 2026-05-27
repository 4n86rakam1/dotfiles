# CLAUDE.md

## 構造

`install` は `bootstrap/` 配下の実行可能ファイルをアルファベット順に実行する (`find | sort | xargs`)。順序制御が必要なスクリプトは `0_apt` のように数字プレフィックスを付ける。

bootstrap スクリプトのうち非自明なもの:

- `dotfiles_symlink` — `~` 配下への symlink を一元管理。新規ファイルをリポジトリ管理下に置く場合はスクリプト内の配列に追加する
- `dconf` — `dconf.d/*.conf` を `dconf load` で KDE/GNOME 設定に適用
- `tabby` — packagecloud の noble リリースに固定 (Ubuntu 26.04 未対応のため)

## コマンド

全体ではなく特定スクリプトだけ再実行したい場合:

```bash
./bootstrap/<script-name>
```
