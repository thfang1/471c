import pytest
from L0 import syntax as L0
from L0.register_allocation import (REGISTERS, build_interference, color_graph,
                                    compute_liveness, get_successors, get_vars,
                                    rewrite_program)


def all_stmts_reachable(body: L0.Statement) -> list[L0.Statement]:
    result: list[L0.Statement] = []
    visited: set[int] = set()
    stack: list[L0.Statement] = [body]
    while stack:
        s = stack.pop()
        if id(s) in visited:
            continue
        visited.add(id(s))
        result.append(s)
        stack.extend(get_successors(s))
    return result


def collect_vars(prog: L0.Program) -> set[str]:
    names: set[str] = set()
    for proc in prog.procedures:
        names.update(proc.parameters)
        for s in all_stmts_reachable(proc.body):
            gen, kill = get_vars(s)
            names |= gen | kill
    return names

class TestGetVars:
    def test_copy(self):
        halt = L0.Halt(value="x")
        stmt = L0.Copy(destination="x", source="y", then=halt)
        gen, kill = get_vars(stmt)
        assert gen == {"y"}
        assert kill == {"x"}

    def test_immediate(self):
        halt = L0.Halt(value="x")
        stmt = L0.Immediate(destination="x", value=42, then=halt)
        gen, kill = get_vars(stmt)
        assert gen == set()
        assert kill == {"x"}

    def test_primitive(self):
        halt = L0.Halt(value="z")
        stmt = L0.Primitive(destination="z", operator="+", left="x", right="y", then=halt)
        gen, kill = get_vars(stmt)
        assert gen == {"x", "y"}
        assert kill == {"z"}

    def test_branch(self):
        halt = L0.Halt(value="x")
        stmt = L0.Branch(operator="<", left="a", right="b", then=halt, otherwise=halt)
        gen, kill = get_vars(stmt)
        assert gen == {"a", "b"}
        assert kill == set()

    def test_allocate(self):
        halt = L0.Halt(value="p")
        stmt = L0.Allocate(destination="p", count=4, then=halt)
        gen, kill = get_vars(stmt)
        assert gen == set()
        assert kill == {"p"}

    def test_load(self):
        halt = L0.Halt(value="v")
        stmt = L0.Load(destination="v", base="p", index=0, then=halt)
        gen, kill = get_vars(stmt)
        assert gen == {"p"}
        assert kill == {"v"}

    def test_store(self):
        halt = L0.Halt(value="p")
        stmt = L0.Store(base="p", index=0, value="v", then=halt)
        gen, kill = get_vars(stmt)
        assert gen == {"p", "v"}
        assert kill == set()

    def test_address(self):
        halt = L0.Halt(value="a")
        stmt = L0.Address(destination="a", name="foo", then=halt)
        gen, kill = get_vars(stmt)
        assert gen == set()
        assert kill == {"a"}

    def test_call(self):
        stmt = L0.Call(target="fn", arguments=["x", "y"])
        gen, kill = get_vars(stmt)
        assert gen == {"fn", "x", "y"}
        assert kill == set()

    def test_halt(self):
        stmt = L0.Halt(value="r")
        gen, kill = get_vars(stmt)
        assert gen == {"r"}
        assert kill == set()


