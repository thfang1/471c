from collections.abc import Callable, Mapping, Sequence
from functools import partial

from L0 import syntax as L0

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

type Identifier = str
type Register   = str
type Graph      = Mapping[Identifier, frozenset[Identifier]]
type Coloring   = Mapping[Identifier, Register]

REGISTERS: tuple[Register, ...] = (
    "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
    "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
)


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------

def _gen(stmt: L0.Statement) -> frozenset[Identifier]:
    match stmt:
        case L0.Copy(source=src):
            return frozenset({src})
        case L0.Immediate():
            return frozenset()
        case L0.Primitive(left=l, right=r):
            return frozenset({l, r})
        case L0.Branch(left=l, right=r):
            return frozenset({l, r})
        case L0.Allocate():
            return frozenset()
        case L0.Load(base=b):
            return frozenset({b})
        case L0.Store(base=b, value=v):
            return frozenset({b, v})
        case L0.Address():
            return frozenset()
        case L0.Call(target=t, arguments=args):
            return frozenset({t, *args})
        case L0.Halt(value=v):  # pragma: no branch
            return frozenset({v})


def _kill(stmt: L0.Statement) -> frozenset[Identifier]:
    match stmt:
        case L0.Copy(destination=d):
            return frozenset({d})
        case L0.Immediate(destination=d):
            return frozenset({d})
        case L0.Primitive(destination=d):
            return frozenset({d})
        case L0.Branch():
            return frozenset()
        case L0.Allocate(destination=d):
            return frozenset({d})
        case L0.Load(destination=d):
            return frozenset({d})
        case L0.Store():
            return frozenset()
        case L0.Address(destination=d):
            return frozenset({d})
        case L0.Call():
            return frozenset()
        case L0.Halt():  # pragma: no branch
            return frozenset()


def _live_in(
    stmt: L0.Statement,
    live_out: frozenset[Identifier],
) -> frozenset[Identifier]:
    """in[i] = gen[i] ∪ (out[i] − kill[i])"""
    return _gen(stmt) | (live_out - _kill(stmt))


def _flatten(
    stmt: L0.Statement,
) -> tuple[list[L0.Statement], dict[int, list[int]]]:
    """
    Depth-first pre-order traversal of the statement tree.
    Returns (nodes, children) where children[i] holds the successor indices
    of nodes[i].
    """
    nodes:    list[L0.Statement]   = []
    children: dict[int, list[int]] = {}

    def walk(s: L0.Statement) -> int:
        idx = len(nodes)
        nodes.append(s)
        match s:
            case L0.Branch(then=th, otherwise=ot):
                children[idx] = [walk(th), walk(ot)]
            case (L0.Copy(then=t) | L0.Immediate(then=t) | L0.Primitive(then=t)
                  | L0.Allocate(then=t) | L0.Load(then=t) | L0.Store(then=t)
                  | L0.Address(then=t)):
                children[idx] = [walk(t)]
            case L0.Call():
                children[idx] = []
            case L0.Halt():  # pragma: no branch
                children[idx] = []
        return idx

    walk(stmt)
    return nodes, children


def compute_liveness(
    stmt: L0.Statement,
    live_at_end: frozenset[Identifier],
) -> tuple[Mapping[int, frozenset[Identifier]], Mapping[int, frozenset[Identifier]]]:
    """
    Compute in[i] and out[i] for every node in the statement tree via
    backward fixed-point iteration (equations 9.1 and 9.2 from the textbook).

    Terminals receive *live_at_end* as their out set.

    Returns (in_sets, out_sets) both indexed by pre-order position.
    """
    nodes, children = _flatten(stmt)
    n = len(nodes)

    out: dict[int, frozenset[Identifier]] = {
        i: (live_at_end if not children[i] else frozenset())
        for i in range(n)
    }

    changed = True
    while changed:
        changed = False
        for i in reversed(range(n)):
            if not children[i]:
                continue
            new_out: frozenset[Identifier] = frozenset(
                v
                for j in children[i]
                for v in _live_in(nodes[j], out[j])
            )
            if new_out != out[i]:
                out[i] = new_out
                changed = True

    in_sets: dict[int, frozenset[Identifier]] = {
        i: _live_in(nodes[i], out[i]) for i in range(n)
    }

    return in_sets, out


# ---------------------------------------------------------------------------
# Interference graph
# ---------------------------------------------------------------------------

def _add_edge(
    graph: dict[Identifier, set[Identifier]],
    x: Identifier,
    y: Identifier,
) -> None:
    graph.setdefault(x, set()).add(y)
    graph.setdefault(y, set()).add(x)


