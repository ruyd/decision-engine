"""Rules engine: readable, versioned business rules evaluated against decision facts.

A rule:
  {"id": "dup_claim", "name": "...", "description": "...", "enabled": true,
   "condition": "claim.dup_count > 0 and claim.total_paid > 0",
   "action": {"outcome": "DENY", "queue": "payment_integrity", "reason": "Duplicate of a paid claim"}}

Conditions are a small, safe Python-like expression language: comparisons, and/or/not,
arithmetic, `in`, list literals, dotted fact access (claim.total_paid, member.risk_tier) and
a few whitelisted functions. Anything else (imports, attribute calls, dunder access) is rejected
at validation time, so rules can be edited in the UI without letting anyone run code.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field
from typing import Any

# Outcome precedence per flow: when several rules fire, the most severe wins.
SEVERITY = {
    "claim": {"DENY": 4, "PEND_SIU": 3, "PEND_REVIEW": 2, "APPROVE": 1},
    "prior_auth": {"DENY": 4, "PEND_CLINICAL": 3, "PEND_INFO": 2, "APPROVE": 1},
}

FUNCS = {
    "abs": abs, "min": min, "max": max, "len": len, "round": round,
    "any_prefix": lambda items, *prefixes: any(str(i).startswith(prefixes) for i in (items or []) if i),
    "count_prefix": lambda items, *prefixes: sum(str(i).startswith(prefixes) for i in (items or []) if i),
}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Mod: operator.mod}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge, ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b, ast.Is: operator.is_, ast.IsNot: operator.is_not}
_ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.BinOp,
            ast.Compare, ast.Name, ast.Attribute, ast.Load, ast.Constant, ast.List, ast.Tuple, ast.Call,
            *_BIN, *_CMP)


class RuleError(ValueError):
    pass


def _path(node: ast.AST) -> str | None:
    """'claim.total_paid' for Attribute/Name chains, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


@dataclass
class Compiled:
    source: str
    tree: ast.Expression
    refs: list[str] = field(default_factory=list)   # fact paths referenced, for the trace


def compile_condition(src: str, known_roots: set[str] | None = None) -> Compiled:
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except SyntaxError as e:
        raise RuleError(f"syntax error: {e.msg}") from None
    refs: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise RuleError(f"'{type(node).__name__}' is not allowed in rule conditions")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise RuleError("private attributes are not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS:
                raise RuleError(f"unknown function; allowed: {', '.join(FUNCS)}")
            if node.keywords:
                raise RuleError("keyword arguments are not allowed")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)):
            p = _path(node)
            if p and p not in FUNCS and not any(r.startswith(p + ".") for r in refs) and p not in refs:
                # keep only the longest chains (claim.total_paid, not claim)
                refs = [r for r in refs if not p.startswith(r + ".")] + [p]
    if known_roots is not None:
        for r in refs:
            if r.split(".")[0] not in known_roots:
                raise RuleError(f"unknown fact '{r}'; facts start with: {', '.join(sorted(known_roots))}")
    return Compiled(src, tree, refs)


def _resolve(facts: dict, path: str) -> Any:
    cur: Any = facts
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise RuleError(f"fact '{path}' is not available")
    return cur


def _eval(node: ast.AST, facts: dict) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, facts)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Name, ast.Attribute)):
        p = _path(node)
        if p is None:
            raise RuleError("unsupported attribute access")
        if p in ("true", "True"):
            return True
        if p in ("false", "False"):
            return False
        return _resolve(facts, p)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval(e, facts) for e in node.elts]
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(v, facts) for v in node.values)
        return any(_eval(v, facts) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, facts)
        return (not v) if isinstance(node.op, ast.Not) else -v
    if isinstance(node, ast.BinOp):
        return _BIN[type(node.op)](_eval(node.left, facts), _eval(node.right, facts))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, facts)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, facts)
            if left is None or right is None:
                if not isinstance(op, (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)):
                    return False          # missing value never satisfies an ordering comparison
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        return FUNCS[node.func.id](*[_eval(a, facts) for a in node.args])
    raise RuleError(f"unsupported expression {type(node).__name__}")


def validate_rules(rules: list[dict], flow: str, known_roots: set[str]) -> list[dict]:
    """Return a list of {id, error} problems (empty = valid)."""
    problems, seen = [], set()
    for r in rules:
        rid = r.get("id") or "?"
        if rid in seen:
            problems.append({"id": rid, "error": "duplicate rule id"})
        seen.add(rid)
        if r.get("action", {}).get("outcome") not in SEVERITY[flow]:
            problems.append({"id": rid, "error": f"outcome must be one of {list(SEVERITY[flow])}"})
        try:
            compile_condition(r.get("condition", ""), known_roots)
        except RuleError as e:
            problems.append({"id": rid, "error": str(e)})
    return problems


def evaluate(ruleset: dict, facts: dict, flow: str) -> dict:
    """Evaluate every enabled rule; return decision + full trace."""
    trace, fired = [], []
    for r in ruleset["rules"]:
        entry = {"id": r["id"], "name": r.get("name", r["id"]), "condition": r["condition"],
                 "enabled": r.get("enabled", True), "action": r["action"], "matched": False, "values": {}}
        if entry["enabled"]:
            try:
                c = compile_condition(r["condition"])
                for ref in c.refs:
                    try:
                        entry["values"][ref] = _resolve(facts, ref)
                    except RuleError:
                        entry["values"][ref] = None
                entry["matched"] = bool(_eval(c.tree, facts))
            except (RuleError, TypeError, ZeroDivisionError) as e:
                entry["error"] = str(e)
            if entry["matched"]:
                fired.append(r)
        trace.append(entry)
    sev = SEVERITY[flow]
    if fired:
        top = max(fired, key=lambda r: sev[r["action"]["outcome"]])   # first rule wins ties
        outcome, queue = top["action"]["outcome"], top["action"].get("queue")
    else:
        default = ruleset.get("default", {"outcome": "APPROVE", "queue": "auto", "reason": "No rule fired"})
        outcome, queue = default["outcome"], default.get("queue", "auto")
    reasons = [{"rule": r["id"], "name": r.get("name", r["id"]), "outcome": r["action"]["outcome"],
                "reason": r["action"].get("reason", "")}
               for r in sorted(fired, key=lambda r: -sev[r["action"]["outcome"]])]
    if not reasons:
        reasons = [{"rule": "default", "name": "Default", "outcome": outcome,
                    "reason": ruleset.get("default", {}).get("reason", "No rule fired")}]
    return {"outcome": outcome, "queue": queue or "auto", "reasons": reasons, "trace": trace}
