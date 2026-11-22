"""Fase 0: AST elaborado e pretty-printer."""
import random

from domo import ast as A
from domo.builder import load
from domo.parser import build_parser, syntactic_analysis
from domo.pretty import pretty

from .casos import CASOS, CASOS_CODIGOS
from .comum import Relatorio, casos_de_ficheiros, casos_de_ficheiros_codigos, prog


def programas_sintaticamente_validos():
    """Todos os programas dos testes e exemplos que passam a análise sintática."""
    parser = build_parser()
    fontes = CASOS + list(casos_de_ficheiros()) + CASOS_CODIGOS + list(casos_de_ficheiros_codigos())
    for nome, src, _ in fontes:
        if syntactic_analysis(parser, src)[0] is not None:
            yield nome, src


def ida_e_volta(src):
    """None se parse(pretty(p)) == p, pretty for idempotente e os erros semânticos se
    mantiverem; senão, a descrição da falha."""
    r1 = load(src)
    texto = pretty(r1.program)
    r2 = load(texto)
    if r2.program is None:
        return "o texto gerado não é aceite:\n" + r2.syntax_error
    if r2.program != r1.program:
        return "AST diferente depois da ida e volta"
    if pretty(r2.program) != texto:
        return "pretty não é idempotente"
    if sorted(e.code for e in r1.errors) != sorted(e.code for e in r2.errors):
        return "erros semânticos diferentes"
    return None


def expressao_aleatoria(rng, prof):
    """Expressão aleatória (sem verificar tipos), para testar os parênteses do pretty-printer."""
    if prof == 0 or rng.random() < 0.2:
        return rng.choice([lambda: A.IntLit(rng.randint(0, 9)), lambda: A.RealLit(rng.choice([0.5, 2.25])),
                           lambda: A.BoolLit(rng.random() < 0.5), lambda: A.Ref((rng.choice("abc"),)),
                           lambda: A.Now(), lambda: A.TimeLit(7, 30)])()
    if rng.random() < 0.25:
        return A.Unary(rng.choice(["-", "not"]), expressao_aleatoria(rng, prof - 1))
    op = rng.choice(["or", "and", "==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/", "%"])
    return A.Binary(op, expressao_aleatoria(rng, prof - 1), expressao_aleatoria(rng, prof - 1))


def expressoes_aleatorias_ida_e_volta(n=500, seed=2627):
    """Expressões aleatórias cuja ida e volta pelo texto não dá a mesma árvore."""
    rng, falhas = random.Random(seed), []
    for _ in range(n):
        e = expressao_aleatoria(rng, 5)
        r = load(prog(f"const x : int = {pretty(e)};"))
        if r.program is None or r.program.decls[0].init != e:
            falhas.append(pretty(e))
    return falhas


def referencias_por_resolver(src):
    """Referências, expressões e declarações sem anotação semântica num programa válido."""
    faltam = []
    for n in A.walk(load(src).program):
        if isinstance(n, A.Ref) and n.res is None:
            faltam.append(f"{n} ({n.line}:{n.col})")
        elif (isinstance(n, A.Expr) and n.type is None
              and not (isinstance(n, A.Ref) and n.kind in ("device", "group", "scene", "command", "event"))):
            faltam.append(f"tipo de {pretty(n)} ({n.line}:{n.col})")
        elif isinstance(n, (A.VarDecl, A.Device, A.Group, A.Scene, A.Rule, A.Zone, A.For)) and n.sym is None:
            faltam.append(f"símbolo de {type(n).__name__} ({n.line}:{n.col})")
    return faltam


def correr(r: Relatorio):
    r.secao("AST e pretty-printer")
    validos = list(programas_sintaticamente_validos())
    falhas = [f"{nome}: {erro}" for nome, src in validos if (erro := ida_e_volta(src))]
    r.verifica(not falhas, f"ida e volta em {len(validos)} programas", "; ".join(falhas[:3]))

    exprs = expressoes_aleatorias_ida_e_volta()
    r.verifica(not exprs, "parênteses em 500 expressões aleatórias", f"ex.: {exprs[0]}" if exprs else "")

    for nome, src, _ in casos_de_ficheiros():
        faltam = referencias_por_resolver(src)
        r.verifica(not faltam, f"AST elaborado completo: {nome}", f"faltam: {faltam[:3]}")
