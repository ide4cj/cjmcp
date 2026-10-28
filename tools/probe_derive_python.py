#!/usr/bin/env python3
"""Record compile-only DerivePython probes against an already built py_interop.

Failures are evidence, not a failing test suite. This does not execute Python.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

CASES = {
    'primitive_control': 'public func echo(s: String): PyObj { toPyObj(s) }',
    'scalar': '@DerivePython\npublic func echo(s: String): String { s }',
    'record': '@DerivePython\npublic struct Record { public Record(public let value: Int64) {} }',
    'callback': '@DerivePython\npublic func invoke(f: () -> Bool): Bool { f() }',
    'generic': '@DerivePython\npublic class Box<T> { public Box(public let value: T) {} }',
    'external_extend': ('public class Existing { public init() {} }\n'
                        '@DerivePython\nextend Existing { public func value(): Int64 { 1 } }'),
    'enum_result': ('@DerivePython\npublic enum Kind { One | Two }\n'
                    '@DerivePython\npublic func kind(): Kind { Kind.One }'),
    'enum_pair': '@DerivePython\npublic enum Pair { Item(Int64, String) }',
    'default_arg': '@DerivePython\npublic func value(limit!: Int64 = 5): Int64 { limit }',
    'private_ctor': '@DerivePython\npublic class Hidden { private init(x: Int64) {} }',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interop', required=True, type=Path,
                        help='directory containing py_interop.cjo and the macro library')
    parser.add_argument('--out', required=True, type=Path,
                        help='new directory for sources, expansions and compiler logs')
    args = parser.parse_args()
    interop = args.interop.resolve()
    if not (interop / 'py_interop.cjo').is_file():
        parser.error('--interop must contain the built py_interop.cjo')
    out = args.out.resolve()
    # Keep old revisions' evidence separate from each fresh run.
    out.mkdir(parents=True, exist_ok=False)
    version = subprocess.run(['cjc', '--version'], check=True,
                             capture_output=True, text=True).stdout.strip()
    results = {}
    for name, body in CASES.items():
        case = out / name
        case.mkdir()
        source = case / 'probe.cj'
        source.write_text('package probe\nimport py_interop.*\n'
                          'import py_interop.internal_macros.*\n' + body + '\n')
        command = ['cjc', str(source), '--import-path', str(interop),
                   '--output-type=staticlib', '--debug-macro', '-Woff', 'all',
                   '--diagnostic-format', 'noColor', '-o', str(case / 'libprobe.a')]
        result = subprocess.run(command, capture_output=True, text=True, cwd=case)
        log = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout + result.stderr)
        (case / 'compile.log').write_text(log)
        results[name] = {'exit_code': result.returncode,
                         'errors': [line for line in log.splitlines() if 'error:' in line]}
        print(f'{name}: exit {result.returncode}', flush=True)
    (out / 'results.json').write_text(json.dumps(
        {'compiler': version, 'interop': str(interop), 'cases': results}, indent=2) + '\n')
    # Without a passing control, failures cannot substantiate macro limitations.
    return int(results['primitive_control']['exit_code'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
