from typing import Mapping

from .syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                     Immediate, Let, Load, Primitive, Program, Reference,
                     Store, Term)

type Env = Mapping[str, int]

def simplify(term: Term, env: Env = {}) -> Term:

    match term:
        case Immediate(value=v):
            return Immediate(value=v)
        
        case Reference(name=name):

            if name in env:
                return Immediate(value=env[name])
            return term
        
        case Let(bindings=bindings, body=body):

            new_bindings: list[tuple[Identifier, Term]] = []
            new_env = dict(env)
            for name, val in bindings:
                s_val = simplify(val, env)
                if isinstance(s_val, Immediate):

                    new_env[name] = int(s_val.value)
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
                if op == "+": return Immediate(value=lv + rv)
                if op == "-": return Immediate(value=lv - rv)
                if op == "*": return Immediate(value=lv * rv)
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

        case Store(base=b, index=i, value=v):
            return Store(
                base=simplify(b, env), 
                index=i, 
                value=simplify(v, env)
            )

        case Load(base=b, index=i):
            return Load(base=simplify(b, env), index=i)

        case Allocate(count=c):
            return Allocate(count=c)

def optimize_program(program: Program) -> Program:

    current_term = program.body
    while True:
        next_term = simplify(current_term)

        if next_term == current_term:
            break
        current_term = next_term
        
    return Program(parameters=program.parameters, body=current_term)