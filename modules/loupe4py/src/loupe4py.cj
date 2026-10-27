package loupe4py

import loupe.{diagnostics, hoverAt, Severity}
import loupe.db.{AnalysisDatabase, Cfg, ModuleModel, PackageModel, ProjectModel}
import loupe.vfs.{FileId, PathInterner, VfsPath}
import py_interop.*
import py_interop.internal_macros.*
import rope.Rope

/** A hover candidate, with plain Cangjie code and optional documentation. */
@DerivePython
public class HoverItem {
    public HoverItem(public let code: String, public let path: ?String, public let doc: ?String) {}
}

/** A hover's half-open UTF-8 byte range and its candidates. */
@DerivePython
public class HoverResult {
    public HoverResult(public let start: Int64, public let end: Int64, public let items: Array<HoverItem>) {}
}

/** A diagnostic's half-open UTF-8 byte range, severity and message. */
@DerivePython
public class Diagnostic {
    public Diagnostic(public let start: Int64, public let end: Int64, public let severity: String,
        public let message: String) {}
}

/**
 * Analysis of one in-memory file in the `default` package, without SDK packages or dependencies.
 * The host must serialize calls; the database and its incremental cache live across text updates.
 */
@DerivePython
public class Analysis {
    private let db = AnalysisDatabase()
    private let paths = PathInterner()
    private let file: FileId
    private var size: Int64 = 0

    public init() {
        let root = VfsPath.virtual("untitled:/")
        let path = VfsPath.virtual("untitled:/example.cj")
        file = paths.intern(path)
        db.setProject(ProjectModel(Cfg([]), [ModuleModel("default", root, [PackageModel("default", root, [path])])]),
            paths)
        db.setFileText(file, Rope())
    }

    /** Replaces the complete source text and invalidates affected analysis queries. */
    public func set_text(text: String): Unit {
        db.setFileText(file, Rope(text))
        size = text.size
    }

    /** Returns hover information, or None for an out-of-bounds offset or no hover target. */
    public func hover(offset: Int64): ?HoverResult {
        if (offset < 0 || offset > size) {
            return None
        }
        hoverAt(db.snapshot(), file, offset).map {
            result => HoverResult(result.range.start, result.range.end,
                result.items.map {item => HoverItem(item.code, item.path, item.doc)})
        }
    }

    /** Returns syntax and semantic diagnostics for the current text. */
    public func diagnostics(): Array<Diagnostic> {
        diagnostics(db.snapshot(), file).map {
            one =>
                let severity = match (one.severity) {
                    case Severity.Error => "error"
                    case Severity.Warning => "warning"
                    case Severity.Hint => "hint"
                }
                Diagnostic(one.range.start, one.range.end, severity, one.message)
        }
    }
}
