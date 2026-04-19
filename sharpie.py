#!/usr/bin/env python3

import sys
import re

DECR_INDENT = -1
NO_INDENT = 0
INCR_INDENT = 1

imports = set()
preamble = []
output = []
indent = 0


def main():
    filepath = sys.argv[1]
    global indent

    with open(filepath) as shellFile:
        lines = shellFile.readlines()
    
    for line in lines:
        code, comment = splitComment(line)

        for pattern, func in SUBSTITUTIONS:
            code = _subOutsideQuotes(pattern, func, code)

        code = _expandCommandSubs(code)

        code = code.lstrip()
        if not code.strip():
            continue

        for pattern, func in RULES:
            match = re.search(pattern, code)
            if not match:
                continue

            result, delta, *pre = func(match.groups())
            indent += pre[0] if pre else 0
            if result is not None:
                output.append(("    " * indent) + result + comment)
            
            indent += delta
            break

    
    printOutput()



# ========== PRE-PROCESSING STEPS ==========
def splitComment(line: str) -> tuple[str, str]:
    splitIndex = _findCommentStartIndex(line)
    if splitIndex == -1:
        return (line.rstrip(), "")
    
    code = line[:splitIndex].rstrip()
    comment = line[splitIndex:]

    return (code, comment)

def transpileVariableOperator(match) -> str:
    return (f"{{{match.group(1)}}}")

def transpileArgs(match) -> str:
    _addMissingImport("sys")
    return f"{{sys.argv[{match.group(1)}]}}"

def transpileVariableValue(match) -> str:
    return f"{match.group(1)}"

def transpileBacktick(match) -> str:
    _addMissingImport("subprocess")

    args = [_shellArg(a) for a in _shellSplit(match.group(1))]
    joined = ', '.join(args)
    return f'{{subprocess.check_output([{joined}]).decode().strip()}}'

def transpileNumArgs(_) -> str:
    _addMissingImport("sys")
    return f"{{len(sys.argv) - 1}}"

def transpileAllArgs(_) -> str:
    _addMissingImport("sys")
    _addHelperClass("ArgList")

    return "{_args}"

def transpileArithmatic(match) -> str:
    expression = match.group(1).strip()
    expression = re.sub(r'\{(\w+)\}', r'int(\1)', expression)
    expression = re.sub(r'\b([a-zA-Z_]\w*)\b', r'int(\1)', expression)
    return f'{{{expression}}}'


# ========== RULE FUNCTIONS ==========
def transpileEcho(expression: tuple[str, ...], end: str = "") -> tuple[str, int]:
    line, redirects = _parseRedirects(expression[0])
    quoteType = _isQuoted(line)
    end_arg = f', end={end}' if end else ""

    if quoteType == "single":
        transpiled = f'print({line}{end_arg}{redirects})'
    elif quoteType == "double":
        transpiled = f'print(f{line}{end_arg}{redirects})'
    else:
        normalised = ' '.join(line.split())
        globbed = _globify(normalised)
        if globbed != normalised:
            transpiled = f'print(" ".join({globbed}){end_arg}{redirects})'
        else:
            transpiled = f'print(f"{normalised}"{end_arg}{redirects})'

    return (transpiled, NO_INDENT)

def transpileEchoN(expression: tuple[str, ...]) -> tuple[str, int]:
    return transpileEcho(expression, end='""')

def transpileEquals(expression: tuple[str, ...]) -> tuple[str, int]:
    return (f"{expression[0]} = {_shellArg(expression[1])}", NO_INDENT)

def transpileFor(expression: tuple[str, ...]) -> tuple[str, int]:
    iteration = expression[0]
    iterable = expression[1]

    globbed = _globify(iterable)
    result = ""

    # Case 1: target has globbing in it
    if globbed != iterable:
        result = f"for {iteration} in {globbed}:"
    # Case 2: target is one variable
    elif _isVariable(iterable):
        result = f"for {iteration} in {iterable[1:-1]}:"
    # Case 3: target is a list of strings
    else:
        stringList = ', '.join(f'"{g}"' for g in iterable.split())
        result = f"for {iteration} in [{stringList}]:"

    return (result, NO_INDENT)

def transpileExit(expression: tuple[str, ...]) -> tuple[str, int]:
    _addMissingImport("sys")

    return (f"sys.exit({expression[0]})", NO_INDENT)

