from collections.abc import Callable, Mapping
from functools import partial

from util.sequential_name_generator import SequentialNameGenerator

from .syntax import (
    Abstract,
    Allocate,
    Apply,
    Begin,
    Branch,
    Immediate,
    Let,
    LetRec,
    Load,
    Primitive,
    Program,
    Reference,
    Store,
    Term,
)

type Context = Mapping[str, str]


def uniqify_term(
    term: Term,
    context: Context,
    fresh: Callable[[str], str],
) -> Term:
    _term = partial(uniqify_term, context=context, fresh=fresh)

    match term:
        case Let(bindings=bindings, body=body):
            pass

        case LetRec(bindings=bindings, body=body):
            pass

        case Reference(name=name):
            pass

        case Abstract(parameters=parameters, body=body):
            pass

        case Apply(target=target, arguments=arguments):
            pass

        case Immediate():
            pass

        case Primitive(operator=operator, left=left, right=right):
            pass

        case Branch(operator=operator, left=left, right=right, consequent=consequent, otherwise=otherwise):
            pass

        case Allocate():
            pass

        case Load(base=base, index=index):
            pass

        case Store(base=base, index=index, value=value):
            pass

        case Begin(effects=effects, value=value):  # pragma: no branch
            pass


def uniqify_program(
    program: Program,
) -> tuple[Callable[[str], str], Program]:
    fresh = SequentialNameGenerator()

    _term = partial(uniqify_term, fresh=fresh)

    match program:
        case Program(parameters=parameters, body=body):  # pragma: no branch
            local = {parameter: fresh(parameter) for parameter in parameters}
            return (
                fresh,
                Program(
                    parameters=[local[parameter] for parameter in parameters],
                    body=_term(body, local),
                ),
            )
