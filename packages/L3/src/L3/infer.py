from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                     Immediate, Let, Load, Primitive, Program, Reference,
                     Store, Term)


class IntType(BaseModel, frozen=True):
    tag: Literal["int"] = "int"
    def __str__(self) -> str:
        return "Int"

class BlockType(BaseModel, frozen=True):
    tag: Literal["block"] = "block"
    def __str__(self) -> str: 
        return "Block"

class FuncType(BaseModel, frozen=True):
    tag: Literal["func"] = "func"
    params: tuple["Type", ...]
    ret: "Type"
    def __str__(self) -> str:
        ps = ", ".join(str(p) for p in self.params)
        return f"({ps}) -> {self.ret}"

class TypeVar(BaseModel, frozen=True):
    tag: Literal["typevar"] = "typevar"
    id: int
    def __str__(self) -> str:
        letters = "αβγδεζηθικλμνξοπρστυφχψω"
        return letters[self.id % len(letters)] if self.id < 100 else f"τ{self.id}"

type Type = Annotated[IntType | BlockType | FuncType | TypeVar, Field(discriminator="tag")]
type Substitution = dict[int, Type]

INT = IntType()
BLOCK = BlockType()

class Scheme(BaseModel, frozen=True):
    quantified: frozenset[int]
    body: Type

type TypeEnv = Mapping[Identifier, Scheme]


def apply_sub(sub: Substitution, t: Type) -> Type:
    match t:
        case TypeVar(id=i): return apply_sub(sub, sub[i]) if i in sub else t
        case FuncType(params=ps, ret=r):
            return FuncType(params=tuple(apply_sub(sub, p) for p in ps), ret=apply_sub(sub, r))
        case _: return t

def unify(t1: Type, t2: Type, sub: Substitution) -> Substitution:
    t1, t2 = apply_sub(sub, t1), apply_sub(sub, t2)
    if t1 == t2: return sub
    
    match t1, t2:
        case TypeVar() as tv1, _:
            var_id = tv1.id
            if occurs(var_id, t2, sub): 
                raise TypeError(f"Infinite type: {t1} ~ {t2}")
            return {**sub, var_id: t2}
            
        case _, TypeVar() as tv2:
            return unify(tv2, t1, sub)
            
        case FuncType() as f1, FuncType() as f2:
            ps1: tuple[Type, ...] = f1.params
            ps2: tuple[Type, ...] = f2.params
            r1: Type = f1.ret
            r2: Type = f2.ret
            
            if len(ps1) != len(ps2): 
                raise TypeError("Arity mismatch")
            
            new_sub = sub
            for a, b in zip(ps1, ps2):
                new_sub = unify(a, b, new_sub)
            return unify(r1, r2, new_sub)
            
        case _: 
            raise TypeError(f"Type mismatch: {t1} vs {t2}")

def occurs(v: int, t: Type, sub: Substitution) -> bool:
    t = apply_sub(sub, t)
    match t:
        case TypeVar(id=i): 
            return i == v
            
        case FuncType() as f:
            ps: tuple[Type, ...] = f.params
            r: Type = f.ret
            return any(occurs(v, p, sub) for p in ps) or occurs(v, r, sub)
            
        case _: 
            return False


class Counter:
    def __init__(self): 
        self.n = 0
    def fresh(self) -> TypeVar:
        self.n += 1
        return TypeVar(id=self.n - 1)

def generalize(env: TypeEnv, t: Type, sub: Substitution) -> Scheme:
    def free_in_type(tp: Type) -> set[int]:
        match tp:
            case TypeVar(id=i): 
                return {i}
            case FuncType() as f:
                ps: tuple[Type, ...] = f.params
                r: Type = f.ret
                res: set[int] = set()
                for p in ps:
                    res |= free_in_type(p)
                return res | free_in_type(r)
            case _: 
                return set()

    t_free = free_in_type(apply_sub(sub, t))
    
    env_free: set[int] = set()
    for s in env.values():
        f_vars = free_in_type(apply_sub(sub, s.body))
        env_free |= (f_vars - s.quantified)
        
    return Scheme(
        quantified=frozenset(t_free - env_free), 
        body=apply_sub(sub, t)
    )

def instantiate(scheme: Scheme, counter: Counter) -> Type:
    mapping: Substitution = {i: counter.fresh() for i in scheme.quantified}
    return apply_sub(mapping, scheme.body)


def infer_term(term: Term, env: TypeEnv, sub: Substitution, counter: Counter) -> tuple[Type, Substitution]:
    match term:
        case Immediate(): 
            return INT, sub
        
        case Reference(name=n):
            if n not in env: raise TypeError(f"Unbound: {n}") # pragma: no branch
            return instantiate(env[n], counter), sub

        case Primitive(left=l, right=r):
            t_l, sub = infer_term(l, env, sub, counter)
            t_r, sub = infer_term(r, env, sub, counter)
            sub = unify(t_l, INT, sub); sub = unify(t_r, INT, sub)
            return INT, sub

        case Abstract(parameters=ps, body=b):
            t_params = [counter.fresh() for _ in ps]
            new_env = {**env, **{n: Scheme(quantified=frozenset(), body=t) for n, t in zip(ps, t_params)}}
            t_body, sub = infer_term(b, new_env, sub, counter)
            return FuncType(params=tuple(apply_sub(sub, t) for t in t_params), ret=t_body), sub

        case Apply(target=tgt, arguments=args):
            t_tgt, sub = infer_term(tgt, env, sub, counter)
            t_args = [infer_term(a, env, sub, counter)[0] for a in args] 
            t_ret = counter.fresh()
            sub = unify(t_tgt, FuncType(params=tuple(t_args), ret=t_ret), sub)
            return apply_sub(sub, t_ret), sub

        case Let(bindings=bs, body=b):
            new_env = dict(env)
            for n, v in bs:
                t_v, sub = infer_term(v, new_env, sub, counter)
                new_env[n] = generalize(env, t_v, sub)
            return infer_term(b, new_env, sub, counter)

        case Branch(left=l, right=r, consequent=c, otherwise=o):
            t_l, sub = infer_term(l, env, sub, counter)
            t_r, sub = infer_term(r, env, sub, counter)
            sub = unify(t_l, INT, sub); sub = unify(t_r, INT, sub)
            t_c, sub = infer_term(c, env, sub, counter)
            t_o, sub = infer_term(o, env, sub, counter)
            sub = unify(t_c, t_o, sub)
            return apply_sub(sub, t_c), sub

        case Allocate(): return BLOCK, sub

        case Load(base=b):
            t_b, sub = infer_term(b, env, sub, counter)
            sub = unify(t_b, BLOCK, sub)
            return INT, sub

        case Store(base=b, value=v):
            t_b, sub = infer_term(b, env, sub, counter)
            t_v, sub = infer_term(v, env, sub, counter)
            sub = unify(t_b, BLOCK, sub); sub = unify(t_v, INT, sub)
            return INT, sub
        
        case Begin(effects=es, value=v):
            for e in es: _, sub = infer_term(e, env, sub, counter)
            return infer_term(v, env, sub, counter)

        case _: raise NotImplementedError(f"Case {type(term)} not handled")

def infer_program(program: Program) -> Type:
    counter = Counter()
    sub: Substitution = {} 
    
    match program: # pragma: no branch
        case Program(parameters=ps, body=b): # pragma: no branch
            env: TypeEnv = {
                n: Scheme(quantified=frozenset(), body=INT) 
                for n in ps
            }
            t_res, sub = infer_term(b, env, sub, counter)
            return apply_sub(sub, t_res)         