def transpileCD(expression: tuple[str, ...]) -> tuple[str, int]:
    _addMissingImport("os")

    return (f"os.chdir({_shellArg(expression[0])})", NO_INDENT)

def transpileRead(expression: tuple[str, ...]) -> tuple[str, int]:
    return (f"{expression[0]} = input()", NO_INDENT)

def transpileExternal(expression: tuple[str, ...]) -> tuple[str, int]:
    _addMissingImport("subprocess")
    line, redirects = _parseRedirects(expression[0])
    
    # replace ", file=" with ", stdout=" for subprocess
    redirects = redirects.replace(", file=", ", stdout=")
    args = [_shellArg(a) for a in _shellSplit(line)]
    return (f"subprocess.run([{', '.join(args)}]{redirects})", NO_INDENT)

def transpileTest(expression: tuple[str, ...]) -> tuple[str, int]:
    parts = _shellSplit(expression[0])
    result = None
    imps = None

    if parts[0] in UNARY_TEST_OPS:
        template, imps = UNARY_TEST_OPS[parts[0]]
        result = template.format(_shellArg(parts[1]))
    elif len(parts) == 3 and parts[1] in BINARY_TEST_OPS:
        template, imps = BINARY_TEST_OPS[parts[1]]
        result = template.format(_shellArg(parts[0]), _shellArg(parts[2]))
    else:
        result = expression[0]   # pass through unknown expressions unchanged
    
    if imps:
        for imp in imps:
            _addMissingImport(imp)
    
    return (result, NO_INDENT)

def transpileIf(expression: tuple[str, ...]) -> tuple[str, int]:
    return (f"if {_transpileCondition(expression[0])}:", NO_INDENT)

def transpileStartConditional(_) -> tuple[str, int]:
    return (None, INCR_INDENT)

def transpileElif(expression: tuple[str, ...]) -> tuple[str, int]:
    return (f"elif {_transpileCondition(expression[0])}:", NO_INDENT, DECR_INDENT)

def transpileElse(_) -> tuple[str, int]:
    return ("else:", INCR_INDENT, DECR_INDENT)

def transpileEndConditional(_) -> tuple[str, int]:
    return (None, DECR_INDENT)

def transpileWhile(expression: tuple[str, ...]) -> tuple[str, int]:
    return (f"while {_transpileCondition(expression[0])}:", NO_INDENT)
    
def transpileCase(expression: tuple[str, ...]) -> tuple[str, int]:
    return (f"match {_shellArg(expression[0])}:", INCR_INDENT)

def transpileCaseTest(expression: tuple[str, ...]) -> tuple[str, int]:
    pattern = expression[0].strip()
    if pattern == "*":
        return ("case _:", INCR_INDENT)
    
    parts = [p.strip().strip('"\'') for p in pattern.split("|")]
    py_pattern = " | ".join(f'"{p}"' for p in parts)
    
    return (f"case {py_pattern}:", INCR_INDENT)

def transpileAnd(expression: tuple[str, ...]) -> tuple[str, int]:
    lhs = _transpileToExpr(expression[0].strip())
    rhs = _transpileToExpr(expression[1].strip())
    cond = f"{lhs}.returncode == 0" if lhs.startswith("subprocess.run(") else lhs
    return (f"{rhs} if {cond} else None", NO_INDENT)

def transpileOr(expression: tuple[str, ...]) -> tuple[str, int]:
    lhs = _transpileToExpr(expression[0].strip())
    rhs = _transpileToExpr(expression[1].strip())
    cond = f"{lhs}.returncode != 0" if lhs.startswith("subprocess.run(") else lhs

    return (f"{rhs} if {cond} else None", NO_INDENT)

# ========== REGEX STEPS ==========
SUBSTITUTIONS = [
    (r"\$([0-9])",                  transpileArgs),
    (r"\$#",                        transpileNumArgs),
    (r"\$@",                        transpileAllArgs),
    (r"\$(\{[^}]*\})",              transpileVariableValue),
    (r"\$(\w+)",                    transpileVariableOperator),
    (r"`(.*?)`",                    transpileBacktick),
    (r"\$\(\(\s*(.*?)\s*\)\)",      transpileArithmatic)
]

