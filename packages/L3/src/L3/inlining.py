from collections.abc import Callable, Mapping
from functools import partial

from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                       Immediate, Let, LetRec, Load, Primitive, Program,
                       Reference, Store, Term)
from L3.uniqify import uniqify_term

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

type Env = Mapping[Identifier, Abstract]   # name → known function definition


# ---------------------------------------------------------------------------
# Size measurement
# ---------------------------------------------------------------------------

def size(term: Term) -> int:
    """Count the number of AST nodes in *term*."""
    match term:
        case Immediate() | Reference() | Allocate():
            return 1
        case Primitive(left=l, right=r):
            return 1 + size(l) + size(r)
        case Abstract(body=b):
            return 1 + size(b)
        case Apply(target=t, arguments=args):
            return 1 + size(t) + sum(size(a) for a in args)
        case Let(bindings=bs, body=b):
            return 1 + sum(size(v) for _, v in bs) + size(b)
        case LetRec(bindings=bs, body=b):
            return 1 + sum(size(v) for _, v in bs) + size(b)
        case Branch(left=l, right=r, consequent=c, otherwise=o):
            return 1 + size(l) + size(r) + size(c) + size(o)
        case Load(base=b):
            return 1 + size(b)
        case Store(base=b, value=v):
            return 1 + size(b) + size(v)
        case Begin(effects=es, value=v):  # pragma: no branch
            return 1 + sum(size(e) for e in es) + size(v)


# ---------------------------------------------------------------------------
# Use counting
# ---------------------------------------------------------------------------

def count_uses(name: Identifier, term: Term) -> int:
    """Count how many times *name* appears as a Reference in *term*."""
    match term:
        case Reference(name=n):
            return 1 if n == name else 0
        case Immediate() | Allocate():
            return 0
        case Primitive(left=l, right=r):
            return count_uses(name, l) + count_uses(name, r)
        case Abstract(body=b):
            return count_uses(name, b)
        case Apply(target=t, arguments=args):
            return count_uses(name, t) + sum(count_uses(name, a) for a in args)
        case Let(bindings=bs, body=b):
            return sum(count_uses(name, v) for _, v in bs) + count_uses(name, b)
        case LetRec(bindings=bs, body=b):
            return sum(count_uses(name, v) for _, v in bs) + count_uses(name, b)
        case Branch(left=l, right=r, consequent=c, otherwise=o):
            return (count_uses(name, l) + count_uses(name, r)
                    + count_uses(name, c) + count_uses(name, o))
        case Load(base=b):
            return count_uses(name, b)
        case Store(base=b, value=v):
            return count_uses(name, b) + count_uses(name, v)
        case Begin(effects=es, value=v):  # pragma: no branch
            return sum(count_uses(name, e) for e in es) + count_uses(name, v)


# ---------------------------------------------------------------------------
# Inlining eligibility
# ---------------------------------------------------------------------------

def is_eligible(
    name: Identifier,
    func: Abstract,
    body: Term,
    threshold: int,
) -> bool:
    """
    A binding (name = func) is eligible for inlining if:
      - the function body is below *threshold* nodes (small-function heuristic), or
      - *name* is used exactly once in *body* (single-use heuristic).
    """
    return size(func.body) <= threshold or count_uses(name, body) == 1


# ---------------------------------------------------------------------------
# Substitution  (beta reduction)
# ---------------------------------------------------------------------------

def substitute(
    params: tuple[Identifier, ...],
    args: tuple[Term, ...],
    body: Term,
    fresh: Callable[[str], str],
) -> Term:
    """
    Inline a call by wrapping the function body in let-bindings that bind
    each parameter to the corresponding argument, then uniqifying to avoid
    variable capture.

      (lambda (p0 p1 ...) body) applied to (a0 a1 ...)
      =>  (let ([p0 a0] [p1 a1] ...) body)

    Uniqification runs immediately after to freshen all bound names.
    """
    let: Term = Let(
        bindings=tuple(zip(params, args)),
        body=body,
    )
    return uniqify_term(let, {}, fresh)


# ---------------------------------------------------------------------------
# Inlining pass
# ---------------------------------------------------------------------------

def inline_term(
    term: Term,
    env: Env,
    fresh: Callable[[str], str],
    threshold: int,
) -> Term:
    """
    Traverse *term* substituting eligible call sites with the function body.

    *env*       : currently in-scope let-bound functions
    *fresh*     : name generator for uniqification after substitution
    *threshold* : size limit for small-function inlining (inclusive)
    """
    recur = partial(inline_term, env=env, fresh=fresh, threshold=threshold)

    match term:
        case Immediate() | Reference() | Allocate():
            return term

        case Let(bindings=bs, body=body):
            new_env   = dict(env)
            new_bindings: list[tuple[Identifier, Term]] = []

            for name, val in bs:
                inlined_val = recur(val)
                # register as a known function if eligible for future call sites
                if isinstance(inlined_val, Abstract):
                    new_env[name] = inlined_val
                new_bindings.append((name, inlined_val))

            new_body = inline_term(body, new_env, fresh, threshold)

            # drop bindings whose name was a function eligible for inlining
            # and is no longer referenced (all call sites replaced)
            kept: list[tuple[Identifier, Term]] = []
            for name, val in new_bindings:
                if (isinstance(val, Abstract)
                        and name in new_env
                        and is_eligible(name, val, new_body, threshold)
                        and count_uses(name, new_body) == 0):
                    pass   # fully inlined — drop the binding
                else:
                    kept.append((name, val))

            if not kept:
                return new_body
            return Let(bindings=tuple(kept), body=new_body)

        case LetRec(bindings=bs, body=body):
            # do not inline across letrec — recursive functions need care
            new_bindings = [(n, recur(v)) for n, v in bs]
            return LetRec(
                bindings=tuple(new_bindings),
                body=recur(body),
            )

        case Apply(target=Reference(name=name), arguments=args):
            inlined_args = tuple(recur(a) for a in args)
            if name in env:
                func = env[name]
                if (len(func.parameters) == len(inlined_args)
                        and is_eligible(name, func, term, threshold)):
                    return substitute(
                        tuple(func.parameters),
                        inlined_args,
                        func.body,
                        fresh,
                    )
            return Apply(
                target=Reference(name=name),
                arguments=inlined_args,
            )

        case Apply(target=t, arguments=args):
            return Apply(
                target=recur(t),
                arguments=tuple(recur(a) for a in args),
            )

        case Abstract(parameters=ps, body=b):
            # functions defined inside lambdas are not visible outside —
            # give each lambda a fresh env scope
            return Abstract(parameters=ps, body=inline_term(b, {}, fresh, threshold))

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

        case Load(base=b, index=i):
            return Load(base=recur(b), index=i)

        case Store(base=b, index=i, value=v):
            return Store(base=recur(b), index=i, value=recur(v))

        case Begin(effects=es, value=v):  # pragma: no branch
            return Begin(
                effects=tuple(recur(e) for e in es),
                value=recur(v),
            )


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def inline_program(
    program: Program,
    fresh: Callable[[str], str],
    threshold: int = 5,
) -> Program:
    """
    Run one pass of function inlining over *program*.

    *threshold* controls the small-function heuristic: any function whose
    body has at most *threshold* AST nodes is inlined at every call site.
    Set threshold=0 to disable small-function inlining (only single-use
    functions are inlined).  Set threshold to a large value to inline
    everything.
    """
    new_body = inline_term(program.body, {}, fresh, threshold)
    return Program(parameters=program.parameters, body=new_body)