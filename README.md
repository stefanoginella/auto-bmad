# 🧩 Claude Code Plugins

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE) [![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin_Marketplace-blueviolet)](https://docs.anthropic.com/en/docs/claude-code)

My collection of opinionated Claude Code plugins — built by a solo dev for solo devs.

I'm a freelance developer exploring what AI-assisted development can actually look like when you give it real structure. These plugins are my experiments in that space, and I hope they can be useful to other developers too. If you have ideas for improvements or new plugins, please open an issue or submit a PR!

## 💡 Why

- **Opinionated by design.** These plugins make choices for you — that's the point. Less decision fatigue, more shipping.
- **Automation over discipline.** If a step can be encoded, it shouldn't depend on you remembering it. The plugin remembers so you don't have to.
- **Solo doesn't mean sloppy.** One person can ship with the rigor of a team when the tooling does the heavy lifting.

## 📦 Installation

Add the marketplace from the **Marketplace** tab of `/plugin` or directly:

```
/plugin marketplace add stefanoginella/claude-code-plugins
```

Then install individual plugins from the **Discover** tab of `/plugin` or directly:

```
/plugin install auto-bmad@claude-code-plugins
```

## 🔌 Available Plugins

| Plugin | Description |
|--------|-------------|
| [auto-bmad](./plugins/auto-bmad/README.md) | Automated and opinionated BMAD pipeline orchestration |
| [code-guardian](./plugins/code-guardian/README.md) | [EXPERIMENTAL] Deterministic security scanning layer. |

## 🤝 Contributing

Got an idea for a plugin or improvement? Open an issue or submit a PR. Check [CONTRIBUTING.md](./CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for details.

## ⚠️ Disclaimer

- **Experimental software.** These plugins are provided as-is, with no guarantees of stability, correctness, or fitness for production use. Use at your own risk.
- **Token usage.** Plugin operations can consume significant API tokens and credits. Pipelines involving multiple agents or long-running tasks may be especially costly. Monitor your usage.
- **AI-generated output.** All content produced by these plugins is AI-generated. Always review outputs before acting on them or committing them to your project.

## 📄 License

[MIT License](./LICENSE)