RULES = [
    (r"^echo -n\s+(.*)$",       transpileEchoN),
    (r"^echo\s+(.*)$",          transpileEcho),
    (r"^(\w+)=(.+)$",           transpileEquals),
    (r"^for (\w+) in (.+)$",    transpileFor),
    (r"^do$",                   transpileStartConditional),
    (r"^done$",                 transpileEndConditional),
    (r"^exit (.*)$",            transpileExit),
    (r"^cd (.*)$",              transpileCD),
    (r"^read (\w+)$",           transpileRead),
    (r"^if (.*)$",              transpileIf),
    (r"^then$",                 transpileStartConditional),
    (r"^elif (.*)$",            transpileElif),
    (r"^else$",                 transpileElse),
    (r"^fi$",                   transpileEndConditional),
    (r"^while (.*)$",           transpileWhile),
    (r"^case (.*) in$",         transpileCase),
    (r"^(.*)\)$",               transpileCaseTest),
    (r"^;;$",                   transpileEndConditional),
    (r"^esac$",                 transpileEndConditional),
    (r"^\[ (.*) \]$",           transpileTest),
    (r"^test (.*)$",            transpileTest),
    (r"^(.*)\s+&&\s+(.*)$",     transpileAnd),
    (r"^(.*)\s+\|\|\s+(.*)$",   transpileOr),
    (r"(.*)",                   transpileExternal)
]

UNARY_TEST_OPS = {
    # string operators
    "-z": ("len({0}) == 0",     None),
    "-n": ("len({0}) != 0",     None),
    # file operators
    "-e": ('os.path.exists({0})',                                                     ("os",)),
    "-f": ('os.path.isfile({0})',                                                     ("os",)),
    "-d": ('os.path.isdir({0})',                                                      ("os",)),
    "-L": ('os.path.islink({0})',                                                     ("os",)),
    "-s": ('os.path.exists({0}) and os.path.getsize({0}) > 0',                        ("os",)),
    
    "-r": ('os.access({0}, os.R_OK)',                                                 ("os",)),
    "-w": ('os.access({0}, os.W_OK)',                                                 ("os",)),
    "-x": ('os.access({0}, os.X_OK)',                                                 ("os",)),

    "-b": ('os.path.exists({0}) and stat.S_ISBLK(os.stat({0}).st_mode)',            ("os", "stat")),
    "-c": ('os.path.exists({0}) and stat.S_ISCHR(os.stat({0}).st_mode)',            ("os", "stat")),
    "-p": ('os.path.exists({0}) and stat.S_ISFIFO(os.stat({0}).st_mode)',           ("os", "stat")),
    "-g": ('os.path.exists({0}) and bool(os.stat({0}).st_mode & stat.S_ISGID)',     ("os", "stat")),
    "-u": ('os.path.exists({0}) and bool(os.stat({0}).st_mode & stat.S_ISUID)',     ("os", "stat")),
}

BINARY_TEST_OPS = {
    # string operators
    "=":   ("{0} == {1}",   None),
    "!=":  ("{0} != {1}",   None),

    # int comparisons
    "-eq": ("int({0}) == int({1})",   None),
    "-ne": ("int({0}) != int({1})",   None),
    "-lt": ("int({0}) < int({1})",    None),
    "-le": ("int({0}) <= int({1})",   None),
    "-gt": ("int({0}) > int({1})",    None),
    "-ge": ("int({0}) >= int({1})",   None),
}



# ========== PRINTING ==========
def printOutput():
    print("#!/usr/bin/env python3")

    for imp in imports:
        print(f"import {imp}")

    for block in preamble:
        print(block)
    
    for line in output:
        print(line)


# ========== HELPER FUNCTIONS ===========
# BUG: doesn't account for escaped quotes: 
#   eg. '\"'
def _findCommentStartIndex(line: str) -> int:
    inQuotes = False

    for i, char in enumerate(line):
        if char == '"' or char == "'":
            inQuotes = not inQuotes
        elif char == '#' and not inQuotes:
            return i

    return -1

def _globify(arg: str) -> str:
    stripped = re.sub(r'\{[^}]*\}', '', arg)
    globChars = re.compile(r'[*?\[]')

    if not globChars.search(stripped):
        return arg

    _addMissingImport("glob")

    return f'sorted(glob.glob(f"{arg}"))'

