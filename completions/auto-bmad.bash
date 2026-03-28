# bash completion for auto-bmad
# Source this in ~/.bashrc:  source /path/to/completions/auto-bmad.bash
# NOTE: Keep in sync with auto-bmad, auto-bmad-story, auto-bmad-epic parsers

_auto_bmad() {
    local cur prev words cword
    _init_completion || return

    local commands="story epic status quickstart validate config help version"

    # Subcommand-specific flags
    local story_flags="--story --from-step --dry-run --skip-cache --skip-tea --reviews --skip-git --no-traces --debug --help"
    local epic_flags="--epic --from-story --to-story --dry-run --no-merge --skip-cache --skip-tea --reviews --skip-git --no-traces --debug --help"
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
        --from-step)
            # Complete with known step IDs
            COMPREPLY=( $(compgen -W "0.1 1.1 1.2 1.3 1.4 2.1 2.2 3.1 3.2 3.3 3.4 3.4b 3.5 4.1 4.2 5.1 5.2 5.3 5.4 5.5 5.6 6.0 6.1 6.2" -- "$cur") )
            return
            ;;
        --story|--epic|--from-story|--to-story)
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
