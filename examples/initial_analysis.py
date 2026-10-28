"""Request script using host-provided analysis and params; proposed API."""

document = analysis.document(params["document"])
hover = analysis.hover(document, params["offset"])
diagnostics = analysis.diagnostics(document)
targets = analysis.definition(document, params["offset"])

# Explicitly project detached values into the script's chosen result format.
result = {
    "revision": analysis.revision,
    "hover": None if hover is None else {
        "range": (hover.range.start, hover.range.end),
        "items": [
            {"code": item.code, "path": item.path, "doc": item.doc}
            for item in hover.items
        ],
    },
    "diagnostics": [
        {
            "range": (item.range.start, item.range.end),
            "severity": item.severity,
            "message": item.message,
            "unnecessary": item.unnecessary,
        }
        for item in diagnostics
    ],
    "definitions": [
        {
            "document": target.origin.document.uri,
            "revision": target.origin.revision,
            "space": target.origin.space,
            "expansion_id": target.origin.expansion_id,
            "full_range": (target.full_range.start, target.full_range.end),
            "focus_range": (target.focus_range.start, target.focus_range.end),
        }
        for target in targets
    ],
}

analysis.check_cancelled()
