#!/usr/bin/env python3
"""Bateria de testes léxicos, sintáticos e semânticos. Uso: python testes.py"""
import logging
from pathlib import Path

from analisador import build_parser, lexical_analysis, syntactic_analysis
from semantic import SemanticAnalyzer

OK, LEX, SYN, SEM = "OK", "LEX", "SYN", "SEM"

def prog(body: str) -> str:
    return f'home "t" {{ {body} }}'

def stm(body: str) -> str:
    return prog(f"scene S {{ {body} }}")

CASOS = [
    ("programa vazio",                       prog(""), OK),
    ("zonas aninhadas",                      prog("zone A { zone B { zone C { device d : light; } } }"), OK),
    ("if sem parênteses",                    prog("var a : bool = true; scene S { if a { } }"), OK),
    ("else if encadeado",                    prog("var a : bool = true; var b : bool = false; scene S { if a { } else if b { } else { } }"), OK),
    ("menos unário e binário",               prog("const a : int = 1 - -2;"), OK),
    ("precedência not/and/or",               prog("const x : bool = true; const y : bool = false; const z : bool = true; const a : bool = not x and y or z;"), OK),
    ("comparação com TIME e now",            stm("if now >= 07:30 { }"), OK),
    ("repeat com expressão",                 prog("const n : int = 2; scene S { repeat n + 1 times { } }"), OK),
    ("comentário no fim da linha",           'home "t" {\n  const a : int = 1; // comentário\n}', OK),
    ("comando sem argumentos",               prog("device lamp : light; scene S { lamp.turn_on(); }"), OK),
    ("comando com argumentos",               prog("device lamp : dimmer; scene S { lamp.fade_to(50); }"), OK),
    ("regra mínima",                         prog("rule R on at 22:30 { }"), OK),
    ("regra com todas as partes",            prog("var a : bool = true; rule R priority 3 on every 5 min when a { }"), OK),
    ("operadores * / != <=",                 prog("const a : real = 2 * 3 / 1; const b : bool = 1 != 2; const c : bool = 1 <= 2;"), OK),
    ("tipo string e unidades sec/hour",      prog('const s : string = "x"; rule R on every 30 sec { wait 1 hour; }'), OK),
    ("unidade como parte de nome (minimo)",  prog("var minimo : int = 0;"), OK),
    ("prefixo de keyword como ID (iffy)",    prog("var iffy : int = 0;"), OK),

    ("SEM: dispositivo inexistente",         stm("Living.sofa.turn_on();"), SEM),
    ("SEM: atribuir a const",                prog("const c : real = 1.0; scene S { c = 22.0; }"), SEM),
    ("SEM: repeat com string",               stm('repeat "tres" times { }'), SEM),
    ("SEM: activate de regra",               prog("rule Heat on at 10:00 {} scene S { activate Heat; }"), SEM),
    ("SEM: tipo errado na atribuição",       prog("device lamp : dimmer; scene S { lamp.brightness = \"alto\"; }"), SEM),
    ("SEM: escrita em propriedade read-only",prog("device lamp : light; scene S { lamp.power = true; }"), SEM),
    ("SEM: identificador duplicado",         prog("device lamp : light; device lamp : dimmer;"), SEM),
    ("SEM: tipo de dispositivo desconhecido",prog("device x : termometro;"), SEM),
    ("SEM: hora com valor impossivel",       prog("rule R on at 25:99 { }"), SEM),
    ("SEM: every com valor 0",               prog("rule R on every 0 min { }"), SEM),
    ("SEM: condicao de if nao booleana",     prog("device lamp : dimmer; scene S { if lamp.brightness { } }"), SEM),

    ("LEX: carácter ilegal @",               prog("const a : int = 1 @ 2;"), LEX),
    ("LEX: string por fechar",               prog('scene S { notify "olá; }'), LEX),
    ("LEX: carácter ilegal #",               prog("# isto não é comentário"), LEX),

    ("SYN: falta ponto e vírgula",           prog("device a : b"), SYN),
    ("SYN: falta dois pontos no device",     prog("device a b;"), SYN),
    ("SYN: comparação encadeada",            prog("const a : bool = 1 < 2 < 3;"), SYN),
    ("SYN: if sem chavetas",                 stm("if a wait 1 sec;"), SYN),
    ("SYN: else solto",                      stm("else { }"), SYN),
    ("SYN: falta home { }",                  "device a : b;", SYN),
    ("SYN: chaveta por fechar",              prog("zone A { ").rsplit("}", 1)[0], SYN),
    ("SYN: regra sem evento",                prog("rule R on { }"), SYN),
    ("SYN: priority sem número",             prog("rule R priority on at 10:00 { }"), SYN),
    ("SYN: every sem número",                prog("rule R on every min { }"), SYN),
    ("SYN: wait sem unidade",                stm("wait 5;"), SYN),
    ("SYN: cena com parênteses",             prog("scene S() { }"), SYN),
    ("SYN: grupo vazio",                     prog("group g = [];"), SYN),
    ("SYN: instrução fora de bloco",         prog("notify \"x\";"), SYN),
    ("SYN: TIME mal formado (22:3)",         prog("rule R on at 22:3 { }"), SYN),
    ("SYN: palavra reservada como ID (min)", prog("var min : int = 0;"), SYN),
    ("SYN: palavra reservada como ID (in)",  prog("device in : lamp;"), SYN),
    ("SYN: comentário de bloco não existe", prog("/* x */ const a : int = 1;"), SYN),
    ("SYN: palavra reservada depois do ponto (on)",  stm("Sala.lamp.on();"), SYN),
    ("SYN: palavra reservada depois do ponto (min)", stm("Sala.lamp.min = 1;"), SYN),
    ("SYN: tipo desconhecido em var",        prog("var a : float = 1.0;"), SYN),
    ("SYN: operador duplo",                  prog("const a : int = 1 + * 2;"), SYN),
    ("SYN: atribuição sem valor",            stm("a = ;"), SYN),
]

