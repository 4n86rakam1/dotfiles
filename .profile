# shellcheck source=/dev/null
test -f ~/.bashrc && . ~/.bashrc

[ -d "$HOME/.bin" ] && export PATH="$PATH:$HOME/.bin"
[ -d "$HOME/.local/bin" ] && export PATH="$HOME/.local/bin:$PATH"

test -d ~/.linuxbrew && eval "$(~/.linuxbrew/bin/brew shellenv)"
test -d /home/linuxbrew/.linuxbrew && eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"

if [ -d "$HOME/.rbenv" ]; then
    export PATH="$HOME/.rbenv/bin:$PATH"
    eval "$(rbenv init -)"
fi

if hash n 2> /dev/null; then
    export N_PREFIX="$HOME/.n"
    export PATH="$PATH:$N_PREFIX/bin"
fi

if hash go 2> /dev/null; then
    export GOPATH=~/.go
    gopath=$(go env GOPATH)
    export PATH="${gopath}/bin:$PATH"
    unset gopath
fi

if [ -d "$HOME/.cargo/bin" ]; then
    export PATH="$HOME/.cargo/bin:$PATH"
fi

export LC_TIME=C
