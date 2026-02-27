import pytest
from L2 import syntax as L2
from L3 import syntax as L3
from L3.eliminate_letrec import (Context, eliminate_letrec_program,
                                 eliminate_letrec_term)


@pytest.mark.skip
def test_check_term_let():
    term = L3.Let(
        bindings=[
            ("x", L3.Immediate(value=0)),
        ],
        body=L3.Reference(name="x"),
    )

    context: Context = {}

    expected = L2.Let(
        bindings=[
            ("x", L2.Immediate(value=0)),
        ],
        body=L2.Reference(name="x"),
    )

    actual = eliminate_letrec_term(term, context)

    assert actual == expected


@pytest.mark.skip
def test_eliminate_letrec_program():
    program = L3.Program(
        parameters=[],
        body=L3.Immediate(value=0),
    )

    expected = L2.Program(
        parameters=[],
        body=L2.Immediate(value=0),
    )

    actual = eliminate_letrec_program(program)

    assert actual == expected

@pytest.mark.skip
def test_eliminate_letrec_term_creates_boxes_and_stores():
    # letrec f = f in f
    # After elimination:
    # let f = allocate(1) in begin
    #   store f 0 (load f 0)
    #   (load f 0)
    term = L3.LetRec(
        bindings=[
            ("f", L3.Reference(name="f")),
        ],
        body=L3.Reference(name="f"),
    )

    context: Context = {}

    expected = L2.Let(
        bindings=[
            ("f", L2.Allocate(count=1)),
        ],
        body=L2.Begin(
            effects=[
                L2.Store(
                    base=L2.Reference(name="f"),
                    index=0,
                    value=L2.Load(base=L2.Reference(name="f"), index=0),
                ),
            ],
            value=L2.Load(base=L2.Reference(name="f"), index=0),
        ),
    )

    actual = eliminate_letrec_term(term, context)

    assert actual == expected

@pytest.mark.skip
def test_eliminate_letrec_term_reference_not_recursive_stays_reference():
    term = L3.Reference(name="x")
    context: Context = {}  # x not recursive here
    expected = L2.Reference(name="x")
    actual = eliminate_letrec_term(term, context)
    assert actual == expected

@pytest.mark.skip
def test_eliminate_letrec_term_reference_recursive_becomes_load():
    term = L3.Reference(name="x")
    context: Context = {"x": None}  # mark as recursive variable
    expected = L2.Load(base=L2.Reference(name="x"), index=0)
    actual = eliminate_letrec_term(term, context)
    assert actual == expected

@pytest.mark.skip
def test_eliminate_let_shadows_recursive_name_in_body():
    # context says "x is recursive" (should load), BUT Let binds x normally,
    # so in body, Reference("x") should stay Reference("x") (no load).
    term = L3.Let(
        bindings=[("x", L3.Immediate(value=1))],
        body=L3.Reference(name="x"),
    )

    context: Context = {"x": None}  # outer says recursive x

    expected = L2.Let(
        bindings=[("x", L2.Immediate(value=1))],
        body=L2.Reference(name="x"),  # important: NOT Load
    )

    actual = eliminate_letrec_term(term, context)

    assert actual == expected

@pytest.mark.skip
def test_eliminate_abstract_shadows_recursive_parameter():
    # context says "x is recursive", BUT lambda parameter x shadows it,
    # so Reference("x") in body should remain Reference("x"), not Load.
    term = L3.Abstract(
        parameters=["x"],
        body=L3.Reference(name="x"),
    )

    context: Context = {"x": None}

    expected = L2.Abstract(
        parameters=["x"],
        body=L2.Reference(name="x"),
    )

    actual = eliminate_letrec_term(term, context)

    assert actual == expected

@pytest.mark.skip
def test_eliminate_apply_and_primitive_recursive_in_lambda():
    # (letrec f = f in (lambda (x) -> f + x))(1)
    # f inside lambda should become Load(f,0)
    term = L3.LetRec(
        bindings=[("f", L3.Reference(name="f"))],
        body=L3.Apply(
            target=L3.Abstract(
                parameters=["x"],
                body=L3.Primitive(
                    operator="+",
                    left=L3.Reference(name="f"),
                    right=L3.Reference(name="x"),
                ),
            ),
            arguments=[L3.Immediate(value=1)],
        ),
    )

    expected = L2.Let(
        bindings=[("f", L2.Allocate(count=1))],
        body=L2.Begin(
            effects=[
                L2.Store(
                    base=L2.Reference(name="f"),
                    index=0,
                    value=L2.Load(base=L2.Reference(name="f"), index=0),
                ),
            ],
            value=L2.Apply(
                target=L2.Abstract(
                    parameters=["x"],
                    body=L2.Primitive(
                        operator="+",
                        left=L2.Load(base=L2.Reference(name="f"), index=0),
                        right=L2.Reference(name="x"),
                    ),
                ),
                arguments=[L2.Immediate(value=1)],
            ),
        ),
    )

    actual = eliminate_letrec_term(term, {})

    assert actual == expected