class TestGetSuccessors:
    def setup_method(self):
        self.halt = L0.Halt(value="x")

    def test_halt_has_no_successors(self):
        assert get_successors(self.halt) == []

    def test_call_has_no_successors(self):
        stmt = L0.Call(target="fn", arguments=[])
        assert get_successors(stmt) == []

    def test_copy_successor(self):
        stmt = L0.Copy(destination="x", source="y", then=self.halt)
        assert get_successors(stmt) == [self.halt]

    def test_immediate_successor(self):
        stmt = L0.Immediate(destination="x", value=1, then=self.halt)
        assert get_successors(stmt) == [self.halt]

    def test_primitive_successor(self):
        stmt = L0.Primitive(destination="z", operator="+", left="x", right="y", then=self.halt)
        assert get_successors(stmt) == [self.halt]

    def test_branch_two_successors(self):
        halt2 = L0.Halt(value="y")
        stmt = L0.Branch(operator="==", left="a", right="b", then=self.halt, otherwise=halt2)
        succs = get_successors(stmt)
        assert len(succs) == 2
        assert self.halt in succs
        assert halt2 in succs

    def test_allocate_successor(self):
        stmt = L0.Allocate(destination="p", count=1, then=self.halt)
        assert get_successors(stmt) == [self.halt]

    def test_load_successor(self):
        stmt = L0.Load(destination="v", base="p", index=0, then=self.halt)
        assert get_successors(stmt) == [self.halt]

    def test_store_successor(self):
        stmt = L0.Store(base="p", index=0, value="v", then=self.halt)
        assert get_successors(stmt) == [self.halt]

    def test_address_successor(self):
        stmt = L0.Address(destination="a", name="lbl", then=self.halt)
        assert get_successors(stmt) == [self.halt]

    def test_shared_node_visited_once(self):
        halt   = L0.Halt(value="x")
        branch = L0.Branch(operator="==", left="a", right="b",
                           then=halt, otherwise=halt)
        stmts  = all_stmts_reachable(branch)
        assert stmts.count(halt) == 1


class TestComputeLiveness:
    def test_single_halt(self):
        halt = L0.Halt(value="x")
        live_out = compute_liveness(halt)
        assert live_out[id(halt)] == set()

    def test_linear_two_stmts(self):
        halt = L0.Halt(value="x")
        imm  = L0.Immediate(destination="x", value=1, then=halt)
        live_out = compute_liveness(imm)
        assert "x" in live_out[id(imm)]
        assert live_out[id(halt)] == set()

    def test_dead_variable_not_live(self):
        halt  = L0.Halt(value="x")
        imm2  = L0.Immediate(destination="x", value=2, then=halt)
        imm1  = L0.Immediate(destination="x", value=1, then=imm2)
        live_out = compute_liveness(imm1)
        assert "x" not in live_out[id(imm1)]

    def test_branch_liveness_merges(self):
        halt_a  = L0.Halt(value="a")
        halt_b  = L0.Halt(value="b")
        branch  = L0.Branch(operator="<", left="a", right="b",
                            then=halt_a, otherwise=halt_b)
        live_out = compute_liveness(branch)
        assert live_out[id(branch)] == {"a", "b"}

    def test_two_vars_simultaneously_live(self):
        halt  = L0.Halt(value="z")
        prim  = L0.Primitive(destination="z", operator="+", left="x", right="y", then=halt)
        imm_y = L0.Immediate(destination="y", value=2, then=prim)
        imm_x = L0.Immediate(destination="x", value=1, then=imm_y)
        live_out = compute_liveness(imm_x)
        assert "x" in live_out[id(imm_x)]


class TestBuildInterference:
    def test_no_interference_sequential(self):
        halt = L0.Halt(value="y")
        copy = L0.Copy(destination="y", source="x", then=halt)
        imm  = L0.Immediate(destination="x", value=1, then=copy)
        live_out = compute_liveness(imm)
        graph = build_interference(imm, live_out)
        assert "x" not in graph.get("y", set())
        assert "y" not in graph.get("x", set())

    def test_interference_simultaneous(self):
        halt  = L0.Halt(value="z")
        prim  = L0.Primitive(destination="z", operator="+", left="x", right="y", then=halt)
        imm_y = L0.Immediate(destination="y", value=2, then=prim)
        imm_x = L0.Immediate(destination="x", value=1, then=imm_y)
        live_out = compute_liveness(imm_x)
        graph = build_interference(imm_x, live_out)
        assert "y" in graph.get("x", set())
        assert "x" in graph.get("y", set())

    def test_graph_is_symmetric(self):
        halt  = L0.Halt(value="z")
        prim  = L0.Primitive(destination="z", operator="+", left="x", right="y", then=halt)
        imm_y = L0.Immediate(destination="y", value=2, then=prim)
        imm_x = L0.Immediate(destination="x", value=1, then=imm_y)
        live_out = compute_liveness(imm_x)
        graph = build_interference(imm_x, live_out)
        for u, neighbors in graph.items():
            for v in neighbors:
                assert u in graph[v], f"{u}→{v} exists but {v}→{u} doesn't exist"


