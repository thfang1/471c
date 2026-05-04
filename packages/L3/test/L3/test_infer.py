from typing import Any, Optional

import pytest
from L3.infer import BLOCK, INT, Counter, FuncType, Substitution, Type, IntType, BlockType
from L3.infer import TypeVar as InferTypeVar
from L3.infer import generalize, infer_program, unify
from L3.syntax import (Abstract, Allocate, Apply, Begin, Branch, Immediate,
                       Let, Load, Primitive, Program, Reference, Store)

def test_type_definitions_coverage():
    # 強制觸發 IntType 的完整生命週期
    i1 = IntType()
    i2 = IntType()
    assert i1 == i2        # 觸發 __eq__
    assert str(i1) == "Int" # 觸發 __str__
    
    # 強制觸發 BlockType 的完整生命週期
    b1 = BlockType()
    b2 = BlockType()
    assert b1 == b2          # 觸發 __eq__
    assert str(b1) == "Block" # 觸發 __str__

# 輔助：手動構造 Program 的快速方法
def check_prog(body: Any, params: Optional[list[str]] = None) -> Type:
    # 如果 params 為 None，則使用空列表
    return infer_program(Program(parameters=params if params is not None else [], body=body))

# 1. 覆蓋基礎類型與 __str__ (解決 14, 18, 24, 31, 33 行)
def test_coverage_strings_and_counter():
    assert str(INT) == "Int"
    assert str(BLOCK) == "Block"
    f = FuncType(params=(INT,), ret=INT)
    assert "(Int) -> Int" in str(f)
    assert "α" in str(InferTypeVar(id=0))
    assert "τ150" in str(InferTypeVar(id=150))
    # 覆蓋 Counter (解決 113 行)
    c = Counter()
    assert c.n == 0
    c.fresh()
    assert c.n == 1

# 2. 覆蓋所有語法節點 (解決 158 - 216 行)
def test_coverage_all_syntax_nodes():
    # Immediate & Reference (159, 161)
    assert check_prog(Immediate(value=1)) == INT
    assert check_prog(Reference(name="x"), params=["x"]) == INT

    # Primitive (165)
    assert check_prog(Primitive(operator="+", left=Immediate(value=1), right=Immediate(value=2))) == INT

    # Abstract & Apply (171, 177)
    # (lambda (x) x) 1
    lam = Abstract(parameters=["x"], body=Reference(name="x"))
    app = Apply(target=lam, arguments=[Immediate(value=1)])
    assert check_prog(app) == INT

    # Let (185)
    # let x = 1 in x
    let = Let(bindings=[("x", Immediate(value=1))], body=Reference(name="x"))
    assert check_prog(let) == INT

    # Branch (192)
    # if (< 1 2) 10 20
    br = Branch(operator="<", left=Immediate(value=1), right=Immediate(value=2),
                consequent=Immediate(value=10), otherwise=Immediate(value=20))
    assert check_prog(br) == INT

    # Memory: Allocate, Load, Store (201, 203, 208)
    # let b = allocate in (begin (store b 0 1) (load b 0))
    mem_logic = Let(
        bindings=[("b", Allocate(count=1))],
        body=Begin(
            effects=[Store(base=Reference(name="b"), index=0, value=Immediate(value=1))],
            value=Load(base=Reference(name="b"), index=0)
        )
    )
    assert check_prog(mem_logic) == INT

# 3. 覆蓋 Unification & Errors (解決 65, 69, 82, 91 行)
def test_coverage_errors_and_unify():
    # Unify symmetry (69) - 將 TypeVar 放在右邊觸發交換
    sub: Substitution = {}
    tv = InferTypeVar(id=50)
    new_sub = unify(INT, tv, sub)
    assert new_sub[50] == INT

    # Infinite Type / Occurs Check (65)
    v = InferTypeVar(id=99)
    f_rec = FuncType(params=(v,), ret=INT)
    with pytest.raises(TypeError, match="Infinite type"):
        unify(v, f_rec, {})

    # Arity Mismatch (82)
    # 傳入 2 個參數給只要 1 個參數的 lambda
    with pytest.raises(TypeError, match="Arity mismatch"):
        check_prog(Apply(target=Abstract(parameters=["x"], body=Reference(name="x")), 
                         arguments=[Immediate(value=1), Immediate(value=2)]))

    # Type Mismatch (91)
    with pytest.raises(TypeError, match="Type mismatch"):
        unify(INT, FuncType(params=(), ret=INT), {})

    # Unbound Variable (162)
    with pytest.raises(TypeError, match="Unbound"):
        check_prog(Reference(name="missing"))

# 4. 覆蓋 NotImplementedError (218)

# 1. 擊破 Line 214 & 218: 測試 Begin 與 NotImplementedError
def test_begin_and_unhandled():
    # 先建立一個完全正常的程式
    prog = Program(parameters=[], body=Immediate(value=1))
    
    # 使用 object.__setattr__ 繞過 Pydantic 的 Frozen 限制與型別檢查
    # 這樣 Program 建立成功了，但在執行 infer_term(prog.body) 時會觸發 default case
    object.__setattr__(prog, 'body', "Not A Term Object")
    
    with pytest.raises(NotImplementedError):
        infer_program(prog)

# 2. 擊破 Line 121, 123, 140: 測試複雜的 Generalization
def test_complex_generalization():
    # 直接手動構造 syntax 物件，完全不依賴 parse_program 或字串解析
    # 代表程式: (program (p) (let ((f (lambda (x y) (+ x y)))) (f p 1)))
    
    f_body = Primitive(operator="+", left=Reference(name="x"), right=Reference(name="y"))
    f_def = Abstract(parameters=["x", "y"], body=f_body)
    
    body_logic = Apply(
        target=Reference(name="f"), 
        arguments=[Reference(name="p"), Immediate(value=1)]
    )
    
    full_body = Let(
        bindings=[("f", f_def)],
        body=body_logic
    )
    
    # 建立 Program (參數 p 會被加入環境中，讓 env.values() 不為空，覆蓋 Line 140)
    prog = Program(parameters=["p"], body=full_body)
    
    # 執行推理 (這會跑過 generalize 裡面的所有迴圈和分支)
    assert infer_program(prog) == INT

