from L3.syntax import (Abstract, Allocate, Begin, Branch, Immediate, Let,
                       LetRec, Load, Primitive, Program, Reference, Store)
from L3.uniqify import Context, uniqify_program, uniqify_term
from util.sequential_name_generator import SequentialNameGenerator


def test_uniqify_term_reference():
    term = Reference(name="x")

    context: Context = {"x": "y"}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh=fresh)

    expected = Reference(name="y")

    assert actual == expected


def test_uniqify_immediate():
    term = Immediate(value=42)

    context: Context = dict[str, str]()
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)

    expected = Immediate(value=42)

    assert actual == expected


def test_uniqify_term_let():
    term = Let(
        bindings=(
            ("x", Immediate(value=1)),
            ("y", Reference(name="x")),
        ),
        body=Reference(name="x"),
    )

    context: Context = {"x": "external_x"}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)

    expected = Let(
        bindings=(
            ("x0", Immediate(value=1)),
            ("y0", Reference(name="external_x")),
        ),
        body=Reference(name="x0"),
    )

    assert actual == expected

def test_uniqify_term_letrec():
    term = LetRec(
        bindings=(
            ("f", Reference(name="g")),
            ("g", Reference(name="f")),
        ),
        body=Reference(name="f"),
    )

    context: Context = {}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)

    expected = LetRec(
        bindings=(
            ("f0", Reference(name="g0")),
            ("g0", Reference(name="f0")),
        ),
        body=Reference(name="f0"),
    )

    assert actual == expected

def test_uniqify_abstract():
    term = Abstract(
        parameters=("x",),
        body=Reference(name="x"),
    )

    context: Context = {}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)

    expected = Abstract(
        parameters=("x0",),
        body=Reference(name="x0"),
    )

    assert actual == expected

def test_uniqify_branch_and_primitive():
    term = Branch(
        operator="==",
        left=Primitive(operator="+", left=Reference(name="a"), right=Immediate(value=1)),
        right=Immediate(value=10),
        consequent=Reference(name="a"),
        otherwise=Immediate(value=0),
    )

    context: Context = {"a": "a_new"}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)

    expected = Branch(
        operator="==",
        left=Primitive(operator="+", left=Reference(name="a_new"), right=Immediate(value=1)),
        right=Immediate(value=10),
        consequent=Reference(name="a_new"),
        otherwise=Immediate(value=0),
    )

    assert actual == expected

def test_uniqify_begin_store_load():
    term = Begin(
        effects=(
            Store(base=Allocate(count=1), index=0, value=Reference(name="ptr")),
        ),
        value=Load(base=Allocate(count=1), index=0),
    )

    context: Context = {"ptr": "ptr_unique"}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)

    expected = Begin(
        effects=(
            Store(base=Allocate(count=1), index=0, value=Reference(name="ptr_unique")),
        ),
        value=Load(base=Allocate(count=1), index=0),
    )

    assert actual == expected

def test_uniqify_program_full_flow():
    program = Program(
        parameters=("x", "y"),
        body=Primitive(
            operator="+",
            left=Reference(name="x"),
            right=Reference(name="y")
        )
    )
    
    _, new_program = uniqify_program(program)
    
    assert isinstance(new_program.body, Primitive)
    body = new_program.body
    
    assert isinstance(body.left, Reference)
    assert isinstance(body.right, Reference)
 
    assert body.left.name == "x0"
    assert body.right.name == "y0"


def test_uniqify_term_letrec_complex():
    term = LetRec(
        bindings=(
            ("f", Immediate(value=1)),
        ),
        body=Reference(name="f")
    )
    
    context: Context = {}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)
    
    expected = LetRec(
        bindings=(
            ("f0", Immediate(value=1)),
        ),
        body=Reference(name="f0")
    )
    
    assert actual == expected

def test_uniqify_allocate_direct():
    term = Allocate(count=5)
    context: Context = {}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)
    
    assert actual == term

def test_uniqify_letrec_edge_case():
    term = LetRec(
        bindings=(("f", Immediate(value=1)),),
        body=Reference(name="f")
    )
    
    context: Context = {}
    fresh = SequentialNameGenerator()
    actual = uniqify_term(term, context, fresh)
    
    expected = LetRec(
        bindings=(("f0", Immediate(value=1)),),
        body=Reference(name="f0")
    )
    assert actual == expected