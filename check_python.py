import sys
v = sys.version_info
print(f"Python {v.major}.{v.minor}.{v.micro}")
ok = v.major == 3 and 10 <= v.minor <= 12
sys.exit(0 if ok else 1)
