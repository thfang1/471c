from collections.abc import Callable, Mapping
from functools import partial
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from .syntax import (Abstract, Allocate, Apply, Begin, Branch, Identifier,
                     Immediate, Let, LetRec, Load, Primitive, Program,
                     Reference, Store, Term)


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


type Type         = Annotated[IntType | BlockType | FuncType | TypeVar, Field(discriminator="tag")]
type Substitution = Mapping[int, Type]
type TypeEnv      = Mapping[Identifier, Scheme]

INT   = IntType()
BLOCK = BlockType()


class Scheme(BaseModel, frozen=True):
    quantified: frozenset[int]
    body: Type


def apply_sub(sub: Substitution, t: Type) -> Type:
    match t:
        case TypeVar(id=i):
            return apply_sub(sub, sub[i]) if i in sub else t
        case FuncType(params=ps, ret=r):
            return FuncType(
                params=tuple(apply_sub(sub, p) for p in ps),
                ret=apply_sub(sub, r),
            )
        case _:  # pragma: no branch
            return t


def occurs(v: int, t: Type, sub: Substitution) -> bool:
    t = apply_sub(sub, t)
    match t:
        case TypeVar(id=i):
            return i == v
        case FuncType(params=ps, ret=r):
            return any(occurs(v, p, sub) for p in ps) or occurs(v, r, sub)
        case _:  # pragma: no branch
            return False


def unify(t1: Type, t2: Type, sub: Substitution) -> dict[int, Type]:
    t1, t2 = apply_sub(sub, t1), apply_sub(sub, t2)
    if t1 == t2:
        return dict(sub)

    match t1, t2:
        case TypeVar(id=i), _:
            if occurs(i, t2, sub):
                raise TypeError(f"Infinite type: {t1} ~ {t2}")
            return {**sub, i: t2}

        case _, TypeVar():
            return unify(t2, t1, sub)

        case FuncType(params=ps1, ret=r1), FuncType(params=ps2, ret=r2):
            if len(ps1) != len(ps2):
                raise TypeError("Arity mismatch")
            new_sub: dict[int, Type] = dict(sub)
            for a, b in zip(ps1, ps2):
                new_sub = unify(a, b, new_sub)
            return unify(r1, r2, new_sub)

        case _:  # pragma: no branch
            raise TypeError(f"Type mismatch: {t1} vs {t2}")


def make_type_var_fresh() -> Callable[[], TypeVar]:
    n = [0]

    def fresh() -> TypeVar:
        tv = TypeVar(id=n[0])
        n[0] += 1
        return tv

    return fresh


def free_vars(t: Type) -> frozenset[int]:
    match t:
        case TypeVar(id=i):
            return frozenset({i})
        case FuncType(params=ps, ret=r):
            result: frozenset[int] = frozenset()
            for p in ps:
                result |= free_vars(p)
            return result | free_vars(r)
        case _:  # pragma: no branch
            return frozenset()


def generalize(env: TypeEnv, t: Type, sub: Substitution) -> Scheme:
    t_free = free_vars(apply_sub(sub, t))

    env_free: frozenset[int] = frozenset()
    for scheme in env.values():
        env_free |= free_vars(apply_sub(sub, scheme.body)) - scheme.quantified

    return Scheme(
        quantified=t_free - env_free,
        body=apply_sub(sub, t),
    )


def instantiate(scheme: Scheme, fresh: Callable[[], TypeVar]) -> Type:
    mapping: dict[int, Type] = {i: fresh() for i in scheme.quantified}
    return apply_sub(mapping, scheme.body)


def infer_term(
    term: Term,
    env: TypeEnv,
    sub: dict[int, Type],
    fresh: Callable[[], TypeVar],
) -> tuple[Type, dict[int, Type]]:
    recur = partial(infer_term, env=env, sub=sub, fresh=fresh)

    match term:
        case Immediate():
            return INT, sub

        case Reference(name=n):
            if n not in env:
                raise TypeError(f"Unbound variable: {n}")
            return instantiate(env[n], fresh), sub

        case Primitive(left=l, right=r):
            t_l, sub = recur(l)
            t_r, sub = recur(r, sub=sub)
            sub = unify(t_l, INT, sub)
            sub = unify(t_r, INT, sub)
            return INT, sub

        case Abstract(parameters=ps, body=b):
            t_params = [fresh() for _ in ps]
            new_env: TypeEnv = {
                **env,
                **{n: Scheme(quantified=frozenset(), body=t)
                   for n, t in zip(ps, t_params)},
            }
            t_body, sub = infer_term(b, new_env, sub, fresh)
            return FuncType(
                params=tuple(apply_sub(sub, t) for t in t_params),
                ret=t_body,
            ), sub

        case Apply(target=tgt, arguments=args):
            t_tgt, sub = recur(tgt)
            t_args: list[Type] = []
            for a in args:
                t_a, sub = infer_term(a, env, sub, fresh)
                t_args.append(t_a)
            t_ret = fresh()
            sub = unify(t_tgt, FuncType(params=tuple(t_args), ret=t_ret), sub)
            return apply_sub(sub, t_ret), sub

        case Let(bindings=bs, body=b):
            new_env = dict(env)
            for n, v in bs:
                t_v, sub = infer_term(v, new_env, sub, fresh)
                new_env[n] = generalize(env, t_v, sub)
            return infer_term(b, new_env, sub, fresh)

        case LetRec(bindings=bs, body=b):
            new_env = dict(env)
            placeholders: dict[Identifier, TypeVar] = {}
            for n, _ in bs:
                tv = fresh()
                placeholders[n] = tv
                new_env[n] = Scheme(quantified=frozenset(), body=tv)
            for n, v in bs:
                t_v, sub = infer_term(v, new_env, sub, fresh)
                sub = unify(placeholders[n], t_v, sub)
            for n in placeholders:
                new_env[n] = generalize(new_env, apply_sub(sub, placeholders[n]), sub)
            return infer_term(b, new_env, sub, fresh)

        case Branch(left=l, right=r, consequent=c, otherwise=o):
            t_l, sub = recur(l)
            t_r, sub = recur(r, sub=sub)
            sub = unify(t_l, INT, sub)
            sub = unify(t_r, INT, sub)
            t_c, sub = infer_term(c, env, sub, fresh)
            t_o, sub = infer_term(o, env, sub, fresh)
            sub = unify(t_c, t_o, sub)
            return apply_sub(sub, t_c), sub

        case Allocate():
            return BLOCK, sub

        case Load(base=b):
            t_b, sub = recur(b)
            sub = unify(t_b, BLOCK, sub)
            return INT, sub

        case Store(base=b, value=v):
            t_b, sub = recur(b)
            t_v, sub = infer_term(v, env, sub, fresh)
            sub = unify(t_b, BLOCK, sub)
            sub = unify(t_v, INT, sub)
            return INT, sub

        case Begin(effects=es, value=v):  # pragma: no branch
            for e in es:
                _, sub = infer_term(e, env, sub, fresh)
            return infer_term(v, env, sub, fresh)


def infer_program(program: Program) -> tuple[Type, dict[int, Type]]:
    fresh = make_type_var_fresh()
    sub: dict[int, Type] = {}

    match program:  # pragma: no branch
        case Program(parameters=ps, body=b):  # pragma: no branch
            env: TypeEnv = {
                n: Scheme(quantified=frozenset(), body=INT)
                for n in ps
            }
            t_res, sub = infer_term(b, env, sub, fresh)
            return apply_sub(sub, t_res), sub