class TestColorGraph:
    def test_empty_graph(self):
        assert color_graph({}) == {}

    def test_single_node(self):
        colors = color_graph({"x": set()})
        assert colors["x"] in REGISTERS

    def test_two_interfering_nodes_get_different_colors(self):
        graph = {"x": {"y"}, "y": {"x"}}
        colors = color_graph(graph)
        assert colors["x"] in REGISTERS
        assert colors["y"] in REGISTERS
        assert colors["x"] != colors["y"]

    def test_triangle_three_colors(self):
        graph = {
            "a": {"b", "c"},
            "b": {"a", "c"},
            "c": {"a", "b"},
        }
        colors = color_graph(graph)
        assert colors["a"] != colors["b"]
        assert colors["b"] != colors["c"]
        assert colors["a"] != colors["c"]

    def test_no_adjacent_same_color(self):
        nodes = ["n0", "n1", "n2", "n3", "n4"]
        graph: dict[str, set[str]] = {n: set() for n in nodes}
        for i, n in enumerate(nodes):
            graph[n].add(nodes[(i + 1) % 5])
            graph[n].add(nodes[(i - 1) % 5])
        colors = color_graph(graph)
        for u, neighbors in graph.items():
            for v in neighbors:
                assert colors[u] != colors[v], \
                    f"Neighbors {u} and {v} are allocated to the same register {colors[u]}"

    def test_all_assigned_registers_are_valid(self):
        graph = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
        colors = color_graph(graph)
        for var, reg in colors.items():
            assert reg in REGISTERS, f"{var} is allocated to an illegal regsiter {reg}"

    def test_too_many_interferences_raises(self):
        K = len(REGISTERS)
        nodes = [f"v{i}" for i in range(K + 1)]
        graph = {n: set(nodes) - {n} for n in nodes}
        with pytest.raises(RuntimeError, match="Register spilling required"):
            color_graph(graph)


