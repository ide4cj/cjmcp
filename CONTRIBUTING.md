# Contributing

## Commits and pull requests

Install [Cocogitto](https://docs.cocogitto.io/guide/#installation) (`cog`), then
enable the commit message hook for your clone:

```sh
cog install-hook commit-msg
```

Use Conventional Commits, for example `feat: add a tool`, `fix: handle missing
input`, or `docs: clarify setup`. You can create a commit with
`cog commit docs "clarify setup"` after staging your changes. Run `cog check`
before opening a pull request; merge and fixup commits are ignored.
