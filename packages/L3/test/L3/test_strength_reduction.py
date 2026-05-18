from typing import Literal

from L3.strength_reduction import reduce_rule as reduce_rule
from L3.strength_reduction import reduce_program, reduce_term
from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate,
                       Let, LetRec, Load, Primitive, Program, Reference,
                       Store, Term)


def _prim(op: Literal["+", "-", "*"], left: Term, right: Term) -> Primitive:
    return Primitive(operator=op, left=left, right=right)


def _x() -> Reference:
    return Reference(name="x")


def _prog(body: Term, params: list[str] | None = None) -> Program:
    return Program(parameters=params or [], body=body)


def _reduce_prog(body: Term, params: list[str] | None = None) -> Term:
    return reduce_program(_prog(body, params)).body


class TestReduceRule:

    # ---- (* x 0) -> 0  and  (* 0 x) -> 0 ----

    def test_mul_right_zero(self):
        assert reduce_rule("*", _x(), Immediate(value=0)) == Immediate(value=0)

    def test_mul_left_zero(self):
        assert reduce_rule("*", Immediate(value=0), _x()) == Immediate(value=0)

    # ---- (* x 1) -> x  and  (* 1 x) -> x ----

    def test_mul_right_one(self):
        assert reduce_rule("*", _x(), Immediate(value=1)) == _x()

    def test_mul_left_one(self):
        assert reduce_rule("*", Immediate(value=1), _x()) == _x()

    # ---- (* x 2) -> (+ x x)  and  (* 2 x) -> (+ x x) ----

    def test_mul_right_two(self):
        result = reduce_rule("*", _x(), Immediate(value=2))
        assert result == _prim("+", _x(), _x())

    def test_mul_left_two(self):
        result = reduce_rule("*", Immediate(value=2), _x())
        assert result == _prim("+", _x(), _x())

    # ---- (+ x 0) -> x  and  (+ 0 x) -> x ----

    def test_add_right_zero(self):
        assert reduce_rule("+", _x(), Immediate(value=0)) == _x()

    def test_add_left_zero(self):
        assert reduce_rule("+", Immediate(value=0), _x()) == _x()

    # ---- (- x 0) -> x ----

    def test_sub_right_zero(self):
        assert reduce_rule("-", _x(), Immediate(value=0)) == _x()

    # ---- (- x x) -> 0 ----

    def test_sub_same_reference(self):
        assert reduce_rule("-", Reference(name="x"), Reference(name="x")) == Immediate(value=0)

    def test_sub_different_references_no_reduction(self):
        assert reduce_rule("-", Reference(name="x"), Reference(name="y")) is None

    # ---- no rule fires -> None ----

    def test_mul_arbitrary_operands(self):
        assert reduce_rule("*", _x(), Reference(name="y")) is None

    def test_add_arbitrary_operands(self):
        assert reduce_rule("+", _x(), Reference(name="y")) is None

    def test_sub_arbitrary_operands(self):
        assert reduce_rule("-", _x(), Reference(name="y")) is None