# 3. 擊破 Line 113: 確保 Counter 被正確初始化 (雖然是 153 行中的一部分)
def test_counter_coverage():
    c = Counter()
    # 這裡確保 __init__ 被完整執行
    assert c.n == 0
    assert isinstance(c.fresh(), InferTypeVar)

# 4. 擊破 Line 162: Unbound Variable 的錯誤出口
def test_unbound_exit_coverage():
    # 確保當 Reference 失敗時，會 raise 並且不流向後面的邏輯
    with pytest.raises(TypeError, match="Unbound"):
        infer_program(Program(parameters=[], body=Reference(name="missing")))

# 5. 擊破 Line 14 & 18: 解決 __str__ 遺漏
def test_str_coverage():
    # 有時候只寫 assert a == b 不會呼叫 __str__
    # 我們手動 print 或是轉字串
    assert str(INT) == "Int"
    assert str(BLOCK) == "Block"
    # 測試一個帶有 TypeVar 的 FuncType
    tv = InferTypeVar(id=0)
    ft = FuncType(params=(tv,), ret=INT)
    assert "α" in str(ft)

# 1. 狙擊 Unify 的相等性與對稱性 (解決 58 -> exit, 69 -> 74)
def test_unify_identity_and_symmetry():
    sub: Substitution = {}
    # 擊破 Line 58: 讓 t1 == t2
    assert unify(INT, INT, sub) == sub
    
    # 擊破 Line 69: 讓左邊是具體型別，右邊是 TypeVar (強制執行交換)
    tv = InferTypeVar(id=888)
    res = unify(INT, tv, sub)
    assert res[888] == INT

# 2. 狙擊 Occurs 與 Free Vars 的 False 路徑 (解決 100 -> 107, 121 -> 122)


# 3. 狙擊 Begin 的循環與 Reference 成功出口 (解決 162, 214)
def test_syntax_full_traversal():
    # 擊破 Line 214: 確保 Begin 裡面有 effects (原本可能是空的)
    # 擊破 Line 162: 確保 Reference 成功找到變數後的出口
    prog = Program(parameters=["a"], body=Begin(
        effects=[Primitive(operator="+", left=Reference(name="a"), right=Immediate(value=1))],
        value=Reference(name="a")
    ))
    # 這會讓 Reference 走進成功的 case，並且讓 Begin 跑過 for 迴圈
    from L3.infer import infer_program
    assert infer_program(prog) == INT

# 4. 擊破最後的 __str__ 盲區 (解決 14, 18, 31, 33)
def test_fix_str_coverage():
    # 有時候 assert 相等不會呼叫到 __str__，我們強制轉字串
    assert "Int" in str(INT)
    assert "Block" in str(BLOCK)
    # 測試多種 TypeVar 名稱
    assert "α" in str(InferTypeVar(id=0))
    assert "τ150" in str(InferTypeVar(id=150))
    # 測試 FuncType 的字串化
    f = FuncType(params=(INT,), ret=INT)
    assert "-> Int" in str(f)
    f = FuncType(params=(INT,), ret=INT)
    assert "-> Int" in str(f)

def test_case():
    # 1. 擊破 Line 113: 獨立測試 Counter
    c = Counter()
    assert c.n == 0
    
    # 2. 擊破 Line 121: free_in_type 處理孤立 TypeVar
    tv = InferTypeVar(id=999)
    res_scheme = generalize({}, tv, {})
    assert 999 in res_scheme.quantified

    # 3. 擊破 Line 162: 成功的 Reference 出口 (False path)
    prog_ok = Program(parameters=["ok_var"], body=Reference(name="ok_var"))
    assert infer_program(prog_ok) == INT

    # 4. 擊破 Line 14, 18: 強制執行 __str__ (轉字串才會跑過那兩行)
    assert str(INT) == "Int"
    assert str(BLOCK) == "Block"

    # 5. 修正 test_case: 
    # 與其傳入垃圾資料，不如直接針對 unify 的最後一公分測試
    # 測一個「兩個具體型別不匹配」的情況，這絕對會噴 TypeError (Line 91)
    with pytest.raises(TypeError, match="Type mismatch"):
        unify(INT, BLOCK, {})

def test_the_final_victory():
    # 1. 擊破 Line 113: 強制檢查 Counter 的初始值
    c = Counter()
    assert c.n == 0
    
    # 2. 擊破 Line 162: 確保一個「最單純且成功」的變數查找
    # 這個測試必須存在，且不能被其他 raise 影響
    prog_ok = Program(parameters=["p"], body=Reference(name="p"))
    assert infer_program(prog_ok) == INT

    # 3. 擊破 Line 14, 18: 確保字串化邏輯徹底執行到 exit
    # 有時候 assert 會中途停止，我們強制賦值
    s_int = str(INT)
    s_block = str(BLOCK)
    assert s_int == "Int"
    assert s_block == "Block"

    # 4. 擊破 Line 226: 傳入一個會讓 match 失敗的東西
    # 即使型別檢查器會抗議，但為了 Coverage 我們必須這樣做



    # 5. 擊破可能的 Unify 遺漏: 測試一個空的 Substitution 查找
    from L3.infer import apply_sub
    tv = InferTypeVar(id=888)
    assert apply_sub({}, tv) == tv

