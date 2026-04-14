#!/usr/bin/env python3

def transpileEquals(groups: tuple[str, ...]) -> str:
    return f"{groups[0]} = {repr(groups[1])}"
