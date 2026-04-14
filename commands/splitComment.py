#!/usr/bin/env python3

def splitComment(line: str) -> tuple[str, str]:
    splitIndex = _findCommentStartIndex(line)
    if splitIndex == -1:
        return (line, "")
    
    code = line[:splitIndex]
    comment = line[splitIndex:]

    return (code, comment)


# BUG: doesn't account for escaped quotes: 
#   eg. '\"'
def _findCommentStartIndex(line: str) -> int:
    inQuotes = False

    for i, char in enumerate(line):
        if char == '"':
            inQuotes = not inQuotes
        elif char == '#' and not inQuotes:
            return i

    return -1

