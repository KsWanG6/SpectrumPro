"""Spectrum maths: safe equations on X / Y (one object), A / B (two objects) and combining spectra of different ranges.
Equations are parsed with a whitelist (numbers, + - * / ** ^ %, parentheses, a few functions). No eval of arbitrary code."""
from __future__ import annotations
import ast, math, functools
import numpy as np
from .core import Spectrum

FUNCS = {"sqrt": np.sqrt, "log": np.log, "ln": np.log, "log10": np.log10, "log2": np.log2, "exp": np.exp, "sin": np.sin, "cos": np.cos,
         "tan": np.tan, "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan, "abs": np.abs, "sign": np.sign, "floor": np.floor, "ceil": np.ceil,
         "pow": np.power, "min": lambda *a: np.min(a[0]) if len(a) == 1 else functools.reduce(np.minimum, a), "max": lambda *a: np.max(a[0]) if len(a) == 1 else functools.reduce(np.maximum, a), "mean": lambda a: np.mean(a) + 0 * a, "cumsum": np.cumsum}
CONSTS = {"pi": math.pi, "e": math.e}
_OPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power, ast.Mod: np.mod}


def _eval(node, env):
    if isinstance(node, ast.Expression): return _eval(node.body, env)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool): return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in env: return env[node.id]
        if node.id in CONSTS: return CONSTS[node.id]
        raise ValueError(f"未知的變數「{node.id}」（可用：{', '.join(sorted(env))}）")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS: return _OPS[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, env); return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and not node.keywords:
        try: return FUNCS[node.func.id](*[_eval(a, env) for a in node.args])
        except TypeError: raise ValueError(f"函數 {node.func.id}() 的參數數量不正確") from None
    raise ValueError("不支援的運算式（只允許 + - * / ^ %、括號與 sqrt/log/ln/log10/exp/sin/cos/tan/abs/pow/min/max 等函數）")


def evaluate(expr: str, env: dict) -> np.ndarray:
    expr = expr.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace("，", ",")
    if not expr: raise ValueError("請輸入運算式")
    try: tree = ast.parse(expr, mode="eval")
    except SyntaxError: raise ValueError(f"運算式語法錯誤：{expr}") from None
    with np.errstate(all="ignore"):
        return np.asarray(_eval(tree, env), float)


def _check(v, n, what):
    v = np.broadcast_to(v, (n,)).astype(float).copy()
    if not np.isfinite(v).all(): raise ValueError(f"{what} 的結果含 NaN / 無窮大（例如 log 負數、除以 0）")
    return v


def apply_one(s: Spectrum, equation: str) -> Spectrum:
    """One object. `Y/5`, `log10(Y)`, `X*1.001+2`, or assignments `X = X + 3; Y = Y/max(Y)` (a bare expression sets Y)."""
    env = {"X": s.x.copy(), "Y": s.y.copy()}; x, y = s.x, s.y
    parts = [p.strip() for p in equation.replace("；", ";").split(";") if p.strip()]
    if not parts: raise ValueError("請輸入運算式")
    for p in parts:
        lhs, eq, rhs = p.partition("=")
        if eq and lhs.strip().upper() in ("X", "Y") and not rhs.startswith("="):
            tgt, val = lhs.strip().upper(), rhs
        else: tgt, val = "Y", p
        r = _check(evaluate(val, env), len(s.x), tgt + " = " + val.strip())
        env[tgt] = r
    x, y = env["X"], env["Y"]
    if np.any(np.diff(x) <= 0): raise ValueError("新的 X 必須嚴格遞增")
    return Spectrum(x, y, s.name, s.history + [f"math({equation.strip()})"])


def apply_two(a: Spectrum, b: Spectrum, equation: str) -> Spectrum:
    """Two objects. A and B are the Y arrays (B is interpolated onto A's X). X is A's axis."""
    if b.x[0] > a.x[0] + 1e-9 or b.x[-1] < a.x[-1] - 1e-9:
        raise ValueError(f"B 的 X 範圍（{b.x[0]:.1f}–{b.x[-1]:.1f}）沒有涵蓋 A（{a.x[0]:.1f}–{a.x[-1]:.1f}）；請先裁切 A 或換一條 B")
    by = b.y if (len(a.x) == len(b.x) and np.array_equal(a.x, b.x)) else np.interp(a.x, b.x, b.y)
    r = _check(evaluate(equation, {"A": a.y.copy(), "B": by, "X": a.x.copy()}), len(a.x), equation)
    return Spectrum(a.x.copy(), r, a.name, a.history + [f"math({equation.strip()}; B={b.name})"])


def combine(specs, adjust: bool = True, name: str = "Combined") -> Spectrum:
    """Join spectra of different (possibly overlapping) X ranges into one. With `adjust`, each next spectrum is scaled
    (least squares, through the origin of the overlap after removing its mean offset) to match the already merged data in the
    overlap; in the overlap the two are cross-faded linearly."""
    if len(specs) < 2: raise ValueError("合併至少需要 2 條光譜")
    S = sorted(specs, key=lambda s: s.x[0])
    x, y = S[0].x.copy(), S[0].y.copy(); notes = []
    for s in S[1:]:
        lo, hi = max(x[0], s.x[0]), min(x[-1], s.x[-1])
        ys = s.y.copy()
        if hi > lo:
            xo = np.linspace(lo, hi, 200); a = np.interp(xo, x, y); b = np.interp(xo, s.x, s.y)
            if adjust:
                A = a - a.mean(); Bc = b - b.mean(); f = float(A @ Bc / (Bc @ Bc)) if (Bc @ Bc) > 0 else 1.0
                if not np.isfinite(f) or f <= 0: f = float(a.mean() / b.mean()) if b.mean() else 1.0
                off = a.mean() - f * b.mean(); ys = f * s.y + off; notes.append(f"{s.name}: ×{f:.4g} {off:+.4g}")
            xn = s.x[s.x > x[-1]]; ov = (x >= lo) & (x <= hi)     # points outside the overlap keep their own data
            w = np.clip((x[ov] - lo) / (hi - lo), 0, 1)                           # 0 -> keep old, 1 -> new
            y[ov] = (1 - w) * y[ov] + w * np.interp(x[ov], s.x, ys)
            x = np.concatenate([x, xn]); y = np.concatenate([y, np.interp(xn, s.x, ys)])
        else:
            x = np.concatenate([x, s.x]); y = np.concatenate([y, s.y])
            notes.append(f"{s.name}: 與前段無重疊，直接接上")
    return Spectrum(x, y, name, [f"combine({len(specs)} spectra, adjust={adjust}; " + "; ".join(notes) + ")"])
