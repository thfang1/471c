from typing import Literal, cast

from L2.optimize import optimize_program
from L2.syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate,
                       Let, Load, Primitive, Program, Reference, Store)


def test_optimize_primitive():
    for op_str in ["+", "-", "*"]:
        op = cast(Literal["+", "-", "*"], op_str)
        results = {"+": 2, "-": 7, "*": 50}
        left_vals = {"+": 1, "-": 10, "*": 10}
        right_vals = {"+": 1, "-": 3, "*": 5}
        
        program = Program(
            parameters=[],
            body=Primitive(
                operator=op,
                left=Immediate(value=left_vals[op]),
                right=Immediate(value=right_vals[op]),
            ),
        )
        expected = Program(parameters=[], body=Immediate(value=results[op]))
        assert optimize_program(program) == expected

def test_optimize_branch_elimination():
    program = Program(
        parameters=[],
        body=Branch(
            operator="<",
            left=Immediate(value=1),
            right=Immediate(value=2),
            consequent=Immediate(value=10),
            otherwise=Immediate(value=20),
        ),
    )
    expected = Program(parameters=[], body=Immediate(value=10))
    assert optimize_program(program) == expected

    program_var = Program(
        parameters=[],
        body=Branch(
            operator="<",
            left=Reference(name="x"),
            right=Immediate(value=2),
            consequent=Immediate(value=10),
            otherwise=Immediate(value=20),
        ),
    )
    assert optimize_program(program_var) == program_var

def test_optimize_let_propagation():

    program = Program(
        parameters=[],
        body=Let(
            bindings=(("x", Immediate(value=10)),),
            body=Primitive(
                operator="+",
                left=Reference(name="x"),
                right=Immediate(value=5),
            ),
        ),
    )
    actual = optimize_program(program)

    if isinstance(actual.body, Let):
        assert actual.body.body == Immediate(value=15)
    else:
        assert actual.body == Immediate(value=15)

def test_optimize_abstract_shadowing():
    program = Program(
        parameters=[],
        body=Let(
            bindings=(("x", Immediate(value=1)),),
            body=Abstract(
                parameters=("x",),
                body=Reference(name="x"),
            ),
        ),
    )
    actual = optimize_program(program)
    assert isinstance(actual.body, Let)
    assert isinstance(actual.body.body, Abstract)
    assert actual.body.body.body == Reference(name="x")

def test_optimize_complex_recursive():
    program = Program(
        parameters=[],
        body=Begin(
            effects=(
                Store(
                    base=Allocate(count=1),
                    index=0,
                    value=Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=1)),
                ),
            ),
            value=Apply(
                target=Reference(name="f"),
                arguments=(Primitive(operator="*", left=Immediate(value=2), right=Immediate(value=3)),),
            ),
        ),
    )
    
    expected_body = Begin(
        effects=(
            Store(base=Allocate(count=1), index=0, value=Immediate(value=2)),
        ),
        value=Apply(target=Reference(name="f"), arguments=(Immediate(value=6),)),
    )
    assert optimize_program(program).body == expected_body

def test_optimize_load():
    program = Program(
        parameters=[],
        body=Load(
            base=Primitive(operator="+", left=Immediate(value=5), right=Immediate(value=5)),
            index=0,
        ),
    )
    expected = Program(parameters=[], body=Load(base=Immediate(value=10), index=0))
    assert optimize_program(program) == expected

def test_optimize_branch_equal():

    program = Program(
        parameters=[],
        body=Branch(
            operator="==",
            left=Immediate(value=5),
            right=Immediate(value=10),
            consequent=Immediate(value=1),
            otherwise=Immediate(value=0),
        ),
    )

    assert optimize_program(program).body == Immediate(value=0)

def test_optimize_let_shadowing_deep():

    program = Program(
        parameters=[],
        body=Let(
            bindings=(("x", Immediate(value=1)),),
            body=Let(
                bindings=(("x", Allocate(count=1)),),
                body=Reference(name="x"),
            ),
        ),
    )
    actual = optimize_program(program).body

    assert isinstance(actual, Let)
    assert isinstance(actual.body, Let)
    assert actual.body.body == Reference(name="x")

def test_optimize_primitive_multiply():

    program = Program(
        parameters=[],
        body=Primitive(
            operator="*",
            left=Immediate(value=6),
            right=Immediate(value=7),
        ),
    )
    assert optimize_program(program).body == Immediate(value=42)

def test_optimize_let_pop_logic():

    inner_let = Let(
        bindings=(("x", Allocate(count=1)),),
        body=Reference(name="x")
    )
    program = Program(
        parameters=[],
        body=Let(
            bindings=(("x", Immediate(value=1)),),
            body=inner_let
        )
    )
    actual = optimize_program(program).body
   
    assert isinstance(actual, Let)
    assert isinstance(actual.body, Let)
    assert actual.body.body == Reference(name="x")

def test_optimize_primitive_no_fold():
   
    program = Program(
        parameters=[],
        body=Primitive(
            operator="+",
            left=Reference(name="a"),
            right=Immediate(value=1)
        )
    )

    assert optimize_program(program).body == program.body

def test_optimize_fixed_point_and_no_op():

    p_fixed = Program(parameters=[], body=Immediate(value=100))
    assert optimize_program(p_fixed).body == Immediate(value=100)


    p_no_fold = Program(
        parameters=[],
        body=Primitive(
            operator="+",
            left=Reference(name="not_a_constant"),
            right=Immediate(value=1)
        )
    )
   
    assert optimize_program(p_no_fold).body == p_no_fold.body


def test_optimize_multi_step_propagation():
    inner = Let(
        bindings=(("b", Reference(name="a")),),
        body=Reference(name="b")
    )
    program = Program(
        parameters=[],
        body=Let(
            bindings=(("a", Immediate(value=1)),),
            body=inner
        )
    )
    actual = optimize_program(program)
    
    res = actual.body
    while isinstance(res, Let):
        res = res.body
    assert res == Immediate(value=1)



def test_optimize_allocate_full_path():
    prog = Program(parameters=[], body=Allocate(count=10))
    assert optimize_program(prog).body == Allocate(count=10)