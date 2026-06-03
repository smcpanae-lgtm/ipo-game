import ast, sys
try:
    src = open("game_tui.py", encoding="utf-8").read()
    ast.parse(src)
    print("OK: game_tui.py syntax valid")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)

# Also check imports are resolvable
try:
    import textual
    print(f"OK: textual {textual.__version__}")
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)

print("All checks passed!")
