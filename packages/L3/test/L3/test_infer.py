from typing import Any

import pytest

from L3.infer import (
    BLOCK,
    INT,
    BlockType,
    FuncType,
    IntType,
    Scheme,
    Type,
    TypeVar,
    apply_sub,
    generalize,
    infer_program,
    instantiate,
    occurs,
    unify,
    free_vars,
    make_type_var_fresh,
)
from L3.syntax import (
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
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prog(body: Any, params: list[str] | None = None) -> tuple[Type, dict[int, Type]]:
    """Convenience wrapper: infer the type of a program."""
    return infer_program(Program(parameters=params or [], body=body))


def _type(body: Any, params: list[str] | None = None) -> Type:
    """Return only the inferred type (discards substitution)."""
    t, _ = _prog(body, params)
    return t


# ---------------------------------------------------------------------------
# Constants and __str__
# ---------------------------------------------------------------------------

class TestConstants:
    def test_int_str(self):
        assert str(INT) == "Int"

    def test_block_str(self):
        assert str(BLOCK) == "Block"

    def test_int_singleton(self):
        assert IntType() == INT

    def test_block_singleton(self):
        assert BlockType() == BLOCK


class TestFuncType:
    def test_str_single_param(self):
        assert str(FuncType(params=(INT,), ret=INT)) == "(Int) -> Int"

    def test_str_multi_param(self):
        assert str(FuncType(params=(INT, BLOCK), ret=INT)) == "(Int, Block) -> Int"

    def test_str_no_params(self):
        assert str(FuncType(params=(), ret=BLOCK)) == "() -> Block"


class TestTypeVar:
    def test_str_greek_letters(self):
        assert str(TypeVar(id=0)) == "α"
        assert str(TypeVar(id=1)) == "β"

    def test_str_high_id(self):
        assert str(TypeVar(id=150)) == "τ150"

    def test_str_wraps_around(self):
        # id=24 wraps: 24 % 24 == 0 → "α"  (24 letters in the alphabet string)
        assert str(TypeVar(id=24)) == "α"


# ---------------------------------------------------------------------------
# make_type_var_fresh
# ---------------------------------------------------------------------------

class TestMakeTypeVarFresh:
    def test_produces_distinct_vars(self):
        fresh = make_type_var_fresh()
        a = fresh()
        b = fresh()
        assert a != b
        assert a.id == 0
        assert b.id == 1

    def test_multiple_instances_independent(self):
        f1 = make_type_var_fresh()
        f2 = make_type_var_fresh()
        assert f1().id == f2().id == 0


# ---------------------------------------------------------------------------
# apply_sub
# ---------------------------------------------------------------------------

class TestApplySub:
    def test_unbound_var_unchanged(self):
        tv = TypeVar(id=0)
        assert apply_sub({}, tv) == tv

    def test_bound_var_replaced(self):
        tv = TypeVar(id=0)
        assert apply_sub({0: INT}, tv) == INT

    def test_chained_substitution(self):
        # 0 → 1,  1 → Int  ⟹  apply(0) = Int
        tv0, tv1 = TypeVar(id=0), TypeVar(id=1)
        assert apply_sub({0: tv1, 1: INT}, tv0) == INT

    def test_func_type_recurses(self):
        tv = TypeVar(id=0)
        ft = FuncType(params=(tv,), ret=tv)
        result = apply_sub({0: INT}, ft)
        assert result == FuncType(params=(INT,), ret=INT)

    def test_int_block_unchanged(self):
        assert apply_sub({0: INT}, INT) == INT
        assert apply_sub({0: INT}, BLOCK) == BLOCK


# ---------------------------------------------------------------------------
# occurs
# ---------------------------------------------------------------------------

class TestOccurs:
    def test_direct_match(self):
        assert occurs(0, TypeVar(id=0), {})

    def test_no_match(self):
        assert not occurs(0, TypeVar(id=1), {})

    def test_in_func_params(self):
        ft = FuncType(params=(TypeVar(id=0),), ret=INT)
        assert occurs(0, ft, {})

    def test_in_func_ret(self):
        ft = FuncType(params=(INT,), ret=TypeVar(id=0))
        assert occurs(0, ft, {})

    def test_not_in_func(self):
        ft = FuncType(params=(INT,), ret=INT)
        assert not occurs(0, ft, {})

    def test_concrete_type_false(self):
        assert not occurs(0, INT, {})
        assert not occurs(0, BLOCK, {})

    def test_via_substitution(self):
        # var 0 → INT in sub; occurs(0, TypeVar(1), {1: TypeVar(0)}) → False
        # because apply_sub resolves TypeVar(1) → TypeVar(0) → INT, not a TypeVar
        assert not occurs(0, TypeVar(id=1), {1: INT})


# ---------------------------------------------------------------------------
# unify
# ---------------------------------------------------------------------------

class TestUnify:
    def test_identical_returns_sub(self):
        sub = {0: INT}
        result = unify(INT, INT, sub)
        assert result == sub

    def test_typevar_left(self):
        result = unify(TypeVar(id=0), INT, {})
        assert result[0] == INT

    def test_typevar_right_symmetric(self):
        result = unify(INT, TypeVar(id=0), {})
        assert result[0] == INT

    def test_func_types(self):
        f1 = FuncType(params=(TypeVar(id=0),), ret=INT)
        f2 = FuncType(params=(INT,), ret=INT)
        result = unify(f1, f2, {})
        assert result[0] == INT

    def test_arity_mismatch_raises(self):
        f1 = FuncType(params=(INT,), ret=INT)
        f2 = FuncType(params=(INT, INT), ret=INT)
        with pytest.raises(TypeError, match="Arity mismatch"):
            unify(f1, f2, {})

    def test_concrete_mismatch_raises(self):
        with pytest.raises(TypeError, match="Type mismatch"):
            unify(INT, BLOCK, {})

    def test_int_block_mismatch_raises(self):
        with pytest.raises(TypeError, match="Type mismatch"):
            unify(INT, FuncType(params=(), ret=INT), {})

    def test_occurs_check_raises(self):
        tv = TypeVar(id=0)
        ft = FuncType(params=(tv,), ret=INT)
        with pytest.raises(TypeError, match="Infinite type"):
            unify(tv, ft, {})


# ---------------------------------------------------------------------------
# free_vars
# ---------------------------------------------------------------------------

class TestFreeVars:
    def test_typevar(self):
        assert free_vars(TypeVar(id=5)) == frozenset({5})

    def test_int_empty(self):
        assert free_vars(INT) == frozenset()

    def test_block_empty(self):
        assert free_vars(BLOCK) == frozenset()

    def test_func_type(self):
        ft = FuncType(params=(TypeVar(id=0), TypeVar(id=1)), ret=TypeVar(id=2))
        assert free_vars(ft) == frozenset({0, 1, 2})

    def test_func_type_no_free(self):
        assert free_vars(FuncType(params=(INT,), ret=BLOCK)) == frozenset()


# ---------------------------------------------------------------------------
# generalize / instantiate
# ---------------------------------------------------------------------------

class TestGeneralize:
    def test_free_var_generalized(self):
        tv = TypeVar(id=0)
        scheme = generalize({}, tv, {})
        assert 0 in scheme.quantified

    def test_env_var_not_generalized(self):
        tv = TypeVar(id=0)
        env = {"x": Scheme(quantified=frozenset(), body=tv)}
        scheme = generalize(env, tv, {})
        assert 0 not in scheme.quantified

    def test_substitution_applied(self):
        tv = TypeVar(id=0)
        scheme = generalize({}, tv, {0: INT})
        assert scheme.body == INT
        assert scheme.quantified == frozenset()


class TestInstantiate:
    def test_monotype_unchanged(self):
        fresh = make_type_var_fresh()
        scheme = Scheme(quantified=frozenset(), body=INT)
        assert instantiate(scheme, fresh) == INT

    def test_quantified_var_replaced(self):
        fresh = make_type_var_fresh()
        # Use a high id so it can't collide with the fresh counter starting at 0
        scheme = Scheme(quantified=frozenset({9999}), body=TypeVar(id=9999))
        result = instantiate(scheme, fresh)
        assert isinstance(result, TypeVar)
        assert result.id != 9999   # replaced with a fresh var

    def test_two_instantiations_independent(self):
        fresh = make_type_var_fresh()
        scheme = Scheme(quantified=frozenset({9999}), body=TypeVar(id=9999))
        r1 = instantiate(scheme, fresh)
        r2 = instantiate(scheme, fresh)
        assert r1 != r2


# ---------------------------------------------------------------------------
# infer_term via infer_program
# ---------------------------------------------------------------------------

class TestInferImmediate:
    def test_int_literal(self):
        assert _type(Immediate(value=42)) == INT

    def test_negative(self):
        assert _type(Immediate(value=-1)) == INT


class TestInferReference:
    def test_bound_param(self):
        assert _type(Reference(name="x"), params=["x"]) == INT

    def test_unbound_raises(self):
        with pytest.raises(TypeError, match="Unbound"):
            _type(Reference(name="missing"))


class TestInferPrimitive:
    def test_addition(self):
        expr = Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))
        assert _type(expr) == INT

    def test_non_int_operand_raises(self):
        # allocate returns BLOCK; using it as a primitive operand should fail
        expr = Primitive(operator="+", left=Allocate(count=1), right=Immediate(value=1))
        with pytest.raises(TypeError):
            _type(expr)