CASOS_CODIGOS = [
    ("for: comando inexistente",    prog("zone Z { device a : light; } group g = [Z.a]; scene S { for l in g { l.nope(); } }"), ["noSuchMember"]),
    ("for: tipo errado",            prog('zone Z { device a : dimmer; } group g = [Z.a]; scene S { for l in g { l.brightness = "x"; } }'), ["typeMismatch"]),
    ("for: propriedade só leitura", prog("zone Z { device a : dimmer; } group g = [Z.a]; scene S { for l in g { l.power = true; } }"), ["readOnly"]),
    ("for: cena antes do grupo",    prog("scene S { for l in g { l.turn_on(); } } group g = [Z.a]; zone Z { device a : light; }"), []),
    ("activate não declarado",      stm("activate nope;"), ["undeclared"]),
    ("activate qualificado",        prog("zone Z { scene T { } } scene S { activate Z.T; }"), []),
    ("cena ativa-se a si própria",  prog("scene a { activate a; }"), ["cyclicActivation"]),
    ("cenas homónimas sem ciclo",   prog("zone A { scene s { activate t; } scene t { } } zone B { scene t { activate s; } scene s { } }"), []),
    ("chamar propriedade",          prog("device l : dimmer; scene S { l.brightness(); }"), ["noSuchMember"]),
    ("chamar dispositivo",          prog("device l : dimmer; scene S { l(); }"), ["noSuchMember"]),
    ("atribuir a dispositivo",      prog("device a : light; device b : light; scene S { a = b; }"), ["notAssignable"]),
    ("atribuir a cena",             prog("scene T { } scene S { T = T; }"), ["notAssignable"]),
    ("comparar dispositivos",       prog("device a : light; device b : light; scene S { if a == b { } }"), ["typeMismatch"]),
    ("init a partir de var",        prog("var a : int = 0; var b : int = a;"), ["notConstant"]),
    ("init com now",                prog("const a : time = now;"), ["notConstant"]),
    ("const circular",              prog("const a : int = b; const b : int = a;"), ["cyclicInit"]),
    ("const usa const posterior",   prog("const a : int = b + 1; const b : int = 2;"), []),
    ("const local usa estado",      prog("device a : dimmer; scene S { const k : int = a.brightness; }"), []),
    ("zona chamada block",          prog("zone block { var x : int = 0; }"), []),
    ("shadowing entre âmbitos",     prog("var x : int = 0; zone Z { var x : real = 1.0; scene S { var x : bool = true; if x { } } }"), []),
    ("local usada antes de declarada", stm("x = 1; var x : int = 0;"), ["undeclared"]),
    ("sem erro em cascata",         stm("if z > 1 { }"), ["undeclared"]),
    ("init não declarado uma vez",  prog("var a : int = b;"), ["undeclared"]),
    ("comando com argumentos a mais", prog("device l : dimmer; scene S { l.fade_to(1, 2); }"), ["typeMismatch"]),
    ("brightness acima de 100",     prog("device l : dimmer; scene S { l.brightness = 150; }"), ["outOfRange"]),
    ("brightness negativo",         prog("device l : dimmer; scene S { l.brightness = -1; }"), ["outOfRange"]),
    ("brightness nos limites",      prog("device l : dimmer; scene S { l.brightness = 0; l.brightness = 100; }"), []),
    ("fade_to acima de 100",        prog("device l : dimmer; scene S { l.fade_to(150); }"), ["outOfRange"]),
    ("position acima de 100",       prog("device b : blind; scene S { b.position = 101; }"), ["outOfRange"]),
    ("valor vindo de constante",    prog("const m : int = 50; device l : dimmer; scene S { l.brightness = m * 3; }"), ["outOfRange"]),
    ("constante local",             prog("device l : dimmer; scene S { const m : int = 150; l.brightness = m; }"), ["outOfRange"]),
    ("constante declarada depois",  prog("scene S { l.brightness = m; } device l : dimmer; const m : int = 150;"), ["outOfRange"]),
    ("intervalo no for",            prog("zone Z { device a : dimmer; } group g = [Z.a]; scene S { for l in g { l.brightness = 150; } }"), ["outOfRange"]),
    ("dispositivo qualificado",     prog("zone Z { device a : dimmer; } scene S { Z.a.brightness = 150; }"), ["outOfRange"]),
    ("sombra de constante local",   prog("const m : int = 150; device l : dimmer; scene S { const m : int = 50; l.brightness = m; }"), []),
    ("variável não é verificada",   prog("var n : int = 150; device l : dimmer; scene S { l.brightness = n; }"), []),
    ("target_temp sem intervalo",   prog("device t : thermostat; scene S { t.target_temp = 150.0; }"), []),
    ("divisão por zero",            prog("const a : int = 1 / 0;"), ["divisionByZero"]),
    ("divisão real por zero",       prog("const a : real = 1.0 / 0.0;"), ["divisionByZero"]),
    ("módulo por zero",             prog("const a : int = 1 % 0;"), ["divisionByZero"]),
    ("divisor calculado",           prog("const a : int = 1 / (2 - 2);"), ["divisionByZero"]),
    ("divisor constante",           prog("const z : int = 0; const a : int = 1 / z;"), ["divisionByZero"]),
    ("dividendo variável",          prog("var n : int = 1; scene S { n = n / 0; }"), ["divisionByZero"]),
    ("divisor variável",            prog("var n : int = 0; scene S { n = 1 / n; }"), []),
    ("divisão normal",              prog("const a : int = 7 / 2; const b : int = 7 % 2; const c : real = 1 / 0.5;"), []),
    ("sem erro em cascata",         prog("const a : int = 1 / 0; const b : int = a + 1; device l : dimmer; scene S { l.brightness = a; }"), ["divisionByZero"]),
    ("ciclo não bloqueia o cálculo", prog("const a : int = 1 / a;"), ["cyclicInit"]),
    ("vários erros",                prog("device x : nope; scene S { y = 1; }"), ["unknownDeviceType", "undeclared"]),
]

