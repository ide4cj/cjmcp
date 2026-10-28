#!/usr/bin/env python3
"""Audit an already built py_interop in isolated compile/runtime subprocesses."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import re
import shutil
import subprocess
import sys
import sysconfig

RUNTIME = {
    'inheritance': ('run', 'assert Derived().baseValue() == 11'),
    'selection': ('run', 'assert not hasattr(owner, "hidden")'),
    'overloads': ('run', 'assert owner.choose() == 1; assert owner.choose(4) == 4'),
    'extension': ('run', 'assert Entry(3, "three").doubled() == 6'),
    'class_mutation': ('run', 'owner.calls = 40; assert owner.next().n == 41'),
    'invalid_setter': ('run', 'owner.calls = "bad"; assert owner.calls == 0'),
    'invalid_ctor': ('run', 'Entry("bad", "value")'),
    'forged_identity': ('run', 'class Fake: __cangjie_identity__ = True\nrecord(Fake())'),
    'registration': ('run', 'assert callable(echo) and isinstance(Entry, type)'),
    'unicode': ('run', 'assert echo("Привет 🐍") == "Привет 🐍"'),
    'nul_string': ('run', 'assert echo("a\\0b") == "a\\0b"'),
    'record': ('run', 'e = record(Entry(9, "девять")); assert (e.n, e.text) == (9, "девять")'),
    'array_string': ('run', 'assert strings(["a", "б"]) == ["a", "б"]'),
    'array_record': ('run', 'es = entries([Entry(2, "two")]); assert es[0].n == 2'),
    'option': ('run', 'assert optional(None) is None; assert optional("yes") == "yes"'),
    'nested': ('run', 'assert nested(None) is None; assert nested([Entry(4, "four")])[0].text == "four"'),
    'pair': ('run', 'assert pair((2, "два")) == (2, "два")'),
    'array_pair_in': ('run', 'assert pairs([(1, "one"), (2, "two")]) == 2'),
    'triple_out': ('run', 'assert tripleOut() == (3, "три", True)'),
    'triple_in': ('run', 'assert triple((3, "three", True)) == 3'),
    'triple_short': ('run', 'triple((3, "three"))'),
    'callback': ('run', 'assert invoke(lambda n: str(n)) == "7"'),
    'callback_retention': ('run', 'import weakref, gc\nclass F:\n def __call__(self, n): return str(n)\nf = F(); weak = weakref.ref(f); owner.save(f); assert owner.callSaved() == "8"; del f; gc.collect(); assert weak() is not None'),
    'callback_error': ('run', 'invoke(lambda n: 1 / 0)'),
    'callback_wrong_return': ('run', 'invoke(lambda n: 123)'),
    'callback_noncallable': ('run', 'invoke(123)'),
    'wrong_string': ('run', 'echo(123)'),
    'missing_arg': ('run', 'echo()'),
    'extra_arg': ('run', 'echo("a", "b")'),
    'wrong_record': ('run', 'record("bad")'),
    'wrong_array': ('run', 'strings([1])'),
    'default_explicit': ('run', 'assert defaulted(limit=8) == 8'),
    'default_omitted': ('run', 'assert defaulted() == 5'),
    'cj_exception': ('run', 'explode()'),
    'python_exception': ('python_error', 'raise ValueError("py-boom")'),
    'result_lifetime': ('run', 'import gc; result = owner.next(); gc.collect(); assert result.text == "owned"'),
    'fresh_scope': ('repeat', 'assert "previous_request" not in locals(); previous_request = 1; result = owner.next(); assert result.n > 0'),
    'threads_gil': ('threads', 'assert echo("thread") == "thread"'),
    'scope_function': ('run', 'def f(): return owner.next().n\nassert f() == 1'),
    'scope_function_adapter': ('same_dict', 'def f(): return owner.next().n\nassert f() == 1'),
    'without_outer_gil': ('without_gil', 'assert echo("lock") == "lock"'),
    'registry_release': ('ownership', ''),
    'reference_gc': ('reference_gc', ''),
    'reference_native': ('reference_native', ''),
    'result_after_request': ('result_after_request', ''),
    'reload': ('reload', ''),
    'unload': ('unload', 'assert record(Entry(1, "end")).n == 1'),
}
COMPILE = {
    'control': 'public func control(s: String): PyObj { toPyObj(s) }',
    'generic': '@DerivePython public class Box<T> { public Box(public let value: T) {} }',
    'concrete_generic': 'public class Box<T> { public Box(public let value: T) {} }\n@DerivePython public func unbox(x: Int64): Int64 { Box<Int64>(x).value }',
    'unbound_extend': 'public class Existing { public init() {} }\n@DerivePython extend Existing { public func value(): Int64 { 1 } }',
    'bound_extend': '@DerivePython public class Existing { public init() {} }\n@DerivePython extend Existing { public func value(): Int64 { 1 } }',
    'enum_result': '@DerivePython public enum Kind { One | Two }\n@DerivePython public func kind(): Kind { Kind.One }',
    'enum_payload': '@DerivePython public enum Kind { Item(Int64, String) }',
    'private_ctor': '@DerivePython public class Hidden { private init(x: Int64) {} }',
    'mutable_struct': '@DerivePython public struct Mutable { public Mutable(public var n: Int64) {} }',
    'array_pair_out': '@DerivePython public func pairs(): Array<(Int64, String)> { [(1, "one")] }',
    'ignored_field': '@DerivePython public class Selected { public init() {}\n @PyIgnore public let hidden: Int64 = 1 }',
    'inheritance_implicit': '@DerivePython public open class Base { public init() {} }\n@DerivePython public class Derived <: Base { public init() { super() } }\npublic func cls(): PyObj { Derived.pyClass() }',
    'callback_out': '@DerivePython public func callback(): (Int64) -> Int64 { { n => n + 1 } }',
}


def run(command, cwd, env, timeout=20):
    try:
        p = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                           errors='replace', timeout=timeout)
        return {'command': command, 'exit': p.returncode,
                'stdout': p.stdout, 'stderr': re.sub(r'\x1b\[[0-9;]*m', '', p.stderr)}
    except subprocess.TimeoutExpired as e:
        return {'command': command, 'exit': 'timeout', 'stdout': (e.stdout or b'').decode(errors='replace'),
                'stderr': (e.stderr or b'').decode(errors='replace')}


def check(results, expected):
    errors = []
    if results['metadata']['interop_revision'] != expected['interop_revision']:
        errors.append('unexpected interop revision')
    for group in ['compile', 'runtime']:
        if results[group].keys() != expected[group].keys():
            errors.append(f'{group}: case set differs from expectations')
        for name, rule in expected[group].items():
            actual = results[group].get(name, {})
            status = actual.get('exit')
            wanted = rule['exit']
            matches = status == wanted
            if wanted == 'signal':
                matches = isinstance(status, int) and status < 0
            if wanted == 'failure':
                matches = isinstance(status, int) and status != 0
            output = actual.get('stdout', '') + actual.get('stderr', '')
            if not matches or any(part not in output for part in rule.get('contains', [])):
                errors.append(f'{group}/{name}: unexpected observation (exit {status})')
    if results['build']['exit'] != 0:
        errors.append('runtime host did not build')
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interop', type=Path, required=True, help='clean source checkout built with build/build.py')
    p.add_argument('--sdk', type=Path, required=True, help='SDK matching cjc, containing runtime/lib')
    p.add_argument('--libpython', type=Path, required=True)
    p.add_argument('--expected', type=Path, default=Path(__file__).with_name('expected.json'))
    p.add_argument('--record-only', action='store_true', help='collect a new revision without validating the baseline')
    p.add_argument('--out', type=Path, required=True, help='new evidence directory')
    a = p.parse_args()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    source = Path(__file__).resolve().parent
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    interop = a.interop.resolve()
    built = interop / 'target/release/py_interop'
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = ':'.join([str(built), str(a.sdk.resolve() / 'runtime/lib/linux_x86_64_cjnative'), env.get('LD_LIBRARY_PATH', '')])
    metadata = {
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'runtime_source_sha256': hashlib.sha256((source / 'runtime.cj').read_bytes()).hexdigest(),
        'generated_constants': (interop / 'src/py_macro_constants.cj').read_text(),
        'interop_build': 'python build/build.py build (release, -O2; constants generated from matching Python.h)',
        'probe_build': 'cjc default -O0',
        'compiler': subprocess.check_output(['cjc', '--version'], text=True).strip(),
        'python_driver': sys.version, 'platform': platform.platform(),
        'libpython': str(a.libpython.resolve()), 'sdk': str(a.sdk.resolve()),
        'interop_revision': subprocess.check_output(['git', '-C', str(interop), 'rev-parse', 'HEAD'], text=True).strip(),
        'interop_diff': subprocess.check_output(['git', '-C', str(interop), 'diff'], text=True),
        'libpython_sha256': hashlib.sha256(a.libpython.read_bytes()).hexdigest(),
        'python_home': env.get('PYTHONHOME'),
        'python_config': {k: sysconfig.get_config_var(k) for k in ['VERSION', 'Py_DEBUG', 'Py_GIL_DISABLED', 'SOABI']},
    }
    results = {'metadata': metadata, 'compile': {}, 'runtime': {}}
    for name, body in COMPILE.items():
        case = out / name
        case.mkdir()
        src = case / 'probe.cj'
        src.write_text('package probe\nimport py_interop.*\nimport py_interop.internal_macros.*\n' + body + '\n')
        command = ['cjc', str(src), '--import-path', str(built), '--output-type=staticlib',
                   '--debug-macro', '-Woff', 'all', '-o', str(case / 'libprobe.a')]
        results['compile'][name] = run(command, case, env)
    cross = out / 'cross_package'
    cross.mkdir()
    domain = cross / 'domain.cj'
    domain.write_text('package domain\npublic struct Value { public Value(public let n: Int64) {} }\n')
    results['compile']['domain'] = run(['cjc', str(domain), '--output-type=staticlib', '-o', str(cross / 'libdomain.a')], cross, env)
    bindings = {
        'external_interface': 'extend Value <: IntoPy<Value> { public func toPyObj(marker!: PyInteropTypeMarker<Value>): PyObj { toPyObj(n) } }',
        'external_converter': 'public unsafe func toNativePyObj(v: Value): NativePyObj { toNativePyObj(v.n) }\n@DerivePython public func answer(): Value { Value(42) }',
    }
    for name, body in bindings.items():
        src = cross / (name + '.cj')
        src.write_text('package binding\nimport domain.Value\nimport py_interop.*\nimport py_interop.internal_macros.*\n' + body + '\n')
        results['compile'][name] = run(['cjc', str(src), '--import-path', str(built), '--import-path', str(cross), '--output-type=staticlib', '--debug-macro', '-Woff', 'all', '-o', str(cross / (name + '.a'))], cross, env)
    annotated = cross / 'bound.cj'
    annotated.write_text('package bound\nimport py_interop.*\nimport py_interop.internal_macros.*\n@DerivePython public class Bound { public init() {} }\n')
    results['compile']['bound_domain'] = run(['cjc', str(annotated), '--import-path', str(built), '--output-type=staticlib', '--debug-macro', '-Woff', 'all', '-o', str(cross / 'libbound.a')], cross, env)
    extension = cross / 'extension.cj'
    extension.write_text('package binding\nimport bound.Bound\nimport py_interop.*\nimport py_interop.internal_macros.*\n@DerivePython extend Bound { public func value(): Int64 { 1 } }\n')
    results['compile']['bound_cross_extend'] = run(['cjc', str(extension), '--import-path', str(built), '--import-path', str(cross), '--output-type=staticlib', '--debug-macro', '-Woff', 'all', '-o', str(cross / 'libextension.a')], cross, env)
    binary = out / 'runtime'
    shutil.copyfile(source / 'runtime.cj', out / 'runtime.cj')
    command = ['cjc', str(out / 'runtime.cj'), '--import-path', str(built), '-L', str(built),
               '-lpy_interop', '--debug-macro', '-Woff', 'all', '-o', str(binary)]
    results['build'] = run(command, out, env)
    if results['build']['exit'] == 0:
        for name, (mode, code) in RUNTIME.items():
            (out / (name + '.py')).write_text(code + '\n')
            results['runtime'][name] = run([str(binary), str(a.libpython.resolve()), mode, code], out, env)
            print(name, results['runtime'][name]['exit'], flush=True)
    results['validation_errors'] = [] if a.record_only else check(results, json.loads(a.expected.read_text()))
    for error in results['validation_errors']:
        print(error, file=sys.stderr)
    (out / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
    return int(bool(results['validation_errors']) or results['build']['exit'] != 0 or results['compile']['control']['exit'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