class TestInferAbstract:
    def test_identity_function(self):
        lam = Abstract(parameters=["x"], body=Reference(name="x"))
        t = _type(lam)
        assert isinstance(t, FuncType)
        assert t.ret == t.params[0]

    def test_constant_function(self):
        lam = Abstract(parameters=["x"], body=Immediate(value=0))
        t = _type(lam)
        assert isinstance(t, FuncType)
        assert t.ret == INT

    def test_multi_param(self):
        add = Abstract(
            parameters=["x", "y"],
            body=Primitive(operator="+", left=Reference(name="x"), right=Reference(name="y")),
        )
        t = _type(add)
        assert isinstance(t, FuncType)
        assert len(t.params) == 2


class TestInferApply:
    def test_apply_identity(self):
        lam = Abstract(parameters=["x"], body=Reference(name="x"))
        app = Apply(target=lam, arguments=[Immediate(value=1)])
        assert _type(app) == INT

    def test_arity_mismatch_raises(self):
        lam = Abstract(parameters=["x"], body=Reference(name="x"))
        with pytest.raises(TypeError):
            _type(Apply(target=lam, arguments=[Immediate(value=1), Immediate(value=2)]))

    def test_type_mismatch_raises(self):
        # apply an int as a function
        with pytest.raises(TypeError):
            _type(Apply(target=Immediate(value=1), arguments=[Immediate(value=2)]))


