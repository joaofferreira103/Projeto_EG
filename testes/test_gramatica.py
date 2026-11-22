"""Parte I: gramática (conflitos LALR), classificação dos programas e códigos de erro semântico."""
import logging

from domo.parser import build_parser, lexical_analysis, syntactic_analysis
from domo.semantic import SemanticAnalyzer

from .casos import CASOS, CASOS_CODIGOS
from .comum import LEX, OK, SEM, SYN, Relatorio, casos_de_ficheiros, casos_de_ficheiros_codigos, prog, stm


def conflitos_lalr():
    """(avisos de conflito do Lark, erro ao construir a tabela ou None)."""
    from lark import logger
    avisos = []

    class H(logging.Handler):
        def emit(self, r):
            avisos.append(r.getMessage())

    h, antigo = H(), logger.level
    logger.addHandler(h)
    logger.setLevel(logging.DEBUG)
    try:
        build_parser(debug=True)
        return [a for a in avisos if "onflict" in a], None
    except Exception as e:
        return [], str(e)
    finally:
        logger.removeHandler(h)
        logger.setLevel(antigo)


def classifica(parser, src):
    """Primeira fase que rejeita o programa (LEX, SYN, SEM) ou OK."""
    _, lex_err = lexical_analysis(parser, src)
    if lex_err:
        return LEX
    tree, syn_err = syntactic_analysis(parser, src)
    if syn_err:
        return SYN
    return SEM if SemanticAnalyzer().analyze(tree) else OK


def codigos(parser, src):
    tree, _ = syntactic_analysis(parser, src)
    if tree is None:
        return ["<erro sintático>"]
    return [e.code for e in SemanticAnalyzer().analyze(tree)]


def correr(r: Relatorio):
    r.secao("Gramática")
    conf, exc = conflitos_lalr()
    r.verifica(exc is None and not conf, "LALR(1) sem conflitos shift/reduce nem reduce/reduce",
               exc or "; ".join(conf[:3]))

    r.secao("Classificação dos programas")
    p = build_parser()
    for nome, src, esperado in CASOS + list(casos_de_ficheiros()):
        obtido = classifica(p, src)
        r.verifica(obtido == esperado, f"{esperado:<3} {nome}", f"obtido: {obtido}")

    r.secao("Códigos de erro semântico")
    for nome, src, esperado in CASOS_CODIGOS + list(casos_de_ficheiros_codigos()):
        obtido = codigos(p, src)
        r.verifica(obtido == esperado, f"{nome}: {esperado or 'aceite'}", f"obtido: {obtido}")

    arvore = syntactic_analysis(p, stm("x = 1;"))[0]
    posicao_ok = all(e.line > 0 for e in SemanticAnalyzer().analyze(arvore))
    arvore = syntactic_analysis(p, prog("device a : dimmer;\nscene S { a.brightness = true; }"))[0]
    posicao_ok = posicao_ok and all(e.line == 2 for e in SemanticAnalyzer().analyze(arvore))
    r.verifica(posicao_ok, "erros indicam a linha correta")
