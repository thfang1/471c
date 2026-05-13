from collections.abc import Mapping
from functools import partial

from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                       Immediate, Let, Load, Primitive, Program, Reference,
                       Store, Term)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

type Env    = Mapping[Identifier, Term]   # name → Immediate | Reference
type CSEEnv = Mapping[Term, Identifier]   # pure expr → canonical binding name


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def is_pure(term: Term) -> bool:
    """True if term has no side effects and is safe to hoist / deduplicate."""
    match term:
        case Immediate() | Reference():
            return True
        case Primitive(left=l, right=r):
            return is_pure(l) and is_pure(r)
        case _:
            return False


# ---------------------------------------------------------------------------
# Pass 1: constant folding + copy propagation
# ---------------------------------------------------------------------------

def simplify(term: Term, env: Env = {}) -> Term:
    """
    Single-pass constant folding and copy propagation.

    *env* maps variable names to their known values (Immediate or Reference).
    Immediates enable constant folding; References enable copy propagation.
    """
    recur = partial(simplify, env=env)

    match term:
        case Immediate():
            return term

        case Reference(name=name):
            # copy / constant propagation: replace with known value if available
            return env[name] if name in env else term

        case Let(bindings=bindings, body=body):
            new_bindings: list[tuple[Identifier, Term]] = []
            new_env = dict(env)
            for name, val in bindings:
                s_val = simplify(val, new_env)
                if isinstance(s_val, (Immediate, Reference)):
                    # propagate constants and copies downstream
                    new_env[name] = s_val
                else:
                    new_env.pop(name, None)
                new_bindings.append((name, s_val))
            return Let(
                bindings=tuple(new_bindings),
                body=simplify(body, new_env),
            )

        case Primitive(operator=op, left=l, right=r):
            sl, sr = recur(l), recur(r)
            if isinstance(sl, Immediate) and isinstance(sr, Immediate):
                lv, rv = int(sl.value), int(sr.value)
                match op:
                    case "+":
                        return Immediate(value=lv + rv)
                    case "-":
                        return Immediate(value=lv - rv)
                    case "*":  # pragma: no branch
                        return Immediate(value=lv * rv)
            return Primitive(operator=op, left=sl, right=sr)

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            sl, sr = recur(l), recur(r)
            if isinstance(sl, Immediate) and isinstance(sr, Immediate):
                lv, rv = int(sl.value), int(sr.value)
                condition = (lv < rv) if op == "<" else (lv == rv)
                return recur(c) if condition else recur(o)
            return Branch(
                operator=op,
                left=sl,
                right=sr,
                consequent=recur(c),
                otherwise=recur(o),
            )

        case Abstract(parameters=params, body=b):
            # shadow any env entries that the parameters rebind
            inner_env = {k: v for k, v in env.items() if k not in params}
            return Abstract(parameters=params, body=simplify(b, inner_env))

        case Apply(target=t, arguments=args):
            return Apply(
                target=recur(t),
                arguments=tuple(recur(a) for a in args),
            )

        case Begin(effects=effs, value=v):
            return Begin(
                effects=tuple(recur(e) for e in effs),
                value=recur(v),
            )

        case Load(base=b, index=i):
            return Load(base=recur(b), index=i)

        case Store(base=b, index=i, value=v):
            return Store(base=recur(b), index=i, value=recur(v))

        case Allocate():
            return term

        case _:  # pragma: no cover
            raise ValueError(f"Unknown term: {term!r}")


# ---------------------------------------------------------------------------
# Pass 2: common subexpression elimination
# ---------------------------------------------------------------------------

def _cse_term(term: Term, table: dict[Term, Identifier]) -> Term:
    """
    Traverse *term*, replacing duplicate pure subexpressions with a reference
    to the first binding that computed them.

    *table* maps a seen pure expression to the binding name that holds its
    value.  The table is threaded through sequential bindings so that later
    bindings can reuse earlier ones.  Each lambda body gets a *fresh* table
    so we never hoist across a lambda boundary.
    """
    recur = partial(_cse_term, table=table)

    match term:
        case Immediate() | Reference() | Allocate():
            return term

        case Let(bindings=bindings, body=body):
            new_bindings: list[tuple[Identifier, Term]] = []
            for name, val in bindings:
                s_val = _cse_term(val, table)
                if is_pure(s_val) and not isinstance(s_val, (Immediate, Reference)):
                    if s_val in table:
                        # duplicate: replace with a copy of the canonical binding
                        s_val = Reference(name=table[s_val])
                    else:
                        # first occurrence: register as canonical
                        table[s_val] = name
                new_bindings.append((name, s_val))
            return Let(
                bindings=tuple(new_bindings),
                body=_cse_term(body, table),
            )

        case Primitive(operator=op, left=l, right=r):
            return Primitive(operator=op, left=recur(l), right=recur(r))

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            return Branch(
                operator=op,
                left=recur(l),
                right=recur(r),
                consequent=recur(c),
                otherwise=recur(o),
            )

        case Abstract(parameters=params, body=b):
            # fresh table per lambda — never hoist across a lambda boundary
            return Abstract(parameters=params, body=_cse_term(b, {}))

        case Apply(target=t, arguments=args):
            return Apply(
                target=recur(t),
                arguments=tuple(recur(a) for a in args),
            )

        case Begin(effects=effs, value=v):
            return Begin(
                effects=tuple(recur(e) for e in effs),
                value=recur(v),
            )

        case Load(base=b, index=i):
            return Load(base=recur(b), index=i)

        case Store(base=b, index=i, value=v):
            return Store(base=recur(b), index=i, value=recur(v))

        case _:  # pragma: no cover
            raise ValueError(f"Unknown term: {term!r}")


def cse(term: Term) -> Term:
    """Entry point: run CSE on *term* with a fresh expression table."""
    return _cse_term(term, {})


# ---------------------------------------------------------------------------
# Optimization loop
# ---------------------------------------------------------------------------

def optimize_program(program: Program) -> Program:
    """
    Iterate CSE → simplify (constant folding + copy propagation) until the
    term stops changing.

    CSE runs first to surface duplicate computations as copy bindings;
    simplify then eliminates those copies and folds any newly constant
    expressions.  Dead bindings produced by copy propagation are removed
    because simplify propagates references, making the original binding
    unused — the existing DCE pass (or a subsequent simplify iteration)
    will then drop it.
    """
    current = program.body
    while True:
        after_cse      = cse(current)
        after_simplify = simplify(after_cse)
        if after_simplify == current:
            break
        current = after_simplify
    return Program(parameters=program.parameters, body=current)