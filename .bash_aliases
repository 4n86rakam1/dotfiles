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

alias be="bundle exec"
alias g="git"
alias globalip="curl inet-ip.info"
alias grep="grep --color"
alias nocomgrep='grep "^[^#;]" --color=never'
alias syc="systemctl"
alias em="emacs"
alias dirusg="sudo du -h --max-depth=1 | sort -hrk1 | head -20"

if hash kubectl 2> /dev/null; then
    alias k="kubectl"
    complete -F __start_kubectl k
fi

path() { echo $PATH | tr : '\n'; }
[[ -f /usr/share/sounds/GNUstep/Tink.wav ]] && notify() { paplay /usr/share/sounds/GNUstep/Tink.wav; }

tfinit() {
    hash tflint > /dev/null && tflint
    terraform init
    terraform validate
    terraform apply
}

check_aws_credential() {
    aws sts get-caller-identity
    echo AWS_REGION: "${AWS_REGION:-none}"
    echo AWS_DEFAULT_REGION: "${AWS_DEFAULT_REGION:-none}"
}
