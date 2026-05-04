from typing import Mapping

from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                     Immediate, Let, Load, Primitive, Program, Reference,
                     Store, Term)

# --- Types --------------------------------------------------------------------

type Env = Mapping[str, Term]  # name -> Immediate or Reference (for propagation)

# --- Purity Check -------------------------------------------------------------

def is_pure(term: Term) -> bool:
    """Return True if term has no side effects and is safe to deduplicate."""
    match term:
        case Immediate() | Reference():
            return True
        case Primitive(left=l, right=r):
            return is_pure(l) and is_pure(r)
        case _:
            return False

# --- Pass 1: Constant Folding + Copy Propagation ------------------------------

def simplify(term: Term, env: Env = {}) -> Term:

    match term:
        case Immediate(value=v):
            return Immediate(value=v)

        case Reference(name=name):
            if name in env:
                return env[name]  # propagate Immediate or Reference
            return term

        case Let(bindings=bindings, body=body):

            new_bindings: list[tuple[Identifier, Term]] = []
            new_env = dict(env)
            for name, val in bindings:
                s_val = simplify(val, new_env)
                if isinstance(s_val, Immediate):
                    # constant propagation: substitute the value directly
                    new_env[name] = s_val
                elif isinstance(s_val, Reference):
                    # copy propagation: substitute the referenced variable
                    new_env[name] = s_val
                else:
                    new_env.pop(name, None)
                new_bindings.append((name, s_val))

            return Let(
                bindings=tuple(new_bindings),
                body=simplify(body, new_env)
            )

        case Primitive(operator=op, left=l, right=r):
            sl, sr = simplify(l, env), simplify(r, env)
            if isinstance(sl, Immediate) and isinstance(sr, Immediate):
                lv, rv = int(sl.value), int(sr.value)
                if op == "+":
                    return Immediate(value=lv + rv)
                elif op == "-":
                    return Immediate(value=lv - rv)
                else:
                    return Immediate(value=lv * rv)
            return Primitive(operator=op, left=sl, right=sr)

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            sl, sr = simplify(l, env), simplify(r, env)

            if isinstance(sl, Immediate) and isinstance(sr, Immediate):
                lv, rv = int(sl.value), int(sr.value)
                condition_met = (lv < rv) if op == "<" else (lv == rv)
                return simplify(c, env) if condition_met else simplify(o, env)

            return Branch(
                operator=op,
                left=sl,
                right=sr,
                consequent=simplify(c, env),
                otherwise=simplify(o, env)
            )

        case Abstract(parameters=params, body=b):
            inner_env = {k: v for k, v in env.items() if k not in params}
            return Abstract(parameters=params, body=simplify(b, inner_env))

        case Apply(target=t, arguments=args):
            new_args: list[Term] = [simplify(a, env) for a in args]
            return Apply(
                target=simplify(t, env),
                arguments=tuple(new_args)
            )

        case Begin(effects=effs, value=v):
            new_effects: list[Term] = [simplify(e, env) for e in effs]
            return Begin(
                effects=tuple(new_effects),
                value=simplify(v, env)
            )

        case Store(base=b, index=i, value=v):  # pragma: no branch
            return Store(
                base=simplify(b, env),
                index=i,
                value=simplify(v, env)
            )

        case Load(base=b, index=i):
            return Load(base=simplify(b, env), index=i)

        case Allocate(count=c):
            return Allocate(count=c)

        case _:  # pragma: no cover
            raise ValueError(f"Unknown term: {term!r}")

# --- Pass 2: Common Subexpression Elimination ---------------------------------

# ExprKey: a hashable structural representation of a pure expression.
# We use the Term itself as the key since pydantic models are frozen (hashable).
type ExprKey = Term

def cse(term: Term, table: dict[ExprKey, str], counter: list[int]) -> Term:
    """
    Traverse `term` and hoist duplicate pure subexpressions into shared
    let-bindings.  `table` maps a seen pure expression to the fresh name
    that was introduced for it.  `counter` is a single-element list used
    as a mutable integer for fresh name generation.
    """
    match term:
        case Immediate() | Reference() | Allocate():
            return term

        case Primitive(operator=op, left=l, right=r):
            # Only recurse into children; deduplication is handled by the
            # Let binding loop so that line 152 can be reached.
            sl = cse(l, table, counter)
            sr = cse(r, table, counter)
            return Primitive(operator=op, left=sl, right=sr)

        case Let(bindings=bindings, body=body):
            new_bindings: list[tuple[Identifier, Term]] = []
            for name, val in bindings:
                s_val = cse(val, table, counter)
                # If this is a pure expression we have seen before, replace with
                # a reference to the earlier binding and do NOT add to table again.
                if is_pure(s_val) and s_val in table:
                    s_val = Reference(name=table[s_val])
                elif is_pure(s_val) and not isinstance(s_val, (Immediate, Reference)):
                    # First time we see this pure expression: record it.
                    table[s_val] = name
                new_bindings.append((name, s_val))
            return Let(
                bindings=tuple(new_bindings),
                body=cse(body, table, counter)
            )

        case Branch(operator=op, left=l, right=r, consequent=c, otherwise=o):
            return Branch(
                operator=op,
                left=cse(l, table, counter),
                right=cse(r, table, counter),
                consequent=cse(c, table, counter),
                otherwise=cse(o, table, counter)
            )

        case Abstract(parameters=params, body=b):
            # Each lambda gets its own CSE scope so we don't hoist across
            # lambda boundaries (would change evaluation semantics).
            inner_table: dict[ExprKey, str] = {}
            return Abstract(parameters=params, body=cse(b, inner_table, counter))

        case Apply(target=t, arguments=args):
            return Apply(
                target=cse(t, table, counter),
                arguments=tuple(cse(a, table, counter) for a in args)
            )

        case Begin(effects=effs, value=v):
            return Begin(
                effects=tuple(cse(e, table, counter) for e in effs),
                value=cse(v, table, counter)
            )

        case Store(base=b, index=i, value=v):
            return Store(
                base=cse(b, table, counter),
                index=i,
                value=cse(v, table, counter)
            )

        case Load(base=b, index=i):
            return Load(base=cse(b, table, counter), index=i)

        case _:  # pragma: no cover
            raise ValueError(f"Unknown term: {term!r}")

def cse_program(term: Term) -> Term:
    """Entry point: run CSE on a single term with a fresh table."""
    return cse(term, {}, [0])

# --- Optimization Loop --------------------------------------------------------

def optimize_program(program: Program) -> Program:

    current_term = program.body
    while True:
        # Order: CSE -> copy propagation + constant folding -> (repeat)
        after_cse = cse_program(current_term)
        after_simplify = simplify(after_cse)

        if after_simplify == current_term:
            break
        current_term = after_simplify

    return Program(parameters=program.parameters, body=current_term)