class TestInferLet:
    def test_simple_binding(self):
        expr = Let(bindings=[("x", Immediate(value=1))], body=Reference(name="x"))
        assert _type(expr) == INT

    def test_polymorphic_let(self):
        # let id = (lambda (x) x) in (id 1)
        id_lam = Abstract(parameters=["x"], body=Reference(name="x"))
        expr = Let(
            bindings=[("id", id_lam)],
            body=Apply(target=Reference(name="id"), arguments=[Immediate(value=1)]),
        )
        assert _type(expr) == INT

    def test_nested_let(self):
        expr = Let(
            bindings=[("x", Immediate(value=1))],
            body=Let(
                bindings=[("y", Immediate(value=2))],
                body=Primitive(operator="+", left=Reference(name="x"), right=Reference(name="y")),
            ),
        )
        assert _type(expr) == INT


class TestInferLetRec:
    def test_simple_letrec(self):
        # letrec f = (lambda (x) x) in (f 1)
        lam = Abstract(parameters=["x"], body=Reference(name="x"))
        expr = LetRec(
            bindings=[("f", lam)],
            body=Apply(target=Reference(name="f"), arguments=[Immediate(value=1)]),
        )
        assert _type(expr) == INT

    def test_recursive_function(self):
        # letrec f = (lambda (n) (if (== n 0) 0 (f (- n 1)))) in (f 5)
        body = Branch(
            operator="==",
            left=Reference(name="n"),
            right=Immediate(value=0),
            consequent=Immediate(value=0),
            otherwise=Apply(
                target=Reference(name="f"),
                arguments=[Primitive(operator="-", left=Reference(name="n"), right=Immediate(value=1))],
            ),
        )
        lam = Abstract(parameters=["n"], body=body)
        expr = LetRec(
            bindings=[("f", lam)],
            body=Apply(target=Reference(name="f"), arguments=[Immediate(value=5)]),
        )
        assert _type(expr) == INT


