from L0 import syntax as L0
from L1 import syntax as L1
from L1.close import close_program, close_statement, free_vars
from util.sequential_name_generator import SequentialNameGenerator


def test_close_simple_halt():
    prog = L1.Program(parameters=[], body=L1.Halt(value="x"))
    fresh = SequentialNameGenerator()
    actual = close_program(prog, fresh)

    assert any(p.name == "main" for p in actual.procedures)

def test_close_abstract_no_free_vars():
    body = L1.Abstract(
        destination="f",
        parameters=["x"],
        body=L1.Halt(value="x"),
        then=L1.Halt(value="f")
    )
    prog = L1.Program(parameters=[], body=body)
    fresh = SequentialNameGenerator()
    actual = close_program(prog, fresh)

    assert len(actual.procedures) == 2
    
def test_close_with_free_vars():
    inner_body = L1.Primitive(
        destination="res", operator="+", left="x", right="y",
        then=L1.Halt(value="res")
    )
    main_body = L1.Immediate(
        destination="y", value=10, then=L1.Abstract(
            destination="f", parameters=["x"], body=inner_body,
            then=L1.Apply(target="f", arguments=["v5"])
        )
    )
    prog = L1.Program(parameters=["v5"], body=main_body)
    fresh = SequentialNameGenerator()
    actual = close_program(prog, fresh)

    lambda_proc = next(p for p in actual.procedures if p.name != "main")
    assert any(isinstance(s, L0.Load) for s in [lambda_proc.body]) 

import L1.syntax as L1
from L1.close import free_vars


def test_free_vars_coverage():
    assert free_vars(L1.Copy(destination="d", source="s", then=L1.Halt(value="d"))) == {"s"}
    assert free_vars(L1.Abstract(destination="f", parameters=["p"], body=L1.Halt(value="v"), then=L1.Halt(value="f"))) == {"v"}
    assert free_vars(L1.Branch(operator="==", left="l", right="r", then=L1.Halt(value="l"), otherwise=L1.Halt(value="r"))) == {"l", "r"}
    assert free_vars(L1.Allocate(destination="d", count=1, then=L1.Halt(value="d"))) == set()
    assert free_vars(L1.Load(destination="d", base="b", index=0, then=L1.Halt(value="d"))) == {"b"}
    assert free_vars(L1.Store(base="b", index=0, value="v", then=L1.Halt(value="b"))) == {"b", "v"}    

def test_free_vars_apply():
    stmt = L1.Apply(target="f", arguments=["x", "y"])
    assert free_vars(stmt) == {"f", "x", "y"}
 
 
def test_free_vars_apply_no_args():
    stmt = L1.Apply(target="f", arguments=[])
    assert free_vars(stmt) == {"f"}

def test_free_vars_immediate():
    stmt = L1.Immediate(destination="r", value=0, then=L1.Halt(value="r"))
    assert free_vars(stmt) == set()
 
 
def test_free_vars_immediate_then_uses_other():
    stmt = L1.Immediate(destination="r", value=0, then=L1.Halt(value="x"))
    assert free_vars(stmt) == {"x"}
 
def test_close_statement_copy():
    fresh = SequentialNameGenerator()
    procedures: list[L0.Procedure] = []
    stmt = L1.Copy(destination="b", source="a", then=L1.Halt(value="b"))
    result = close_statement(stmt, procedures, fresh)
    assert result == L0.Copy(destination="b", source="a", then=L0.Halt(value="b"))
    assert procedures == []
 

def test_close_statement_branch():
    fresh = SequentialNameGenerator()
    procedures: list[L0.Procedure] = []
    stmt = L1.Branch(
        operator="<",
        left="x",
        right="y",
        then=L1.Halt(value="x"),
        otherwise=L1.Halt(value="y"),
    )
    result = close_statement(stmt, procedures, fresh)
    assert result == L0.Branch(
        operator="<",
        left="x",
        right="y",
        then=L0.Halt(value="x"),
        otherwise=L0.Halt(value="y"),
    )
 

def test_close_statement_allocate():
    fresh = SequentialNameGenerator()
    procedures: list[L0.Procedure] = []
    stmt = L1.Allocate(destination="p", count=3, then=L1.Halt(value="p"))
    result = close_statement(stmt, procedures, fresh)
    assert result == L0.Allocate(destination="p", count=3, then=L0.Halt(value="p"))
 

def test_close_statement_load():
    fresh = SequentialNameGenerator()
    procedures: list[L0.Procedure] = []
    stmt = L1.Load(destination="v", base="p", index=2, then=L1.Halt(value="v"))
    result = close_statement(stmt, procedures, fresh)
    assert result == L0.Load(destination="v", base="p", index=2, then=L0.Halt(value="v"))
 
 
def test_close_statement_store():
    fresh = SequentialNameGenerator()
    procedures: list[L0.Procedure] = []
    stmt = L1.Store(base="p", index=0, value="x", then=L1.Halt(value="p"))
    result = close_statement(stmt, procedures, fresh)
    assert result == L0.Store(base="p", index=0, value="x", then=L0.Halt(value="p"))
 
  
def test_close_program_all_statement_types():
    """
    Exercises Copy, Branch, Allocate, Load, Store, Apply, and Immediate
    all in a single program so every close_statement branch is hit.
    """
    fresh = SequentialNameGenerator()

    program = L1.Program(
        parameters=["x"],
        body=L1.Allocate(
            destination="p",
            count=1,
            then=L1.Store(
                base="p",
                index=0,
                value="x",
                then=L1.Load(
                    destination="v",
                    base="p",
                    index=0,
                    then=L1.Copy(
                        destination="w",
                        source="v",
                        then=L1.Branch(
                            operator="<",
                            left="w",
                            right="x",
                            then=L1.Halt(value="w"),
                            otherwise=L1.Halt(value="x"),
                        ),
                    ),
                ),
            ),
        ),
    )
 
    result = close_program(program, fresh)
    assert isinstance(result, L0.Program)
    assert len(result.procedures) == 1
    main = result.procedures[0]
    assert isinstance(main.body, L0.Allocate)
 