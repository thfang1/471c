from functools import partial

from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate,
                       Let, LetRec, Load, Primitive, Program, Reference,
                       Store, Term)


def reduce_rule(operator: str, left: Term, right: Term) -> Term | None:
    match operator, left, right:
        # (* x 0) -> 0  and  (* 0 x) -> 0
        case "*", _, Immediate(value=0):
            return Immediate(value=0)
        case "*", Immediate(value=0), _:
            return Immediate(value=0)

        # (* x 1) -> x  and  (* 1 x) -> x
        case "*", _, Immediate(value=1):
            return left
        case "*", Immediate(value=1), _:
            return right

        # (* x 2) -> (+ x x)  and  (* 2 x) -> (+ x x)
        case "*", _, Immediate(value=2):
            return Primitive(operator="+", left=left, right=left)
        case "*", Immediate(value=2), _:
            return Primitive(operator="+", left=right, right=right)

        # (+ x 0) -> x  and  (+ 0 x) -> x
        case "+", _, Immediate(value=0):
            return left
        case "+", Immediate(value=0), _:
            return right

        # (- x 0) -> x
        case "-", _, Immediate(value=0):
            return left

        # (- x x) -> 0  when both sides are identical references
        case "-", Reference(name=a), Reference(name=b) if a == b:
            return Immediate(value=0)

        case _:
            return None

def reduce_term(term: Term) -> Term:
    recur = partial(reduce_term)

    match term:
        case Immediate() | Reference() | Allocate():
            return term

        case Primitive(operator=op, left=l, right=r):
            sl, sr = recur(l), recur(r)
            reduced = reduce_rule(op, sl, sr)
            return reduced if reduced is not None else Primitive(operator=op, left=sl, right=sr)

        case Let(bindings=bs, body=b):
            return Let(
                bindings=tuple((n, recur(v)) for n, v in bs),
                body=recur(b),
            )

        case LetRec(bindings=bs, body=b):
            return LetRec(
                bindings=tuple((n, recur(v)) for n, v in bs),
                body=recur(b),
            )

        case Abstract(parameters=ps, body=b):
            return Abstract(parameters=ps, body=recur(b))

        case Apply(target=t, arguments=args):
            return Apply(target=recur(t), arguments=tuple(recur(a) for a in args))

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

        case _:  # pragma: no cover
            raise ValueError(f"Unknown term: {term!r}")


def reduce_program(program: Program) -> Program:
    return Program(parameters=program.parameters, body=reduce_term(program.body))