EXEMPLOS = Path(__file__).with_name("examples")

def casos_de_ficheiros():
    for f in sorted((EXEMPLOS / "valid").glob("*.domo")):
        yield (f"valid/{f.name}", f.read_text(encoding="utf-8"), OK)

def casos_de_ficheiros_codigos():
    """Os ficheiros inválidos têm de falhar com o código indicado em '// expect:'."""
    for f in sorted((EXEMPLOS / "invalid_semantic").glob("*.domo")):
        src = f.read_text(encoding="utf-8")
        yield (f"invalid_semantic/{f.name}", src, [src.split("expect:")[1].split()[0]])

def codigos(parser, src):
    tree, _ = syntactic_analysis(parser, src)
    if tree is None:
        return ["<erro sintático>"]
    return [e.code for e in SemanticAnalyzer().analyze(tree)]

def classifica(parser, src):
    _, lex_err = lexical_analysis(parser, src)
    if lex_err:
        return LEX
    tree, syn_err = syntactic_analysis(parser, src)
    if syn_err:
        return SYN
    sem_err = SemanticAnalyzer().analyze(tree)
    if sem_err:
        return SEM
    return OK

def conflitos_lalr():
    from lark import logger
    avisos = []
    class H(logging.Handler):
        def emit(self, r): avisos.append(r.getMessage())
    h, antigo = H(), logger.level
    logger.addHandler(h); logger.setLevel(logging.DEBUG)
    try:
        build_parser(debug=True)
        return [a for a in avisos if "onflict" in a], None
    except Exception as e:
        return [], str(e)
    finally:
        logger.removeHandler(h); logger.setLevel(antigo)