def build_interference(
    stmt: L0.Statement,
    live_at_end: frozenset[Identifier],
) -> Graph:
    """
    Build the interference graph for a procedure body.

    Definition 9.2: x interferes with y when
        x ∈ kill[i],  y ∈ out[i],  x ≠ y,
        and the instruction is not a plain copy  x := y.
    """
    nodes, _ = _flatten(stmt)
    _, out_sets  = compute_liveness(stmt, live_at_end)

    graph: dict[Identifier, set[Identifier]] = {}

    for s in nodes:
        for v in _gen(s) | _kill(s):
            graph.setdefault(v, set())

    for i, s in enumerate(nodes):
        is_copy = isinstance(s, L0.Copy)
        for x in _kill(s):
            for y in out_sets[i]:
                if x == y:
                    continue
                if is_copy and y == s.source:  # type: ignore[union-attr]
                    continue
                _add_edge(graph, x, y)

    return {v: frozenset(nbrs) for v, nbrs in graph.items()}


# ---------------------------------------------------------------------------
# Graph colouring  (Algorithm 9.3)
# ---------------------------------------------------------------------------

def color_graph(
    graph: Graph,
    registers: Sequence[Register],
    precolored: Coloring,
) -> tuple[Coloring, frozenset[Identifier]]:
    """
    Optimistic graph colouring (Algorithm 9.3).

    simplify: repeatedly remove a node with < N edges (or, if none exists,
              the node with the most edges as a spill candidate — §9.7).
    select:   re-insert nodes from the stack, assigning the lowest available
              register; mark as spilled if none is available.

    Precolored nodes are never removed during simplify.
    """
    n = len(registers)

    remaining: dict[Identifier, set[Identifier]] = {
        v: set(nbrs) for v, nbrs in graph.items()
    }
    stack: list[tuple[Identifier, frozenset[Identifier]]] = []

    # ---- simplify ----
    while True:
        candidates = [v for v in remaining if v not in precolored]
        if not candidates:
            break

        chosen = next(
            (v for v in candidates if len(remaining[v]) < n),
            max(candidates, key=lambda v: len(remaining[v])),
        )

        nbrs = frozenset(remaining.pop(chosen))
        stack.append((chosen, nbrs))
        for nb in nbrs:
            remaining[nb].discard(chosen)

    # ---- select ----
    coloring: dict[Identifier, Register] = dict(precolored)
    spilled:  set[Identifier]            = set()

    for v, nbrs in reversed(stack):
        used      = frozenset(coloring[nb] for nb in nbrs if nb in coloring)
        available = [r for r in registers if r not in used]
        if available:
            coloring[v] = available[0]
        else:
            spilled.add(v)

    return coloring, frozenset(spilled)


# ---------------------------------------------------------------------------
# Spill rewriting
# ---------------------------------------------------------------------------

