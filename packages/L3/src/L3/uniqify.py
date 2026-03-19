from collections.abc import Callable, Mapping

from util.sequential_name_generator import SequentialNameGenerator

from .syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate, Let,
                     LetRec, Load, Primitive, Program, Reference, Store, Term)

#from functools import partial



type Context = Mapping[str, str]


def uniqify_term(
    term: Term,
    context: Context,
    fresh: Callable[[str], str],
) -> Term:
    #_term = partial(uniqify_term, context=context, fresh=fresh)
    def recur(t: Term, ctx: Context = context) -> Term:
        return uniqify_term(t, ctx, fresh)

    match term:
        case Let(bindings=bindings, body=body):
            new_context = dict(context)
            new_bindings : list[tuple[str, Term]] = []
            for name, val in bindings:
                new_val = recur(val)
                new_name = fresh(name)
                new_context[name] = new_name
                new_bindings.append((new_name, new_val))
            
            return Let(
                bindings=tuple(new_bindings),
                body=recur(body, new_context) 
            )

        case LetRec(bindings=bindings, body=body):
            new_context = dict(context)
            for name, _ in bindings:
                new_context[name] = fresh(name)
            
            new_bindings = [
                (new_context[name], recur(val, new_context))
                for name, val in bindings
            ]
            return LetRec(
                bindings=tuple(new_bindings),
                body=recur(body, new_context)
            )

        case Reference(name=name):
            return Reference(name=context.get(name, name))

        case Abstract(parameters=parameters, body=body):
            new_context = dict(context)
            new_params : list[str] = []
            for p in parameters:
                new_name = fresh(p)
                new_context[p] = new_name
                new_params.append(new_name)
            
            return Abstract(
                parameters=tuple(new_params),
                body=recur(body, new_context)
            )

        case Apply(target=target, arguments=arguments):
            return Apply(
                target=recur(target),
                arguments=tuple(recur(arg) for arg in arguments)
            )

        case Immediate():
            return term

        case Primitive(operator=operator, left=left, right=right):
            return Primitive(
                operator=operator,
                left=recur(left),
                right=recur(right)
            )

        case Branch(operator=operator, left=left, right=right, consequent=consequent, otherwise=otherwise):
            return Branch(
                operator=operator,
                left=recur(left),
                right=recur(right),
                consequent=recur(consequent),
                otherwise=recur(otherwise)
            )

        case Allocate():
            return term

        case Load(base=base, index=index):
            return Load(base=recur(base), index=index)

        case Store(base=base, index=index, value=value):
            return Store(base=recur(base), index=index, value=recur(value))

        case Begin(effects=effects, value=value):  # pragma: no branch
            return Begin(
                effects=tuple(recur(e) for e in effects),
                value=recur(value)
            )


def uniqify_program(
    program: Program,
) -> tuple[Callable[[str], str], Program]:
    fresh = SequentialNameGenerator()

    #_term = partial(uniqify_term, fresh=fresh)

    match program:
        case Program(parameters=parameters, body=body):  # pragma: no branch
            local = {parameter: fresh(parameter) for parameter in parameters}
            return (
                fresh,
                Program(
                    parameters=[local[parameter] for parameter in parameters],
                    #body=_term(body, local),
                    body=uniqify_term(body, local, fresh),
                ),
            )
