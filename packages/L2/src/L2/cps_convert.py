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
        case L2.Let(bindings=bindings, body=body):
            pass

        case L2.Reference(name=name):
            pass

        case L2.Abstract(parameters=parameters, body=body):
            pass

        case L2.Apply(target=target, arguments=arguments):
            pass

        case L2.Immediate(value=value):
            pass

        case L2.Primitive(operator=operator, left=left, right=right):
            pass

        case L2.Branch(operator=operator, left=left, right=right, consequent=consequent, otherwise=otherwise):
            pass

        case L2.Allocate(count=count):
            pass

        case L2.Load(base=base, index=index):
            pass

        case L2.Store(base=base, index=index, value=value):
            pass

        case L2.Begin(effects=effects, value=value):  # pragma: no branch
            pass


def cps_convert_terms(
    terms: Sequence[L2.Term],
    k: Callable[[Sequence[L1.Identifier]], L1.Statement],
    fresh: Callable[[str], str],
) -> L1.Statement:
    _term = partial(cps_convert_term, fresh=fresh)
    _terms = partial(cps_convert_terms, fresh=fresh)

    match terms:
        case []:
            return k([])

        case [first, *rest]:
            return _term(first, lambda first: _terms(rest, lambda rest: k([first, *rest])))

        case _:  # pragma: no cover
            raise ValueError(terms)


def cps_convert_program(
    program: L2.Program,
    fresh: Callable[[str], str],
) -> L1.Program:
    _term = partial(cps_convert_term, fresh=fresh)

    match program:
        case L2.Program(parameters=parameters, body=body):  # pragma: no branch
            return L1.Program(
                parameters=parameters,
                body=_term(body, lambda value: L1.Halt(value=value)),
            )
