#!/usr/bin/env python3
"""Bateria de testes léxicos e sintáticos. Uso: python testes.py"""
import logging
from pathlib import Path

from analisador import build_parser, lexical_analysis, syntactic_analysis

OK, LEX, SYN = "OK", "LEX", "SYN"       # resultado esperado

def prog(body: str) -> str:
    return f'home "t" {{ {body} }}'

def stm(body: str) -> str:               # instrução dentro de uma cena
    return prog(f"scene S {{ {body} }}")

CASOS = [
    # ---------------- válidos ----------------
    ("exemplo A.8 completo",                 Path(__file__).with_name("casa.domo").read_text(), OK),
    ("programa vazio",                       prog(""), OK),
    ("zonas aninhadas",                      prog("zone A { zone B { zone C { device d : x; } } }"), OK),
    ("if sem parênteses",                    stm("if a { }"), OK),
    ("else if encadeado",                    stm("if a { } else if b { } else { }"), OK),
    ("menos unário e binário",               prog("const a : int = 1 - -2;"), OK),
    ("precedência not/and/or",               prog("const a : bool = not x and y or z;"), OK),
    ("comparação com TIME e now",            stm("if now >= 07:30 { }"), OK),
    ("repeat com expressão",                 stm("repeat n + 1 times { }"), OK),
    ("comentário no fim da linha",           'home "t" {\n  const a : int = 1; // comentário\n}', OK),
    ("comando sem argumentos",               stm("Sala.lamp.turn_on();"), OK),
    ("comando com argumentos",               stm("Sala.lamp.set(50, 3 + 4);"), OK),
    ("regra mínima",                         prog("rule R on at 22:30 { }"), OK),
    ("regra com todas as partes",            prog("rule R priority 3 on every 5 min when a { }"), OK),
    ("unidade como parte de nome (minimo)",  prog("var minimo : int = 0;"), OK),
    ("prefixo de keyword como ID (iffy)",    prog("var iffy : int = 0;"), OK),
    # válidos sintaticamente, inválidos semanticamente (motivam a gramática de atributos)
    ("SEM: dispositivo inexistente",         stm("Living.sofa.turn_on();"), OK),
    ("SEM: atribuir a const",                prog("const c : real = 1.0; scene S { c = 22.0; }"), OK),
    ("SEM: for sobre zona",                  stm("for x in Living { }"), OK),
    ("SEM: repeat com string",               stm('repeat "tres" times { }'), OK),
    ("SEM: activate de regra",               stm("activate Heat;"), OK),
    ("SEM: tipo errado na atribuição",       stm('Living.lamp.brightness = "alto";'), OK),

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
    ("SYN: palavra reservada depois do ponto (on)",  stm("Sala.lamp.on();"), SYN),
    ("SYN: palavra reservada depois do ponto (min)", stm("Sala.lamp.min = 1;"), SYN),
    ("SYN: tipo desconhecido em var",        prog("var a : float = 1.0;"), SYN),
    ("SYN: operador duplo",                  prog("const a : int = 1 + * 2;"), SYN),
    ("SYN: atribuição sem valor",            stm("a = ;"), SYN),
]

def classifica(parser, src):
    _, lex_err = lexical_analysis(parser, src)
    if lex_err:
        return LEX
    _, err = syntactic_analysis(parser, src)
    return SYN if err else OK

def conflitos_lalr():
    """Constrói a tabela LALR com debug ligado e recolhe os avisos de conflitos."""
    from lark import logger
    avisos = []
    class H(logging.Handler):
        def emit(self, r): avisos.append(r.getMessage())
    h, antigo = H(), logger.level
    logger.addHandler(h); logger.setLevel(logging.DEBUG)
    try:
        build_parser("basic", debug=True)
        return [a for a in avisos if "onflict" in a], None
    except Exception as e:                      # reduce/reduce levanta exceção
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
    for nome, src, esperado in CASOS:
        obtido = classifica(p, src)
        ok = obtido == esperado
        falhas += not ok
        print(f"{'✓' if ok else '✗'}  {esperado:<3} {nome}" + ("" if ok else f"   (obtido: {obtido})"))
    print(f"\n{len(CASOS) - falhas}/{len(CASOS)} testes passaram")
    raise SystemExit(1 if falhas else 0)
