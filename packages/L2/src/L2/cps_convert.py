from collections.abc import Callable, Sequence
from functools import partial

from L1 import syntax as L1
from L2 import syntax as L2


def cps_convert_term(
    term: L2.Term,
    k: Callable[[L1.Identifier], L1.Statement],
    fresh: Callable[[str], str],
) -> L1.Statement:
    _term = partial(cps_convert_term, fresh=fresh)
    _terms = partial(cps_convert_terms, fresh=fresh)

    match term:
        case L2.Reference(name=name):
            return k(name)

        case L2.Immediate(value=value):
            v = fresh("t")
            return L1.Immediate(destination=v, value=value, then=k(v))

        case L2.Primitive(operator=operator, left=left, right=right):
            def after_left(left_v: str) -> L1.Statement:
                def after_right(r: str) -> L1.Statement:
                    res = fresh("t")
                    return L1.Primitive(
                        destination=res,
                        operator=operator,
                        left=left_v,
                        right=r,
                        then=k(res),
                    )
                return _term(right, after_right)
            return _term(left, after_left)

        case L2.Abstract(parameters=parameters, body=body):
            f = fresh("t")
            k_param = fresh("k")
            f_body = _term(body, lambda res: L1.Apply(target=k_param, arguments=[res]))
            return L1.Abstract(
                destination=f,
                parameters=[*parameters, k_param],  # k is the LAST parameter
                body=f_body,
                then=k(f),
            )

        case L2.Apply(target=target, arguments=arguments):
            def after_target(f: str) -> L1.Statement:
                def after_args(args: Sequence[str]) -> L1.Statement:
                    k_obj = fresh("k")
                    rv = fresh("t")
                    return L1.Abstract(
                        destination=k_obj,
                        parameters=[rv],
                        body=k(rv),
                        then=L1.Apply(target=f, arguments=[*args, k_obj]),  # k is the LAST argument
                    )
                return _terms(arguments, after_args)
            return _term(target, after_target)

        case L2.Let(bindings=bindings, body=body):
            def convert_bindings(bs: list[tuple[L2.Identifier, L2.Term]]) -> L1.Statement:
                if not bs:
                    return _term(body, k)
                (name, val), *rest = bs
                def after_val(v: str) -> L1.Statement:
                    return L1.Copy(
                        destination=name,
                        source=v,
                        then=convert_bindings(rest),
                    )
                return _term(val, after_val)
            return convert_bindings(list(bindings))

        case L2.Branch(operator=operator, left=left, right=right,
                       consequent=consequent, otherwise=otherwise):
            def after_left(left_v: str) -> L1.Statement:
                def after_right(r: str) -> L1.Statement:
                    j_obj = fresh("j")
                    rv = fresh("t")
                    return L1.Abstract(
                        destination=j_obj,
                        parameters=[rv],
                        body=k(rv),
                        then=L1.Branch(
                            operator=operator,
                            left=left_v,
                            right=r,
                            then=_term(consequent, lambda v: L1.Apply(target=j_obj, arguments=[v])),
                            otherwise=_term(otherwise, lambda v: L1.Apply(target=j_obj, arguments=[v])),
                        ),
                    )
                return _term(right, after_right)
            return _term(left, after_left)

        case L2.Allocate(count=count):
            v = fresh("t")
            return L1.Allocate(destination=v, count=count, then=k(v))

        case L2.Load(base=base, index=index):
            def after_base(b: str) -> L1.Statement:
                v = fresh("t")
                return L1.Load(destination=v, base=b, index=index, then=k(v))
            return _term(base, after_base)

        case L2.Store(base=base, index=index, value=value):
            def after_base(b: str) -> L1.Statement:
                def after_value(v: str) -> L1.Statement:
                    dummy = fresh("t")
                    return L1.Store(
                        base=b,
                        index=index,
                        value=v,
                        then=L1.Immediate(destination=dummy, value=0, then=k(dummy)),
                    )
                return _term(value, after_value)
            return _term(base, after_base)

        case L2.Begin(effects=effects, value=value):
            def convert_effects(es: list[L2.Term]) -> L1.Statement:
                if not es:
                    return _term(value, k)
                head, *tail = es
                return _term(head, lambda _: convert_effects(tail))
            return convert_effects(list(effects))

        case _:  # pragma: no cover
            raise ValueError(f"Unknown L2 term: {term!r}")


def cps_convert_terms(
    terms: Sequence[L2.Term],
    k: Callable[[Sequence[L1.Identifier]], L1.Statement],
    fresh: Callable[[str], str],
) -> L1.Statement:
    _term = partial(cps_convert_term, fresh=fresh)
    _terms = partial(cps_convert_terms, fresh=fresh)
    match list(terms):
        case []:
            return k([])
        case [first, *rest]:
            return _term(first, lambda f: _terms(rest, lambda r: k([f, *r])))
        case _:  # pragma: no cover
            raise ValueError(terms)


def cps_convert_program(
    program: L2.Program,
    fresh: Callable[[str], str],
) -> L1.Program:
    _term = partial(cps_convert_term, fresh=fresh)
    match program:
        case L2.Program(parameters=parameters, body=body):
            return L1.Program(
                parameters=list(parameters),
                body=_term(body, lambda res: L1.Halt(value=res)),
            )
        case _:
            raise ValueError(f"Unknown L2 program: {program!r}")