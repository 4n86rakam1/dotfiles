case `uname` in
    Linux)
        alias ls='ls --color -F'
        alias ll='ls --color -alF'
        alias la='ls --color -A'
        alias pbcopy="xsel --clipboard --input"
        ;;
    Darwin)
        alias ls='ls -FG'
        alias la='ls -aFG'
        alias ll='ls -alFG'
        ;;
esac

alias g="git"
alias globalip="curl inet-ip.info"
alias grep="grep --color"
alias nocomgrep='grep "^[^#;]" --color=never'
alias dirusg="sudo du -h --max-depth=1 | sort -hrk1 | head -20"

if hash kubectl 2> /dev/null; then
    alias k="kubectl"
    complete -F __start_kubectl k
fi

path() { echo $PATH | tr : '\n'; }
[[ -f /usr/share/sounds/GNUstep/Tink.wav ]] && notify() { paplay /usr/share/sounds/GNUstep/Tink.wav; }

# claude --bg starts the session in the caller's cwd, so wrap cd to spawn a
# session for a project the agent view cannot dispatch to.
cbg() {
    local dir=$1
    if [[ -z ${dir} ]]; then
        echo "usage: cbg <directory> [claude args...]" >&2
        return 1
    fi
    shift
    (cd "${dir}" && claude --bg "$@")
}

# Only the first word is a directory; the rest are passed through to claude
_cbg() {
    local IFS=$'\n' # keep a directory name containing spaces as one candidate
    (( COMP_CWORD == 1 )) && COMPREPLY=($(compgen -d -- "${COMP_WORDS[COMP_CWORD]}"))
}
complete -o filenames -o default -F _cbg cbg

tfinit() {
    hash tflint > /dev/null && tflint
    terraform init
    terraform validate
    terraform apply
}
