"""Teste do LarkAG (lark-ag 1.0.2) para a Fase 0 da Parte II.
Uso: pip install --no-deps lark-ag==1.0.2 ; python experimentos/larkag/spike_larkag.py"""
from lark_ag import Lark_AG
from lark_ag.generator_layer import GeneratorLayer

BASE = r'''
SA(start){ ok : bool }
SA(program){ ok : bool }
SA(decllist){ decls : dict }
IA(decllist){ env : dict }
SA(decl){ decls : dict }
IA(decl){ env : dict }
SA(expr){ type : str }
IA(expr){ env : dict }
SA(atom){ type : str }
IA(atom){ env : dict }

start: program ER{ start.ok = program.ok; }

program: "home" "{" decllist "}"
    ER{ program.ok = decllist.decls is not None; decllist.env = %ENV%; }

decllist: decl decllist
    ER{ decllist[1].decls = {**decllist[2].decls, **decl.decls}; decl.env = decllist[1].env; decllist[2].env = %ENV2%; }
  | ER{ decllist.decls = {}; }

decl: "var" ID ":" TYPE "=" expr ";"
    ER{ decl.decls = (lambda t: {str(ID): t})(expr.type); expr.env = decl.env; }
    CC{ (lambda t: expr.type == t or (t == "real" and expr.type == "int"))(str(TYPE)) -> "typeMismatch"; }

expr: expr "+" atom
    ER{ expr[1].type = "real" if "real" in (expr[2].type, atom.type) else "int"; expr[2].env = expr[1].env; atom.env = expr[1].env; }
  | atom
    ER{ expr.type = atom.type; atom.env = expr.env; }

atom: INT  ER{ atom.type = "int"; }
    | REAL ER{ atom.type = "real"; }
    | ID   ER{ atom.type = atom.env.get(str(ID), "undeclared"); }
    CC{ str(ID) in atom.env -> "undeclared"; }

TYPE: "int" | "real"
ID: /[a-z][a-z0-9]*/
REAL: /[0-9]+\.[0-9]+/
INT: /[0-9]+/
'''
# Nota: decl.decls usa expr.type só para forçar a visita de expr antes de expr.env (ver relatório).

VARIANTES = {
    "L-atribuída (blocos do Domo: env da esquerda p/ direita)":
        BASE.replace("%ENV%", "{}").replace("%ENV2%", "{**decllist[1].env, **decl.decls}"),
    "Não L-atribuída (zonas do Domo: env = decls do próprio nó)":
        BASE.replace("%ENV%", "decllist.decls").replace("%ENV2%", "decllist[1].env"),
}

CASOS = {
    "ordem normal":           ('home { var a : int = 1; var b : int = a + 2; }', "ok"),
    "usar antes de declarar": ('home { var b : int = a + 2; var a : int = 1; }', "ok nas zonas, undeclared nos blocos"),
    "typeMismatch":           ('home { var a : int = 1.5; }', "typeMismatch"),
    "dois erros":             ('home { var a : int = 1.5; var b : int = zz; }', "typeMismatch + undeclared"),
    "erro de sintaxe":        ('home { var a int = 1; }', "erro com linha/coluna"),
}

for nome, ag_text in VARIANTES.items():
    print(f"\n=== {nome} ===")
    ag = Lark_AG(ag_text)
    for caso, (src, esperado) in CASOS.items():
        try:
            ag.process(src)
            res = "OK"
        except Exception as e:
            res = f"{type(e).__name__}: {str(e).splitlines()[0][:70]}"
        print(f"  {caso:<24} esperado: {esperado:<36} obtido: {res}")
    code = GeneratorLayer(ag_text).getInterpreterFile()
    print("  -- código gerado para program:")
    print("    " + code[code.index("def program_0"):code.index("def decllist_0")].strip().replace("\n", "\n    "))

# --- Compatibilidade com a sintaxe usada em domo.lark ---
print("\n=== Sintaxe do Lark usada em domo.lark ===")
mini = 'SA(start){ v : int }\nstart: %s\n%s\nINT: /[0-9]+/\n'
sintaxe = {
    "?regra (colapsar nós)":   mini % ('x ER{ start.v = x.v; }', 'SA(x){ v : int }\n?x: INT ER{ x.v = 1; }'),
    "_regra (fundir no pai)":  mini % ('_x ER{ start.v = 1; }', '_x: INT ER{ }'),
    "-> alias":                mini % ('INT -> lit ER{ start.v = 1; }', ''),
    "alternativa sem ER{}":    mini % ('INT', ''),
}
for n, g in sintaxe.items():
    try:
        Lark_AG(g); print(f"  {n:<24} aceite")
    except Exception as e:
        print(f"  {n:<24} rejeitado ({type(e).__name__})")

print("\n=== Nomes de regra com '_' (zone_decl, var_decl, and_expr, ...) ===")
ren = VARIANTES[next(iter(VARIANTES))].replace("decllist", "decl_list")
try:
    Lark_AG(ren).process(CASOS["ordem normal"][0]); print("  OK")
except Exception as e:
    print(f"  falha: {type(e).__name__}: {e}")

p = Lark_AG(VARIANTES[next(iter(VARIANTES))]).processor.parser
print("\n=== Parser gerado ===")
print(f"  parser={p.options.parser} lexer={p.options.lexer} propagate_positions={p.options.propagate_positions}")
