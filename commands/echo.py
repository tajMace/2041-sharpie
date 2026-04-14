#!/usr/bin/env python3

# TOFIX: breaks when passed through quote marks inside the string:
# eg. echo ""wow!"
#           ^ this additional quote marks breaks the syntax
def transpileEcho(groups: tuple[str, ...]) -> str:
    return f'print(f"{groups[0]}")'


