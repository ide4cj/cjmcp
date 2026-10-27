package loupe4py_example

import std.fs.File
import loupe4py.Analysis
import py_interop.*

main(args: Array<String>): Int64 {
    if (args.size != 1) {
        eprintln("usage: loupe4py_example <script.py>")
        return 2
    }
    try {
        let script = String.fromUtf8(File.readFrom(args[0]))
        Python.load()
        // The host owns the session; scripts share its database through this proxy.
        let analysis = Analysis()
        let context = PyDict<String, PyObj>([("analysis", analysis.toPyObj())])
        let invocation = PyDict<String, PyObj>([("script", PyString(script)), ("context", context)])
        try {
            // Functions and comprehensions must see the same namespace as top-level statements.
            Python.exec("exec(script, context, context)", locals: invocation)
        } finally {
            Python.exec("import sys; sys.stdout.flush(); sys.stderr.flush()")
        }
        return 0
    } catch (e: Exception) {
        eprintln(e.toString())
        return 1
    }
}