class TestReduceTermPassthrough:
    def test_immediate(self):
        t = Immediate(value=42)
        assert reduce_term(t) == t

    def test_reference(self):
        t = Reference(name="x")
        assert reduce_term(t) == t

    def test_allocate(self):
        t = Allocate(count=1)
        assert reduce_term(t) == t

    def test_primitive_no_rule(self):
        t = _prim("+", _x(), Reference(name="y"))
        assert reduce_term(t) == t

    def test_abstract(self):
        t = Abstract(parameters=["x"], body=_prim("*", _x(), Immediate(value=1)))
        result = reduce_term(t)
        assert isinstance(result, Abstract)
        assert result.body == _x()

    def test_apply(self):
        t = Apply(
            target=Reference(name="f"),
            arguments=[_prim("*", _x(), Immediate(value=1))],
        )
        result = reduce_term(t)
        assert isinstance(result, Apply)
        assert result.arguments[0] == _x()

    def test_branch(self):
        t = Branch(
            operator="<",
            left=_prim("+", _x(), Immediate(value=0)),
            right=Immediate(value=1),
            consequent=_prim("*", _x(), Immediate(value=0)),
            otherwise=_prim("*", _x(), Immediate(value=1)),
        )
        result = reduce_term(t)
        assert isinstance(result, Branch)
        assert result.left == _x()
        assert result.consequent == Immediate(value=0)
        assert result.otherwise == _x()

    def test_load(self):
        t = Load(base=_prim("+", _x(), Immediate(value=0)), index=0)
        result = reduce_term(t)
        assert isinstance(result, Load)
        assert result.base == _x()

    def test_store(self):
        t = Store(
            base=Reference(name="p"),
            index=0,
            value=_prim("*", _x(), Immediate(value=1)),
        )
        result = reduce_term(t)
        assert isinstance(result, Store)
        assert result.value == _x()

    def test_begin(self):
        t = Begin(
            effects=[_prim("*", _x(), Immediate(value=0))],
            value=_prim("+", _x(), Immediate(value=0)),
        )
        result = reduce_term(t)
        assert isinstance(result, Begin)
        assert result.effects[0] == Immediate(value=0)
        assert result.value == _x()

    def test_let(self):
        t = Let(
            bindings=[("y", _prim("*", _x(), Immediate(value=1)))],
            body=Reference(name="y"),
        )
        result = reduce_term(t)
        assert isinstance(result, Let)
        assert result.bindings[0][1] == _x()

    def test_letrec(self):
        t = LetRec(
            bindings=[("f", Abstract(parameters=["x"],
                                     body=_prim("*", _x(), Immediate(value=1))))],
            body=Reference(name="f"),
        )
        result = reduce_term(t)
        assert isinstance(result, LetRec)
        assert isinstance(result.bindings[0][1], Abstract)
        assert result.bindings[0][1].body == _x()


class TestReduceTermRules:
    def test_mul_zero(self):
        assert reduce_term(_prim("*", _x(), Immediate(value=0))) == Immediate(value=0)

    def test_mul_one(self):
        assert reduce_term(_prim("*", _x(), Immediate(value=1))) == _x()

    def test_mul_two(self):
        assert reduce_term(_prim("*", _x(), Immediate(value=2))) == _prim("+", _x(), _x())

    def test_add_zero(self):
        assert reduce_term(_prim("+", _x(), Immediate(value=0))) == _x()

    def test_sub_zero(self):
        assert reduce_term(_prim("-", _x(), Immediate(value=0))) == _x()

    def test_sub_self(self):
        assert reduce_term(
            _prim("-", Reference(name="x"), Reference(name="x"))
        ) == Immediate(value=0)

    def test_bottom_up_composition(self):
        # (* (* x 1) 2)  ->  (* x 2)  ->  (+ x x)
        inner = _prim("*", _x(), Immediate(value=1))
        outer = _prim("*", inner, Immediate(value=2))
        assert reduce_term(outer) == _prim("+", _x(), _x())

    def test_no_spurious_rewrite(self):
        # (* x 3) — no rule for multiplying by 3
        t = _prim("*", _x(), Immediate(value=3))
        assert reduce_term(t) == t


class TestReduceProgram:
    def test_params_preserved(self):
        prog = _prog(Reference(name="n"), params=["n"])
        result = reduce_program(prog)
        assert list(result.parameters) == ["n"]

    def test_bodyreduce_ruled(self):
        assert _reduce_prog(_prim("*", _x(), Immediate(value=1)), params=["x"]) == _x()

    def test_synergy_with_constant_folding(self):
        from L3.cse import simplify
        body = _prim("*", Reference(name="x"), Immediate(value=2))
        reduced = reduce_term(body)
        folded = simplify(reduced, {"x": Immediate(value=3)})
        assert folded == Immediate(value=6)

    def test_fewer_primitives_than_without_reduction(self):
        def count_primitives(t: Term) -> int:
            match t:
                case Primitive(left=l, right=r):
                    return 1 + count_primitives(l) + count_primitives(r)
                case Let(bindings=bs, body=b):
                    return sum(count_primitives(v) for _, v in bs) + count_primitives(b)
                case _:
                    return 0

        body = Let(
            bindings=[
                ("a", _prim("*", _x(), Immediate(value=1))),
                ("b", _prim("+", _x(), Immediate(value=0))),
                ("c", _prim("-", _x(), Immediate(value=0))),
            ],
            body=_prim("+", Reference(name="a"),
                       _prim("+", Reference(name="b"), Reference(name="c"))),
        )
        before = count_primitives(body)
        after  = count_primitives(reduce_term(body))
        assert after < before

    def test_extensibility_new_rule(self):
        t = _prim("-", Immediate(value=0), _x())
        assert reduce_term(t) == t