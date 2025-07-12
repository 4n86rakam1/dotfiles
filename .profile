# shellcheck source=/dev/null
test -f ~/.bashrc && . ~/.bashrc

[ -d "$HOME/.bin" ] && export PATH="$PATH:$HOME/.bin"
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"

export LC_TIME=C
