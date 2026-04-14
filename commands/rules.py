#!/usr/bin/env python3

RULES = [
    (r"^#!.*$", setHashbang),
    (r"^echo\s+(.*)$", transpileEcho),
    (r"^(\w+)=(.+)$", transpileEquals),
    (r"\$(\w+)", transpileVariableOperator),
]

# for each line:
#   for each (regex, function) in RULE:
#       match = regex search
#       if not regex:
#           continue
#
#       return function(match)
#
#
#

#!/usr/bin/env dash
# echo WOW

