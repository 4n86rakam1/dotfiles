# If not running interactively, do not do anything
[[ $- != *i* ]] && return

eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"

# tmux is enabled on qterminal only
if [[ $(ps -p ${PPID} -o cmd=) == *qterminal ]]; then
    tmux attach || exec tmux
fi

# ref: https://github.com/scop/bash-completion#installation
[[ $PS1 && -f /usr/share/bash-completion/bash_completion ]] && \
    . /usr/share/bash-completion/bash_completion

# shellcheck source=/dev/null
[[ -f ~/.bash_aliases ]] && . ~/.bash_aliases

hash direnv 2> /dev/null && eval "$(direnv hook bash)"

function man() {
    env \
        LESS_TERMCAP_md=$'\e[38;5;70m' \
        LESS_TERMCAP_me=$'\e[0m' \
        LESS_TERMCAP_so=$'\e[48;5;238m' \
        LESS_TERMCAP_se=$'\e[0m' \
        LESS_TERMCAP_us=$'\e[4;38;5;130m' \
        LESS_TERMCAP_ue=$'\e[0m' \
        man "$@"
}

COLOREND="\[\e[00m\]"
RED="\[\e[0;31m\]"
GREEN="\[\e[0;32m\]"
YELLOW="\[\e[0;33m\]"
WHITE="\[\e[0;37m\]"

function __my_parse_git_branch() {
    branch="$(git rev-parse --abbrev-ref HEAD 2> /dev/null)"
    test "${branch}" == "" && return 0

    if [[ -z "$(git status --short)" ]]; then
        echo "${GREEN} [${branch}]${COLOREND}"
    else
        echo "${RED} [${branch}]${COLOREND}"
    fi
}

function __my_custom_prompt() {
    tail="${WHITE}›${COLOREND}"
    PS1="${YELLOW}\w${COLOREND}$(__my_parse_git_branch) ${tail} "
}

__prompt_style="custom"

function __set_prompt() {
    if [[ "${__prompt_style}" == "custom" ]]; then
        __my_custom_prompt
    else
        PS1='$ '
    fi
}

function toggle_prompt() {
    if [[ "${__prompt_style}" == "custom" ]]; then
        __prompt_style="simple"
    else
        __prompt_style="custom"
    fi
}

__prompt_common_prefix="history -a; history -c; history -r"

PROMPT_DIRTRIM=3
PROMPT_COMMAND="${__prompt_common_prefix}; __set_prompt; ${PROMPT_COMMAND}"

HISTSIZE=-1
HISTFILESIZE=-1
HISTCONTROL=ignoreboth
shopt -s histappend

export LESS="-asXFMMRqix8 --mouse --wheel-lines=3"
