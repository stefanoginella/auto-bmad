# bash completion for auto-bmad
# Source this in ~/.bashrc:  source /path/to/completions/auto-bmad.bash

_auto_bmad() {
    local cur prev words cword
    _init_completion || return

    local commands="story epic help version"

    # Subcommand-specific flags
    local story_flags="--story --from-step --dry-run --skip-cache --skip-tea --reviews --skip-git --no-traces --help"
    local epic_flags="--epic --from-story --to-story --dry-run --no-merge --skip-cache --skip-tea --reviews --skip-git --no-traces --help"
    local reviews_values="full fast none"

    # Complete subcommand as first argument
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return
    fi

    # Determine which subcommand we're completing for
    local subcmd="${words[1]}"

    # Handle value completions for flags that take arguments
    case "$prev" in
        --reviews)
            COMPREPLY=( $(compgen -W "$reviews_values" -- "$cur") )
            return
            ;;
        --story|--from-step|--epic|--from-story|--to-story)
            # These take user-specific values — no completion
            return
            ;;
    esac

    # Complete flags for the active subcommand
    case "$subcmd" in
        story)
            COMPREPLY=( $(compgen -W "$story_flags" -- "$cur") )
            ;;
        epic)
            COMPREPLY=( $(compgen -W "$epic_flags" -- "$cur") )
            ;;
    esac
}

complete -F _auto_bmad auto-bmad
