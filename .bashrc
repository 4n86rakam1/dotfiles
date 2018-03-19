# alias
alias ls='ls -FG'
alias la='ls -aFG'
alias ll='ls -alFG'
alias airport="/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
alias updatedb="sudo /usr/libexec/locate.updatedb"
alias path="echo $PATH | tr : '\n'"
alias ocaml="rlwrap ocaml"
alias mac_sleep="osascript -e 'tell application \"Finder\" to sleep'"
alias rebuild_spotlight_index="sudo mdutil -E /"
alias chrome="/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"
alias be="bundle exec"
alias g="git"

# color
COLOREND="\[\e[00m\]"
BLACK="\[\e[0;30m\]"
RED="\[\e[0;31m\]"
GREEN="\[\e[0;32m\]"
YELLOW="\[\e[0;33m\]"
BLUE="\[\e[0;34m\]"
PURPLE="\[\e[0;35m\]"
CYAN="\[\e[0;36m\]"
WHITE="\[\e[0;37m\]"

# get current branch
function parse_git_branch() {
    branch="$(git branch --no-color 2> /dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/ [\1]/')"
    if [[ $branch != "" ]]; then
        if [[ $(git status 2> /dev/null | tail -n1) == "nothing to commit, working tree clean" ]]; then
            echo "${GREEN}$branch${COLOREND} "
        else
            echo "${RED}$branch${COLOREND} "
        fi
    fi
}

function promps() {
    tail="${BLUE}›${COLOREND} "
    PS1="${YELLOW}\w${COLOREND}$(parse_git_branch)${tail}"
}

function venv_prompt() {
    if [[ ! -z "${VIRTUAL_ENV}" ]]; then
        PYTHON_VERSION=`python -V | sed -e 's/Python //g'`
        PS1="${CYAN}(`basename ${VIRTUAL_ENV}`)${COLOREND}:${CYAN}${PYTHON_VERSION}${COLOREND} ${PS1}"
    fi
}

export PROMPT_COMMAND="promps; venv_prompt; $PROMPT_COMMAND"
