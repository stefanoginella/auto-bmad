PREFIX ?= /usr/local
BINDIR  = $(PREFIX)/bin
BASH_COMPLETION_DIR = $(PREFIX)/share/bash-completion/completions
ZSH_COMPLETION_DIR  = $(PREFIX)/share/zsh/site-functions
REPO_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

.PHONY: install uninstall help

install:
	@echo "Installing auto-bmad..."
	@mkdir -p $(BINDIR)
	@chmod +x $(REPO_DIR)auto-bmad
	@ln -sf $(REPO_DIR)auto-bmad $(BINDIR)/auto-bmad
	@echo "  Symlinked $(BINDIR)/auto-bmad -> $(REPO_DIR)auto-bmad"
	@# Bash completion
	@mkdir -p $(BASH_COMPLETION_DIR)
	@cp $(REPO_DIR)completions/auto-bmad.bash $(BASH_COMPLETION_DIR)/auto-bmad
	@echo "  Installed bash completion -> $(BASH_COMPLETION_DIR)/auto-bmad"
	@# Zsh completion
	@mkdir -p $(ZSH_COMPLETION_DIR)
	@cp $(REPO_DIR)completions/_auto-bmad $(ZSH_COMPLETION_DIR)/_auto-bmad
	@echo "  Installed zsh completion  -> $(ZSH_COMPLETION_DIR)/_auto-bmad"
	@echo ""
	@echo "Done! Start a new shell or run:"
	@echo "  source $(BASH_COMPLETION_DIR)/auto-bmad    # bash"
	@echo "  autoload -Uz compinit && compinit           # zsh (if needed)"

uninstall:
	@echo "Uninstalling auto-bmad..."
	@rm -f $(BINDIR)/auto-bmad
	@echo "  Removed $(BINDIR)/auto-bmad"
	@rm -f $(BASH_COMPLETION_DIR)/auto-bmad
	@echo "  Removed bash completion"
	@rm -f $(ZSH_COMPLETION_DIR)/_auto-bmad
	@echo "  Removed zsh completion"
	@echo "Done."

help:
	@echo "auto-bmad Makefile"
	@echo ""
	@echo "  make install    Install auto-bmad to PATH with shell completions"
	@echo "  make uninstall  Remove auto-bmad and completions"
	@echo ""
	@echo "  PREFIX=/usr/local  (default, override with PREFIX=~/.local)"
