import collections
from collections.abc import Callable

from L0 import syntax as L0

REGISTERS = ["rax", "rcx", "rdx", "rbx", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]
FreshFunc = Callable[[str], str]


def get_vars(stmt: L0.Statement) -> tuple[set[str], set[str]]:
    match stmt:
        case L0.Copy(destination=d, source=s):
            return {s}, {d}
        case L0.Immediate(destination=d):
            return set(), {d}
        case L0.Primitive(destination=d, left=l, right=r):
            return {l, r}, {d}
        case L0.Branch(left=l, right=r):
            return {l, r}, set()
        case L0.Allocate(destination=d):
            return set(), {d}
        case L0.Load(destination=d, base=b):
            return {b}, {d}
        case L0.Store(base=b, value=v):
            return {b, v}, set()
        case L0.Address(destination=d):
            return set(), {d}
        case L0.Call(target=t, arguments=args):
            return {t} | set(args), set()
        case L0.Halt(value=v):
            return {v}, set()


def get_successors(stmt: L0.Statement) -> list[L0.Statement]:
    match stmt:
        case L0.Branch(then=th, otherwise=ot):
            return [th, ot]
        case L0.Halt():
            return []
        case L0.Call():
            return []
        case (L0.Copy(then=t) | L0.Immediate(then=t) | L0.Primitive(then=t) |  # pragma: no branch
              L0.Allocate(then=t) | L0.Load(then=t) | L0.Store(then=t) |
              L0.Address(then=t)):
            return [t]
        case _:  # pragma: no cover
            return []


def _collect_all_stmts(body: L0.Statement) -> list[L0.Statement]:
    all_stmts: list[L0.Statement] = []
    stack = [body]
    visited: set[int] = set()
    while stack:
        s = stack.pop()
        if id(s) in visited:
            continue
        visited.add(id(s))
        all_stmts.append(s)
        stack.extend(get_successors(s))
    return all_stmts


def compute_liveness(body: L0.Statement) -> dict[int, set[str]]:
    all_stmts = _collect_all_stmts(body)

    live_in:  dict[int, set[str]] = {id(s): set() for s in all_stmts}
    live_out: dict[int, set[str]] = {id(s): set() for s in all_stmts}

    changed = True
    while changed:
        changed = False
        for s in reversed(all_stmts):
            gen, kill = get_vars(s)

            new_out: set[str] = set()
            for succ in get_successors(s):
                new_out |= live_in[id(succ)]

            new_in = gen | (new_out - kill)

            if new_in != live_in[id(s)] or new_out != live_out[id(s)]:
                live_in[id(s)]  = new_in
                live_out[id(s)] = new_out
                changed = True

    return live_out


def build_interference(
    body: L0.Statement,
    live_out: dict[int, set[str]],
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = collections.defaultdict(set[str])

    for s in _collect_all_stmts(body):
        gen, kill = get_vars(s)
        for v in gen | kill:
            if v not in graph:
                graph[v] = set()

        out = live_out[id(s)]
        for d in kill:
            for v in out:
                if d != v:
                    graph[d].add(v)
                    graph[v].add(d)

    return graph


def color_graph(graph: dict[str, set[str]]) -> dict[str, str]:
    K = len(REGISTERS)

    adj: dict[str, set[str]] = {n: set(neighbors) for n, neighbors in graph.items()}
    remaining = list(adj.keys())
    stack: list[str] = []

    while remaining:
        candidate = next((n for n in remaining if len(adj[n]) < K), None)

        if candidate is None:
            candidate = max(remaining, key=lambda n: len(adj[n]))

        stack.append(candidate)
        remaining.remove(candidate)
        for m in list(adj[candidate]):
            adj[m].discard(candidate)
        adj[candidate].clear()

    colors: dict[str, str] = {}
    while stack:
        n = stack.pop()
        used = {colors[m] for m in graph.get(n, set()) if m in colors}
        chosen = next((r for r in REGISTERS if r not in used), None)
        if chosen is None:
            raise RuntimeError(
                f"Register spilling required for '{n}': "
                f"no free register among {REGISTERS}"
            )
        colors[n] = chosen

    return colors


def rewrite_program(program: L0.Program) -> L0.Program:
    new_procs: list[L0.Procedure] = []

    for proc in program.procedures:
        live_out = compute_liveness(proc.body)
        graph    = build_interference(proc.body, live_out)
        colors   = color_graph(graph)

        def rename(v: str) -> str:
            return colors.get(v, v)

        walked: dict[int, L0.Statement] = {}

        def walk(s: L0.Statement) -> L0.Statement:
            if id(s) in walked:
                return walked[id(s)]

            result: L0.Statement
            match s:
                case L0.Copy(destination=d, source=src, then=t):
                    result = L0.Copy(
                        destination=rename(d),
                        source=rename(src),
                        then=walk(t),
                    )
                case L0.Immediate(destination=d, value=v, then=t):
                    result = L0.Immediate(
                        destination=rename(d),
                        value=v,
                        then=walk(t),
                    )
                case L0.Primitive(destination=d, operator=op, left=l, right=r, then=t):
                    result = L0.Primitive(
                        destination=rename(d),
                        operator=op,
                        left=rename(l),
                        right=rename(r),
                        then=walk(t),
                    )
                case L0.Branch(operator=op, left=l, right=r, then=th, otherwise=ot):
                    result = L0.Branch(
                        operator=op,
                        left=rename(l),
                        right=rename(r),
                        then=walk(th),
                        otherwise=walk(ot),
                    )
                case L0.Allocate(destination=d, count=cnt, then=t):
                    result = L0.Allocate(
                        destination=rename(d),
                        count=cnt,
                        then=walk(t),
                    )
                case L0.Load(destination=d, base=b, index=idx, then=t):
                    result = L0.Load(
                        destination=rename(d),
                        base=rename(b),
                        index=idx,
                        then=walk(t),
                    )
                case L0.Store(base=b, index=idx, value=v, then=t):
                    result = L0.Store(
                        base=rename(b),
                        index=idx,
                        value=rename(v),
                        then=walk(t),
                    )
                case L0.Address(destination=d, name=nm, then=t):
                    result = L0.Address(
                        destination=rename(d),
                        name=nm,
                        then=walk(t),
                    )
                case L0.Call(target=tgt, arguments=args):
                    result = L0.Call(
                        target=rename(tgt),
                        arguments=[rename(a) for a in args],
                    )
                case L0.Halt(value=v):
                    result = L0.Halt(value=rename(v))
                case _:  # pragma: no cover
                    raise ValueError(f"Unexpected statement: {s}")

            walked[id(s)] = result
            return result

        new_procs.append(L0.Procedure(
            name=proc.name,
            parameters=[rename(p) for p in proc.parameters],
            body=walk(proc.body),
        ))

    return L0.Program(procedures=new_procs)