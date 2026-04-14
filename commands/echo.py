#!/usr/bin/env python3

def transpileEcho(groups: tuple[str, ...]) -> str:
    return f"print({repr(groups[0])})"