if __name__ == "__main__":
    print("== Gramática ==")
    conf, exc = conflitos_lalr()
    if exc:
        print("ERRO ao construir LALR:", exc)
    else:
        print(f"Conflitos shift/reduce ou reduce/reduce: {len(conf)}  (esperado: 0)")
        for c in conf: print("  ", c)

    print("\n== Testes ==")
    p = build_parser()
    falhas = 0
    todos = CASOS + list(casos_de_ficheiros())
    for nome, src, esperado in todos:
        obtido = classifica(p, src)
        ok = obtido == esperado
        falhas += not ok
        print(f"{'✓' if ok else '✗'}  {esperado:<3} {nome}" + ("" if ok else f"   (obtido: {obtido})"))
    print("\n== Códigos de erro semântico ==")
    com_codigo = CASOS_CODIGOS + list(casos_de_ficheiros_codigos())
    for nome, src, esperado in com_codigo:
        obtido = codigos(p, src)
        ok = obtido == esperado
        falhas += not ok
        print(f"{'✓' if ok else '✗'}  {nome}: {esperado or 'aceite'}" + ("" if ok else f"   (obtido: {obtido})"))
    arvore = syntactic_analysis(p, stm("x = 1;"))[0]
    posicao_ok = all(e.line > 0 for e in SemanticAnalyzer().analyze(arvore))
    arvore = syntactic_analysis(p, prog("device a : dimmer;\nscene S { a.brightness = true; }"))[0]
    posicao_ok = posicao_ok and all(e.line == 2 for e in SemanticAnalyzer().analyze(arvore))
    falhas += not posicao_ok
    print(f"{'✓' if posicao_ok else '✗'}  erros indicam a linha correta")
    total = len(todos) + len(com_codigo) + 1
    print(f"\n{total - falhas}/{total} testes passaram")
    raise SystemExit(1 if falhas else 0)