class TestInferBranch:
    def test_both_branches_int(self):
        br = Branch(
            operator="<",
            left=Immediate(value=1), right=Immediate(value=2),
            consequent=Immediate(value=10), otherwise=Immediate(value=20),
        )
        assert _type(br) == INT

    def test_branch_type_mismatch_raises(self):
        # one branch returns BLOCK, the other INT
        br = Branch(
            operator="<",
            left=Immediate(value=1), right=Immediate(value=2),
            consequent=Allocate(count=1),
            otherwise=Immediate(value=0),
        )
        with pytest.raises(TypeError):
            _type(br)

    def test_non_int_condition_raises(self):
        br = Branch(
            operator="<",
            left=Allocate(count=1), right=Immediate(value=0),
            consequent=Immediate(value=1), otherwise=Immediate(value=0),
        )
        with pytest.raises(TypeError):
            _type(br)


class TestInferMemory:
    def test_allocate_returns_block(self):
        assert _type(Allocate(count=3)) == BLOCK

    def test_load_returns_int(self):
        expr = Let(
            bindings=[("b", Allocate(count=1))],
            body=Load(base=Reference(name="b"), index=0),
        )
        assert _type(expr) == INT

    def test_store_returns_int(self):
        expr = Let(
            bindings=[("b", Allocate(count=1))],
            body=Store(base=Reference(name="b"), index=0, value=Immediate(value=42)),
        )
        assert _type(expr) == INT

    def test_load_non_block_raises(self):
        with pytest.raises(TypeError):
            _type(Load(base=Immediate(value=0), index=0))

    def test_store_non_block_base_raises(self):
        with pytest.raises(TypeError):
            _type(Store(base=Immediate(value=0), index=0, value=Immediate(value=1)))


class TestInferBegin:
    def test_effects_discarded(self):
        expr = Begin(
            effects=[Immediate(value=99)],
            value=Immediate(value=1),
        )
        assert _type(expr) == INT

    def test_empty_effects(self):
        assert _type(Begin(effects=[], value=Immediate(value=0))) == INT

    def test_effect_with_side_effect(self):
        expr = Let(
            bindings=[("b", Allocate(count=1))],
            body=Begin(
                effects=[Store(base=Reference(name="b"), index=0, value=Immediate(value=1))],
                value=Load(base=Reference(name="b"), index=0),
            ),
        )
        assert _type(expr) == INT


# ---------------------------------------------------------------------------
# infer_program
# ---------------------------------------------------------------------------

class TestInferProgram:
    def test_returns_tuple(self):
        result = infer_program(Program(parameters=[], body=Immediate(value=0)))
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_type_is_first(self):
        t, _ = infer_program(Program(parameters=[], body=Immediate(value=0)))
        assert t == INT

    def test_sub_is_dict(self):
        _, sub = infer_program(Program(parameters=[], body=Immediate(value=0)))
        assert isinstance(sub, dict)

    def test_params_are_int(self):
        t, _ = infer_program(Program(parameters=["x", "y"], body=Reference(name="x")))
        assert t == INT

    def test_complex_program(self):
        # (program (p) (let ((f (lambda (x y) (+ x y)))) (f p 1)))
        add = Abstract(
            parameters=["x", "y"],
            body=Primitive(operator="+", left=Reference(name="x"), right=Reference(name="y")),
        )
        expr = Let(
            bindings=[("f", add)],
            body=Apply(
                target=Reference(name="f"),
                arguments=[Reference(name="p"), Immediate(value=1)],
            ),
        )
        t, _ = infer_program(Program(parameters=["p"], body=expr))
        assert t == INT