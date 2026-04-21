from collections.abc import Callable
from functools import partial

from L0 import syntax as L0
from L1 import syntax as L1

FreshFunc = Callable[[str], str]

def free_vars(stmt: L1.Statement) -> set[L1.Identifier]:
    match stmt:
        case L1.Copy(destination=d, source=s, then=t):
            return ({s} | free_vars(t)) - {d}
        case L1.Abstract(destination=d, parameters=p, body=b, then=t):
            return (free_vars(b) - set(p) | free_vars(t)) - {d}
        case L1.Apply(target=t, arguments=args):
            return {t} | set(args)
        case L1.Immediate(destination=d, then=t):
            return free_vars(t) - {d}
        case L1.Primitive(destination=d, left=l, right=r, then=t):
            return ({l, r} | free_vars(t)) - {d}
        case L1.Branch(left=l, right=r, then=th, otherwise=ot):
            return {l, r} | free_vars(th) | free_vars(ot)
        case L1.Allocate(destination=d, then=t):
            return free_vars(t) - {d}
        case L1.Load(destination=d, base=b, then=t):
            return {b} | free_vars(t) - {d}
        case L1.Store(base=b, value=v, then=t):
            return {b, v} | free_vars(t)
        case L1.Halt(value=v):
            return {v}
        case _: # pragma: no cover
            return set()
    

def close_statement(
    stmt: L1.Statement,
    procedures: list[L0.Procedure],
    fresh: FreshFunc,
) -> L0.Statement:
    _close = partial(close_statement, procedures=procedures, fresh=fresh)

    match stmt:
        case L1.Abstract(destination=dest, parameters=params, body=body, then=then):
            f_vars = sorted(list(free_vars(body) - set(params)))
            proc_name = fresh("proc")
            closure_ptr = fresh("closure")
            code_ptr = fresh("code")

            new_body = _close(body)
            for i, v in enumerate(f_vars):
                new_body = L0.Load(destination=v, base=params[0], index=i + 1, then=new_body)

            procedures.append(L0.Procedure(
                name=proc_name,
                parameters=[closure_ptr, *params],
                body=new_body
            ))

            size = len(f_vars) + 1
            closure_init = _close(then)
            for i, v in enumerate(reversed(f_vars)):
                closure_init = L0.Store(base=dest, index=len(f_vars) - i, value=v, then=closure_init)
            
            return L0.Address(destination=code_ptr, name=proc_name, then=
                L0.Allocate(destination=dest, count=size, then=
                    L0.Store(base=dest, index=0, value=code_ptr, then=closure_init)
                )
            )

        case L1.Apply(target=target, arguments=args):
            code_ptr = fresh("cp")
            return L0.Load(destination=code_ptr, base=target, index=0, then=
                L0.Call(target=code_ptr, arguments=[target, *args])
            )

        case L1.Copy(destination=d, source=s, then=t):
            return L0.Copy(destination=d, source=s, then=_close(t))
        case L1.Immediate(destination=d, value=v, then=t):
            return L0.Immediate(destination=d, value=v, then=_close(t))
        case L1.Primitive(destination=d, operator=o, left=l, right=r, then=t):
            return L0.Primitive(destination=d, operator=o, left=l, right=r, then=_close(t))
        case L1.Branch(operator=o, left=l, right=r, then=th, otherwise=ot):
            return L0.Branch(operator=o, left=l, right=r, then=_close(th), otherwise=_close(ot))
        case L1.Allocate(destination=d, count=c, then=t):
            return L0.Allocate(destination=d, count=c, then=_close(t))
        case L1.Load(destination=d, base=b, index=i, then=t):
            return L0.Load(destination=d, base=b, index=i, then=_close(t))
        case L1.Store(base=b, index=i, value=v, then=t):
            return L0.Store(base=b, index=i, value=v, then=_close(t))
        case L1.Halt(value=v):
            return L0.Halt(value=v)
        case _: # pragma: no cover
            raise ValueError(f"Unknown statement type: {type(stmt)}")

def close_program(program: L1.Program, fresh: FreshFunc) -> L0.Program:
    procedures: list[L0.Procedure] = []
    main_body = close_statement(program.body, procedures, fresh)

    procedures.append(L0.Procedure(
        name="main",
        parameters=program.parameters,
        body=main_body
    ))
    
    return L0.Program(procedures=procedures)    