def _rewrite_spills_stmt(
    stmt: L0.Statement,
    slots: Mapping[Identifier, Identifier],
    fresh: Callable[[str], str],
) -> L0.Statement:
    """
    Rewrite *stmt* so that every read/write of a spilled variable goes
    through its heap-allocated slot pointer.
    """
    recur = partial(_rewrite_spills_stmt, slots=slots, fresh=fresh)

    def load_if_spilled(
        name: Identifier,
    ) -> tuple[Identifier, Callable[[L0.Statement], L0.Statement]]:
        """Return (local_name, wrap) where wrap injects a Load if name is spilled."""
        if name in slots:
            tmp = fresh(name)
            return tmp, lambda cont: L0.Load(destination=tmp, base=slots[name], index=0, then=cont)
        return name, lambda cont: cont

    match stmt:
        case L0.Copy(destination=d, source=src, then=t):
            src_name, wrap_src = load_if_spilled(src)
            if d in slots:
                tmp_d = fresh(d)
                return wrap_src(
                    L0.Copy(destination=tmp_d, source=src_name,
                             then=L0.Store(base=slots[d], index=0, value=tmp_d,
                                           then=recur(t)))
                )
            return wrap_src(L0.Copy(destination=d, source=src_name, then=recur(t)))

        case L0.Immediate(destination=d, value=v, then=t):
            if d in slots:
                tmp = fresh(d)
                return L0.Immediate(
                    destination=tmp, value=v,
                    then=L0.Store(base=slots[d], index=0, value=tmp, then=recur(t)))
            return L0.Immediate(destination=d, value=v, then=recur(t))

        case L0.Primitive(destination=d, operator=op, left=l, right=r, then=t):
            l_name, wrap_l = load_if_spilled(l)
            r_name, wrap_r = load_if_spilled(r)
            if d in slots:
                tmp_d = fresh(d)
                core: L0.Statement = L0.Primitive(
                    destination=tmp_d, operator=op, left=l_name, right=r_name,
                    then=L0.Store(base=slots[d], index=0, value=tmp_d, then=recur(t)))
            else:
                core = L0.Primitive(
                    destination=d, operator=op, left=l_name, right=r_name, then=recur(t))
            return wrap_l(wrap_r(core))

        case L0.Branch(operator=op, left=l, right=r, then=th, otherwise=ot):
            l_name, wrap_l = load_if_spilled(l)
            r_name, wrap_r = load_if_spilled(r)
            core = L0.Branch(
                operator=op, left=l_name, right=r_name,
                then=recur(th), otherwise=recur(ot))
            return wrap_l(wrap_r(core))

        case L0.Allocate(destination=d, count=c, then=t):
            if d in slots:
                tmp = fresh(d)
                return L0.Allocate(
                    destination=tmp, count=c,
                    then=L0.Store(base=slots[d], index=0, value=tmp, then=recur(t)))
            return L0.Allocate(destination=d, count=c, then=recur(t))

        case L0.Load(destination=d, base=b, index=i, then=t):
            b_name, wrap_b = load_if_spilled(b)
            if d in slots:
                tmp = fresh(d)
                core = L0.Load(
                    destination=tmp, base=b_name, index=i,
                    then=L0.Store(base=slots[d], index=0, value=tmp, then=recur(t)))
            else:
                core = L0.Load(destination=d, base=b_name, index=i, then=recur(t))
            return wrap_b(core)

        case L0.Store(base=b, index=i, value=v, then=t):
            b_name, wrap_b = load_if_spilled(b)
            v_name, wrap_v = load_if_spilled(v)
            return wrap_b(wrap_v(
                L0.Store(base=b_name, index=i, value=v_name, then=recur(t))
            ))

        case L0.Address(destination=d, name=nm, then=t):
            if d in slots:
                tmp = fresh(d)
                return L0.Address(
                    destination=tmp, name=nm,
                    then=L0.Store(base=slots[d], index=0, value=tmp, then=recur(t)))
            return L0.Address(destination=d, name=nm, then=recur(t))

        case L0.Call(target=tg, arguments=args):
            tg_name, wrap_tg = load_if_spilled(tg)
            pairs = [load_if_spilled(a) for a in args]
            arg_names = [name for name, _ in pairs]
            core = L0.Call(target=tg_name, arguments=arg_names)
            for _, wrap in reversed(pairs):
                core = wrap(core)
            return wrap_tg(core)

        case L0.Halt(value=v):  # pragma: no branch
            v_name, wrap_v = load_if_spilled(v)
            return wrap_v(L0.Halt(value=v_name))


def rewrite_spills(
    procedure: L0.Procedure,
    spilled: frozenset[Identifier],
    fresh: Callable[[str], str],
) -> L0.Procedure:
    """
    Allocate a heap slot for every spilled variable and rewrite the
    procedure body to load/store through those slots.
    """
    slots: dict[Identifier, Identifier] = {
        x: fresh(f"_slot_{x}") for x in sorted(spilled)
    }
    new_body = _rewrite_spills_stmt(procedure.body, slots, fresh)

    for x in sorted(spilled, reverse=True):
        new_body = L0.Allocate(destination=slots[x], count=1, then=new_body)

    return L0.Procedure(
        name=procedure.name,
        parameters=procedure.parameters,
        body=new_body,
    )


# ---------------------------------------------------------------------------
# Apply allocation
# ---------------------------------------------------------------------------

