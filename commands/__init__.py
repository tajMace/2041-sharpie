#!/usr/bin/env python3

from .hashbang import setHashbang
from .echo import transpileEcho
from .equals import transpileEquals

TRANSPILERS = [
    "hashbang": setHashbang,
    "echo": transpileEcho,
    "equals": transpileEquals,
]
