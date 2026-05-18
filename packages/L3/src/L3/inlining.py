from collections.abc import Callable, Mapping
from functools import partial

from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                       Immediate, Let, LetRec, Load, Primitive, Program,
                       Reference, Store, Term)
from L3.uniqify import uniqify_term

type Env = Mapping[Identifier, Abstract]   

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


def is_eligible(
    name: Identifier,
    func: Abstract,
    body: Term,
    threshold: int,
) -> bool:
    return size(func.body) <= threshold or count_uses(name, body) == 1


def substitute(
    params: tuple[Identifier, ...],
    args: tuple[Term, ...],
    body: Term,
    fresh: Callable[[str], str],
) -> Term:
    let: Term = Let(
        bindings=tuple(zip(params, args)),
        body=body,
    )
    return uniqify_term(let, {}, fresh)


def inline_term(
    term: Term,
    env: Env,
    fresh: Callable[[str], str],
    threshold: int,
) -> Term:
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


def inline_program(
    program: Program,
    fresh: Callable[[str], str],
    threshold: int = 5,
) -> Program:
    new_body = inline_term(program.body, {}, fresh, threshold)
    return Program(parameters=program.parameters, body=new_body)