def _isVariable(s: str) -> bool:
    return bool(re.match(r'^\{\w+\}$', s))

def _addMissingImport(target: str):
    if target not in imports:
        imports.add(target)

def _subOutsideQuotes(pattern: str, func, code: str) -> str:
    segments = re.split(r"('[^']*')", code)

    # odd indexed are quoted; ignore
    result = []
    for i, segment in enumerate(segments):
        if i % 2 == 1:
            result.append(segment)
        else:
            result.append(re.sub(pattern, func, segment))
    return ''.join(result)

def _shellArg(s: str) -> str:
    # bare variable reference
    if re.match(r'^\{[^}]+\}$', s):
        return s[1:-1]
    if _isQuoted(s):
        s = s[1:-1]
    return f'f"{s}"'

def _isQuoted(s: str) -> str:
    if s.startswith('\'') and s.endswith('\'') and len(s) >= 2:
        return "single"

    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        return "double"

    return None

def _shellSplit(s: str) -> list[str]:
    tokens = []
    current = []
    inQuotes = None
    for ch in s:
        if ch in ('"', "'") and inQuotes is None:
            inQuotes = ch
            current.append(ch)
        elif ch == inQuotes:
            inQuotes = None
            current.append(ch)
        elif ch == ' ' and inQuotes is None:
            if current:
                tokens.append(''.join(current))
                current = []
        else:
            current.append(ch)

    if current:
        tokens.append(''.join(current))

    return tokens

def _addHelperClass(name: str):
    if any(name in block for block in preamble):
        return
    if name == "ArgList":
        preamble.append(
            "class _ArgList(list):\n"
            "   def __str__(self):\n"
            "       return ' '.join(self)\n"
            "_args = _ArgList(sys.argv[1:])"
        )

def _expandCommandSubs(code: str) -> str:
    segments = re.split(r"('[^']*')", code)
    result = []
    for i, segment in enumerate(segments):
        if i % 2 == 1:
            result.append(segment)
        else:
            result.append(_expandCommandSubsSegment(segment))
    return ''.join(result)

def _expandCommandSubsSegment(code: str) -> str:
    stash = {}
    count = [0]

    def replace_innermost(m):
        key = f"\x00{count[0]}\x00"
        count[0] += 1
        _addMissingImport("subprocess")
        parts = _shellSplit(m.group(1))
        args = [stash.get(a, _shellArg(a)) for a in parts]
        stash[key] = f'subprocess.check_output([{", ".join(args)}]).decode().strip()'
        return key

    while re.search(r'\$\(([^()]*)\)', code):
        code = re.sub(r'\$\(([^()]*)\)', replace_innermost, code)

    for key, expansion in stash.items():
        code = code.replace(key, '{' + expansion + '}')

    return code

def _parseRedirects(line: str) -> tuple[str, str]:
    stdout = ""
    stdin = ""

    m = re.search(r'\s*>>\s*(\S+)', line)
    if m:
        stdout = f", file=open({_shellArg(m.group(1))}, 'a')"
        line = line[:m.start()] + line[m.end():]

    m = re.search(r'\s*>\s*(\S+)', line)
    if m:
        stdout = f", file=open({_shellArg(m.group(1))}, 'w')"
        line = line[:m.start()] + line[m.end():]

    m = re.search(r'\s*<\s*(\S+)', line)
    if m:
        stdin = f", stdin=open({_shellArg(m.group(1))}, 'r')"
        line = line[:m.start()] + line[m.end():]

    return line.strip(), stdout + stdin

def _transpileToExpr(code: str) -> str:
    for pattern, func in RULES:
        m = re.search(pattern, code)
        if not m:
            continue
        result, *_ = func(m.groups())
        return result
    return code

def _transpileConditionPart(expression: str) -> str:
    py = _transpileToExpr(expression.strip())
    return f"{py}.returncode == 0" if py.startswith("subprocess.run(") else py

def _transpileCondition(expression: str) -> str:
    if ' && ' in expression:
        return ' and '.join(_transpileConditionPart(p) for p in expression.split(' && '))
    if ' || ' in expression:
        return ' or '.join(_transpileConditionPart(p) for p in expression.split(' || '))
    return _transpileConditionPart(expression)

if __name__ == "__main__":
    main()
