# Contributing

## Setup and build

Use the Cangjie 1.3.0 SDK with matching static stdx libraries under
`$CANGJIE_HOME/third_party/stdx` (see the platform paths in `cjpm.toml`).
Set `CANGJIE_HOME` and put the SDK tools on `PATH`.

From the repository root:

```sh
cjpm build
```

The workspace currently builds `modules/loupe4py`; `modules/py_interop` is not
a workspace member yet. Add tests for behavior changes when applicable and
describe how you checked the change in your pull request.

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

Keep pull requests focused. Explain the problem, what changed, and the checks
you ran.
