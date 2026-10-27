"""Executed by the Cangjie host, which supplies the `analysis` object."""

source = "// Пример\nmain() {\n    let value = 42\n    value\n}\n"
analysis.set_text(source)


def hover_at_last_value(text):
    return analysis.hover(text.encode("utf-8").rindex(b"value"))


# loupe measures UTF-8 bytes; Python's str indexes Unicode code points.
offset = source.encode("utf-8").rindex(b"value")
hover = hover_at_last_value(source)
assert hover is not None
assert (hover.start, hover.end) == (offset, offset + len(b"value"))
assert hover.items[0].code == "let value: Int64"
assert analysis.hover(-1) is None
assert analysis.hover(len(source.encode("utf-8")) + 1) is None
assert analysis.hover(0) is None
assert analysis.diagnostics() == []
print(hover.items[0].code)

# Reuse the same database: changing the initializer changes the inferred type.
source = source.replace("42", "1.5")
analysis.set_text(source)
offset = source.encode("utf-8").rindex(b"value")
assert analysis.hover(offset).items[0].code == "let value: Float64"
print(analysis.hover(offset).items[0].code)

analysis.set_text("main() {\n    let value = 42\n    let wrong: Bool = value\n}\n")
diagnostics = analysis.diagnostics()
assert any(
    item.severity == "error"
    and "mismatched types" in item.message
    and "Bool" in item.message
    and "Int64" in item.message
    for item in diagnostics
)
for item in diagnostics:
    print(f"{item.severity} [{item.start}, {item.end}): {item.message}")

analysis.set_text("main() {}")
assert analysis.diagnostics() == []
print("loupe Python example: OK")