class TestRewriteProgram:
    def _make_program(self, body: L0.Statement, params: list[str] = []) -> L0.Program:
        return L0.Program(procedures=[
            L0.Procedure(name="main", parameters=params, body=body)
        ])

    def test_halt_only(self):
        body = L0.Halt(value="x")
        prog = self._make_program(body, params=["x"])
        result = rewrite_program(prog)
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS), \
            f"Still have name(s) of register(s) after revising {vars_used - set(REGISTERS)}"

    def test_simple_linear(self):
        halt = L0.Halt(value="x")
        body = L0.Immediate(destination="x", value=1, then=halt)
        result = rewrite_program(self._make_program(body))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)

    def test_add_two_numbers(self):
        # imm x=3 → imm y=4 → prim z=x+y → halt(z)
        halt  = L0.Halt(value="z")
        prim  = L0.Primitive(destination="z", operator="+", left="x", right="y", then=halt)
        imm_y = L0.Immediate(destination="y", value=4, then=prim)
        imm_x = L0.Immediate(destination="x", value=3, then=imm_y)
        result = rewrite_program(self._make_program(imm_x))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)

    def test_branch_program(self):
        # imm a=1 → imm b=2 → branch(a<b) → halt(a) / halt(b)
        halt_a  = L0.Halt(value="a")
        halt_b  = L0.Halt(value="b")
        branch  = L0.Branch(operator="<", left="a", right="b",
                            then=halt_a, otherwise=halt_b)
        imm_b   = L0.Immediate(destination="b", value=2, then=branch)
        imm_a   = L0.Immediate(destination="a", value=1, then=imm_b)
        result  = rewrite_program(self._make_program(imm_a))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)

    def test_no_two_interfering_vars_share_register(self):
        # imm x=1 → imm y=2 → prim z=x+y → halt(z)
        halt  = L0.Halt(value="z")
        prim  = L0.Primitive(destination="z", operator="+", left="x", right="y", then=halt)
        imm_y = L0.Immediate(destination="y", value=2, then=prim)
        imm_x = L0.Immediate(destination="x", value=1, then=imm_y)
        result = rewrite_program(self._make_program(imm_x))

        proc = result.procedures[0]
        stmts = all_stmts_reachable(proc.body)
        prim_nodes = [s for s in stmts if isinstance(s, L0.Primitive)]
        assert prim_nodes, "Primitive nodes not found"
        p = prim_nodes[0]
        assert p.left != p.right, \
            f"x and y（active）are allocated to a same register {p.left}"

    def test_load_store_rewrite(self):
        # alloc p → store p[0]=v → load w=p[0] → halt(w)
        halt  = L0.Halt(value="w")
        load  = L0.Load(destination="w", base="p", index=0, then=halt)
        store = L0.Store(base="p", index=0, value="v", then=load)
        imm_v = L0.Immediate(destination="v", value=99, then=store)
        alloc = L0.Allocate(destination="p", count=1, then=imm_v)
        result = rewrite_program(self._make_program(alloc))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)

    def test_address_rewrite(self):
        # addr a=label → halt(a)
        halt = L0.Halt(value="a")
        addr = L0.Address(destination="a", name="my_label", then=halt)
        result = rewrite_program(self._make_program(addr))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)

    def test_call_rewrite(self):
        # imm x=1 → imm y=2 → call fn(x, y)
        call   = L0.Call(target="fn", arguments=["x", "y"])
        imm_y  = L0.Immediate(destination="y", value=2, then=call)
        imm_x  = L0.Immediate(destination="x", value=1, then=imm_y)
        result = rewrite_program(self._make_program(imm_x))
        proc = result.procedures[0]
        stmts = all_stmts_reachable(proc.body)
        calls = [s for s in stmts if isinstance(s, L0.Call)]
        assert calls
        c = calls[0]
        assert c.target in REGISTERS
        assert all(a in REGISTERS for a in c.arguments)

    def test_copy_rewrite(self):
        # imm x=5 → copy y=x → halt(y)
        halt = L0.Halt(value="y")
        copy = L0.Copy(destination="y", source="x", then=halt)
        imm  = L0.Immediate(destination="x", value=5, then=copy)
        result = rewrite_program(self._make_program(imm))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)

    def test_branch_distinct_halts(self):
        halt_t  = L0.Halt(value="a")
        halt_f  = L0.Halt(value="b")
        branch  = L0.Branch(operator="==", left="a", right="b",
                            then=halt_t, otherwise=halt_f)
        imm_b   = L0.Immediate(destination="b", value=2, then=branch)
        imm_a   = L0.Immediate(destination="a", value=1, then=imm_b)
        result  = rewrite_program(self._make_program(imm_a))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)


        halt   = L0.Halt(value="x")
        branch = L0.Branch(operator="<", left="x", right="y",
                           then=halt, otherwise=halt)
        imm_y  = L0.Immediate(destination="y", value=2, then=branch)
        imm_x  = L0.Immediate(destination="x", value=1, then=imm_y)
        result = rewrite_program(self._make_program(imm_x))
        vars_used = collect_vars(result)
        assert vars_used <= set(REGISTERS)


        halt1 = L0.Halt(value="x")
        body1 = L0.Immediate(destination="x", value=1, then=halt1)
        halt2 = L0.Halt(value="y")
        body2 = L0.Immediate(destination="y", value=2, then=halt2)
        prog = L0.Program(procedures=[
            L0.Procedure(name="proc1", parameters=[], body=body1),
            L0.Procedure(name="proc2", parameters=[], body=body2),
        ])
        result = rewrite_program(prog)
        assert len(result.procedures) == 2
        for proc in result.procedures:
            for s in all_stmts_reachable(proc.body):
                gen, kill = get_vars(s)
                for v in gen | kill:
                    assert v in REGISTERS, f"{proc.name} still has variable {v}"