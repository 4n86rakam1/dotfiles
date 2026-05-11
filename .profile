# shellcheck source=/dev/null
test -f ~/.bashrc && . ~/.bashrc

[ -d "$HOME/.bin" ] && export PATH="$PATH:$HOME/.bin"
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"

export PATH="${ASDF_DATA_DIR:-$HOME/.asdf}/shims:$PATH"

export LC_TIME=C

# Added by LM Studio CLI tool (lms)
export PATH="$PATH:/home/maya/.lmstudio/bin"
