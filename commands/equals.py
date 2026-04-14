#!/usr/bin/env python3

def transpileEquals(match: str) -> str:
    return f'{match.group(1)} = "{match.group(2)}"'
