package runtime_probe

import py_interop.*
import py_interop.internal_macros.*
import std.env.*
import std.runtime.*
import std.ref.*

@DerivePython
public struct Entry {
    public Entry(public let n: Int64, public let text: String) {}
}
@DerivePython
public class Owner {
    public var calls: Int64 = 0
    @PyIgnore public let hidden: Int64 = 42
    private var saved: ?((Int64) -> String) = None
    public init() {}
    public func choose(): Int64 { 1 }
    public func choose(value: Int64): Int64 { value }
    public func save(f: (Int64) -> String) { saved = f }
    public func callSaved(): String { saved.getOrThrow()(8) }
    public func next(): Entry {
        calls++
        Entry(calls, "owned")
    }
}
@DerivePython
extend Entry { public func doubled(): Int64 { n * 2 } }
@DerivePython
public open class Base {
    public init() {}
    public func baseValue(): Int64 { 11 }
}
@DerivePython
public class Derived <: Base { public init() { super() } }
@DerivePython
public func echo(s: String): String { s }
@DerivePython
public func record(e: Entry): Entry { e }
@DerivePython
public func entries(es: Array<Entry>): Array<Entry> { es }
@DerivePython
public func strings(xs: Array<String>): Array<String> { xs }
@DerivePython
public func optional(x: ?String): ?String { x }
@DerivePython
public func nested(xs: ?Array<Entry>): ?Array<Entry> { xs }
@DerivePython
public func pair(p: (Int64, String)): (Int64, String) { p }
@DerivePython
public func pairs(ps: Array<(Int64, String)>): Int64 { ps.size }
@DerivePython
public func triple(p: (Int64, String, Bool)): Int64 { p[0] }
@DerivePython
public func tripleOut(): (Int64, String, Bool) { (3, "три", true) }
@DerivePython
public func invoke(f: (Int64) -> String): String { f(7) }
@DerivePython
public func defaulted(limit!: Int64 = 5): Int64 { limit }
@DerivePython
public func explode(): String { throw Exception("cj-boom") }

