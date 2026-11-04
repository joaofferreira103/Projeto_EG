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
    # ---------------- válidos (Léxica + Sintática + Semântica) ----------------
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
    ("unidade como parte de nome (minimo)",  prog("var minimo : int = 0;"), OK),
    ("prefixo de keyword como ID (iffy)",    prog("var iffy : int = 0;"), OK),

    # ---------------- erros semânticos ----------------
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

    # ---------------- erros léxicos ----------------
    ("LEX: carácter ilegal @",               prog("const a : int = 1 @ 2;"), LEX),
    ("LEX: string por fechar",               prog('scene S { notify "olá; }'), LEX),
    ("LEX: carácter ilegal #",               prog("# isto não é comentário"), LEX),

    # ---------------- erros sintáticos ----------------
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

EXEMPLOS = Path(__file__).with_name("examples")

def casos_de_ficheiros():
    for f in sorted((EXEMPLOS / "valid").glob("*.domo")):
        yield (f"valid/{f.name}", f.read_text(encoding="utf-8"), OK)
    for f in sorted((EXEMPLOS / "invalid_semantic").glob("*.domo")):
        yield (f"SEM: {f.stem}", f.read_text(encoding="utf-8"), SEM)

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
        build_parser("basic", debug=True)
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
    p = build_parser("basic")
    falhas = 0
    todos = CASOS + list(casos_de_ficheiros())
    for nome, src, esperado in todos:
        obtido = classifica(p, src)
        ok = obtido == esperado
        falhas += not ok
        print(f"{'✓' if ok else '✗'}  {esperado:<3} {nome}" + ("" if ok else f"   (obtido: {obtido})"))
    total = len(todos)
    print(f"\n{total - falhas}/{total} testes passaram")
    raise SystemExit(1 if falhas else 0)