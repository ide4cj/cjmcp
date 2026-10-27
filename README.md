# cjmcp

An initial experiment exposing loupe language analysis to an embedded Python
interpreter through `py_interop` and `@DerivePython`.

## Run the example

Requires Linux, Cangjie 1.3.0 with stdx, and a CPython shared library. From the
repository root:

```sh
cjpm build
PYTHON_DYNLIB=/usr/lib/libpython3.14.so \
    cjpm run --skip-build --name loupe4py_example -- examples/loupe.py
```

Set `PYTHON_DYNLIB` to your installed `libpython3.x.so`. It may be omitted when
`py_interop` can discover the library automatically.

The Cangjie executable owns an `Analysis` session and supplies it to the Python
script as `analysis`. The script replaces the source text, reads a local
variable's inferred type through hover, changes that type, and checks semantic
diagnostics. Assertions make the example an executable integration check.
An arbitrary script path can be passed in place of `examples/loupe.py`; a Python
exception makes the host exit unsuccessfully.

## Minimal API

`Analysis` owns one virtual file in the `default` package. Source should omit a
`package` declaration. Calls are sequential, and each query reads a fresh
snapshot of the persistent database.

- `analysis.set_text(text)` replaces the file's complete source.
- `analysis.hover(offset)` returns `None` or an object with `start`, `end`, and
  `items`. Each item has `code`, optional `path`, and optional `doc`.
- `analysis.diagnostics()` returns a list of objects with `start`, `end`,
  `severity` (`error`, `warning`, or `hint`), and `message`.

Offsets and half-open ranges are **UTF-8 byte offsets**, so compute them against
`source.encode("utf-8")` in Python.

This example does not load a project, SDK packages, or external macros. It
demonstrates local inference through hover; a structural inference API and the
MCP transport are future work. The embedding currently uses `py_interop`'s proxy
lifetime and callback exception behavior directly; this is a short-lived example,
not yet a long-running script service.