func context(owner: Owner): PyDict<String, PyObj> {
    PyDict([
        ("Entry", Entry.pyClass()), ("Owner", Owner.pyClass()),
        ("Base", Base.pyClass()), ("Derived", Derived.pyClass(marker: PyInteropTypeMarker<Derived>())),
        ("owner", toPyObj(owner)),
        ("echo", PythonTopLevelFunctions.echo),
        ("record", PythonTopLevelFunctions.record),
        ("entries", PythonTopLevelFunctions.entries),
        ("strings", PythonTopLevelFunctions.strings),
        ("optional", PythonTopLevelFunctions.optional),
        ("nested", PythonTopLevelFunctions.nested),
        ("pair", PythonTopLevelFunctions.pair),
        ("pairs", PythonTopLevelFunctions.pairs),
        ("triple", PythonTopLevelFunctions.triple),
        ("tripleOut", PythonTopLevelFunctions.tripleOut),
        ("invoke", PythonTopLevelFunctions.invoke),
        ("defaulted", PythonTopLevelFunctions.defaulted),
        ("explode", PythonTopLevelFunctions.explode)
    ])
}
func tracked(ctx: PyDict<String, PyObj>): (WeakRef<Owner>, Int64) {
    let value = Owner()
    let proxy = toPyObj(value)
    let id = unsafe { CPointer<CangjiePyObjStorage>(proxy.getRef().getPtr()).read().registryId }
    ctx.setItem("tracked", proxy)
    (WeakRef(value, CleanupPolicy.EAGER), id)
}
func unowned(): WeakRef<Owner> {
    WeakRef(Owner(), CleanupPolicy.EAGER)
}
func collect<T>(ref: WeakRef<T>): Bool where T <: Object {
    for (_ in 0..20) {
        gc(heavy: true)
        sleep(Duration.millisecond * 10)
        if (ref.value.isNone()) { return true }
    }
    false
}
func requestResult(owner: Owner): PyObj {
    let scope = context(owner)
    withGIL { Python.eval("owner.next()", locals: scope) }
}
func temporaryPythonReference() {
    let value = Python.eval("__import__('builtins').sentinel")
    blackBox(value)
}
main() {
    let args = getCommandLine()
    try {
        Python.load(args[1])
        println("LOADED ${Python.getVersion()}")
        let owner = Owner()
        let ctx = context(owner)
        if (args[2] == "result_after_request") {
            let result = requestResult(owner)
            for (_ in 0..20) {
                gc(heavy: true)
                sleep(Duration.millisecond * 10)
            }
            withGIL {
                ctx.setItem("result", result)
                Python.exec("assert result.n == 1 and result.text == 'owned'", locals: ctx)
            }
            blackBox(owner)
        } else if (args[2] == "reload") {
            Python.unload()
            Python.load(args[1])
            withGIL { Python.exec("assert owner.next().n == 1", locals: context(owner)) }
        } else if (args[2] == "ownership") {
            let baseline = unowned()
            if (!collect(baseline)) { throw Exception("GC control failed") }
            let (weak, id) = withGIL { tracked(ctx) }
            withGIL { Python.exec("del tracked; import gc; gc.collect()", locals: ctx) }
            let freed = collect(weak)
            println("REGISTRY_FREED ${freed}")
            // Removing the registry root separately distinguishes it from GC latency.
            PyProxy.del(id)
            println("AFTER_REGISTRY_DELETE ${collect(weak)}")
            blackBox(ctx)
        } else if (args[2] == "reference_gc") {
            withGIL {
                Python.exec("import builtins; builtins.sentinel = []")
                temporaryPythonReference()
                Python.exec("del __import__('builtins').sentinel")
            }
            for (_ in 0..20) {
                gc(heavy: true)
                sleep(Duration.millisecond * 10)
            }
        } else if (args[2] == "reference_native") {
            withGIL {
                let value = Python.eval("[]")
                ctx.setItem("sentinel", value)
                Python.exec("import sys; before = sys.getrefcount(sentinel)", locals: ctx)
                let ptr = value.getRef().getIncPtr()
                Python.exec("assert sys.getrefcount(sentinel) == before + 1", locals: ctx)
                unsafe { Py_DecRef(ptr) }
                Python.exec("assert sys.getrefcount(sentinel) == before", locals: ctx)
            }
        } else if (args[2] == "same_dict") {
            withGIL {
                Python.getBuiltinsAttr("exec").getOrThrow()([toPyObj(args[3]), ctx, ctx])
            }
        } else if (args[2] == "without_gil") {
            Python.exec(args[3], locals: ctx)
        } else if (args[2] == "threads") {
            let jobs = Array(4, { _ => spawn { withGIL { Python.exec(args[3], locals: context(owner)) } } })
            for (job in jobs) { job.get() }
        } else if (args[2] == "repeat") {
            for (_ in 0..100) {
                withGIL { Python.exec(args[3], locals: context(owner)) }
            }
            if (owner.calls != 100) { throw Exception("owner state lost") }
        } else if (args[2] == "python_error") {
            try {
                withGIL { Python.exec(args[3], locals: ctx) }
                throw Exception("Python error not propagated")
            } catch (e: Exception) {
                if (!e.toString().contains("py-boom")) { throw e }
                println("PYTHON_EXCEPTION ${e.toString()}")
                withGIL { Python.exec("assert 2 + 2 == 4", locals: ctx) }
            }
        } else {
            withGIL { Python.exec(args[3], locals: ctx) }
        }
        if (args[2] == "unload") {
            Python.unload()
            gc(heavy: true)
            sleep(Duration.millisecond * 100)
        }
        println("PASS")
    } catch (e: Exception) {
        eprintln(e.toString())
        return 1
    }
    return 0
}
