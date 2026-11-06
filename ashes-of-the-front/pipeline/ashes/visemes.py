"""Named mouth shapes (visemes) and facial expressions.

These lists are the single source in code. The JSON schemas repeat them, and
the tests fail if the two copies drift apart.
"""

VISEMES = ("REST", "MBP", "FV", "TH", "DNT", "KG", "CHJ", "SZ", "L", "AA", "E", "I", "O", "U")
EXPRESSIONS = ("neutral", "angry", "determined", "surprised", "injured")