def apply_allocation(
    procedure: L0.Procedure,
    coloring: Coloring,
) -> L0.Procedure:
    """Rename every identifier in the procedure body to its assigned register."""
    def r(name: Identifier) -> Register:
        return coloring.get(name, name)

    def rewrite(stmt: L0.Statement) -> L0.Statement:
        match stmt:
            case L0.Copy(destination=d, source=src, then=t):
                return L0.Copy(destination=r(d), source=r(src), then=rewrite(t))
            case L0.Immediate(destination=d, value=v, then=t):
                return L0.Immediate(destination=r(d), value=v, then=rewrite(t))
            case L0.Primitive(destination=d, operator=op, left=l, right=ri, then=t):
                return L0.Primitive(
                    destination=r(d), operator=op, left=r(l), right=r(ri), then=rewrite(t))
            case L0.Branch(operator=op, left=l, right=ri, then=th, otherwise=ot):
                return L0.Branch(
                    operator=op, left=r(l), right=r(ri),
                    then=rewrite(th), otherwise=rewrite(ot))
            case L0.Allocate(destination=d, count=c, then=t):
                return L0.Allocate(destination=r(d), count=c, then=rewrite(t))
            case L0.Load(destination=d, base=b, index=i, then=t):
                return L0.Load(destination=r(d), base=r(b), index=i, then=rewrite(t))
            case L0.Store(base=b, index=i, value=v, then=t):
                return L0.Store(base=r(b), index=i, value=r(v), then=rewrite(t))
            case L0.Address(destination=d, name=nm, then=t):
                return L0.Address(destination=r(d), name=nm, then=rewrite(t))
            case L0.Call(target=tg, arguments=args):
                return L0.Call(target=r(tg), arguments=[r(a) for a in args])
            case L0.Halt(value=v):  # pragma: no branch
                return L0.Halt(value=r(v))

    return L0.Procedure(
        name=procedure.name,
        parameters=[r(p) for p in procedure.parameters],
        body=rewrite(procedure.body),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_names(stmt: L0.Statement) -> set[Identifier]:
    acc: set[Identifier] = set()

    def walk(s: L0.Statement) -> None:
        match s:
            case L0.Copy(destination=d, source=src, then=t):
                acc.update([d, src]); walk(t)
            case L0.Immediate(destination=d, then=t):
                acc.add(d); walk(t)
            case L0.Primitive(destination=d, left=l, right=r, then=t):
                acc.update([d, l, r]); walk(t)
            case L0.Branch(left=l, right=r, then=th, otherwise=ot):
                acc.update([l, r]); walk(th); walk(ot)
            case L0.Allocate(destination=d, then=t):
                acc.add(d); walk(t)
            case L0.Load(destination=d, base=b, then=t):
                acc.update([d, b]); walk(t)
            case L0.Store(base=b, value=v, then=t):
                acc.update([b, v]); walk(t)
            case L0.Address(destination=d, then=t):
                acc.add(d); walk(t)
            case L0.Call(target=tg, arguments=args):
                acc.update([tg, *args])
            case L0.Halt(value=v):  # pragma: no branch
                acc.add(v)

    walk(stmt)
    return acc


def _make_fresh(existing: set[Identifier]) -> Callable[[str], str]:
    counters: dict[str, int] = {}

    def fresh(hint: str) -> str:
        i = counters.get(hint, 0)
        while True:
            name = f"{hint}_{i}"
            i += 1
            if name not in existing:
                counters[hint] = i
                existing.add(name)
                return name

    return fresh


# ---------------------------------------------------------------------------
# Procedure and program entry points
# ---------------------------------------------------------------------------

def allocate_procedure(
    procedure: L0.Procedure,
    registers: Sequence[Register],
) -> L0.Procedure:
    """
    Full register-allocation pipeline for a single L0 Procedure.

    Iterates: liveness → interference → colouring → spill-rewrite
    until no variables remain spilled.

    Procedure parameters are pre-colored to registers[0..k-1],
    matching the calling convention (arguments arrive in r0, r1, …).

    Spill-slot pointer variables (injected by rewrite_spills) are tracked in
    *protected* so they are never chosen for spilling again, which would
    otherwise cause unbounded slot-of-slot recursion.
    """
    existing  = _all_names(procedure.body) | set(procedure.parameters)
    fresh     = _make_fresh(existing)
    current   = procedure
    protected : set[Identifier] = set()

    while True:
        precolored: dict[Identifier, Register] = {
            param: registers[i]
            for i, param in enumerate(current.parameters)
            if i < len(registers)
        }

        all_protected = frozenset(protected) | frozenset(precolored.keys())
        graph             = build_interference(current.body, all_protected)
        coloring, spilled = color_graph(graph, registers, precolored)

        # never spill slot pointers or parameters
        spilled = frozenset(v for v in spilled if v not in protected)

        if not spilled:
            return apply_allocation(current, coloring)

        current = rewrite_spills(current, spilled, fresh)
        # after rewriting, protect every slot pointer so it is never spilled
        protected |= {name for name in _all_names(current.body)
                      if name.startswith("_slot_")}


def allocate_program(
    program: L0.Program,
    registers: Sequence[Register],
) -> L0.Program:
    """Apply register allocation to every Procedure in an L0 Program."""
    _allocate = partial(allocate_procedure, registers=registers)
    return L0.Program(procedures=[_allocate(proc) for proc in program.procedures])