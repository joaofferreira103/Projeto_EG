#!/usr/bin/env python3
"""
Avaliação da qualidade da gramática e da linguagem (Tarefa 4 do enunciado).

Todos os valores são calculados a partir de domo.lark e dos testes existentes,
por isso continuam certos se a gramática mudar. Uso: python -m testes.qualidade

Código de saída: 0 se todas as verificações obrigatórias passarem, 1 caso contrário.
Métricas de tamanho e de estrutura baseadas em Power & Malloy, "A metrics suite for
grammar-based software" (2004), adaptadas a BNF.
"""
import logging
from collections import Counter, defaultdict
from pathlib import Path

from lark import Lark, Tree, logger
from lark.exceptions import GrammarError
from lark.lexer import PatternStr

from domo.parser import GRAMMAR, build_derivation_parser, build_parser, lexical_analysis, syntactic_analysis
from domo.semantic import SemanticAnalyzer
from .casos import CASOS, CASOS_CODIGOS
from .comum import EXEMPLOS, OK, SEM

PALAVRAS_RESERVADAS = set("""home zone device var const group scene rule
    priority on change signal at every when
    if else repeat times for in wait notify activate
    and or not true false now
    int real bool string time
    sec min hour""".split())
SIMBOLOS = set("{ } [ ] ( ) , ; : . = + - * / % == != < <= > >=".split())
CODIGOS_TABELA_8 = {"typeMismatch", "readOnly", "noSuchMember", "undeclared", "duplicate", "assignToConst",
                    "unknownDeviceType", "heterogeneousGroup", "invalidTime", "zeroPeriod", "notAnEvent",
                    "notAProperty", "notAScene", "condNotBool", "cyclicActivation"}
DANGLING_ELSE = 's: "if" "x" s | "if" "x" s "else" s | "y"\n%ignore " "\n'


class Grammar:
    """Vista em BNF de domo.lark, sem as simplificações de árvore ('?regra' e '_regra')."""

    def __init__(self, parser: Lark):
        self.ignored = set(parser.ignore_tokens)
        self.prods = [(str(r.origin.name), tuple(s.name for s in r.expansion), r.alias) for r in parser.rules]
        self.nonterms = {lhs for lhs, _, _ in self.prods}
        self.terms = {t.name for t in parser.terminals} - self.ignored
        self.by_lhs = defaultdict(list)
        for lhs, rhs, _ in self.prods:
            self.by_lhs[lhs].append(rhs)
        self.calls = {n: {s for rhs in self.by_lhs[n] for s in rhs if s in self.nonterms} for n in self.nonterms}
        self.nullable = self._nullable()
        self.first = self._first()
        self.follow = self._follow()

    def _nullable(self):
        out, changed = set(), True
        while changed:
            changed = False
            for lhs, rhs, _ in self.prods:
                if lhs not in out and all(s in out for s in rhs):
                    out.add(lhs)
                    changed = True
        return out

    def first_of(self, seq, first=None):
        first = self.first if first is None else first
        out = set()
        for s in seq:
            out |= first.get(s, {s})
            if s not in self.nullable:
                break
        return out

    def _first(self):
        first = {n: set() for n in self.nonterms}
        changed = True
        while changed:
            changed = False
            for lhs, rhs, _ in self.prods:
                new = self.first_of(rhs, first)
                if not new <= first[lhs]:
                    first[lhs] |= new
                    changed = True
        return first

    def _follow(self):
        follow = {n: set() for n in self.nonterms}
        follow["start"].add("$END")
        changed = True
        while changed:
            changed = False
            for lhs, rhs, _ in self.prods:
                for i, s in enumerate(rhs):
                    if s not in self.nonterms:
                        continue
                    tail = rhs[i + 1:]
                    new = self.first_of(tail)
                    if all(t in self.nullable for t in tail):
                        new |= follow[lhs]
                    if not new <= follow[s]:
                        follow[s] |= new
                        changed = True
        return follow

    def reachable(self):
        seen, todo = {"start"}, ["start"]
        while todo:
            for s in self.calls[todo.pop()] - seen:
                seen.add(s)
                todo.append(s)
        return seen

    def productive(self):
        out, changed = set(), True
        while changed:
            changed = False
            for lhs, rhs, _ in self.prods:
                if lhs not in out and all(s not in self.nonterms or s in out for s in rhs):
                    out.add(lhs)
                    changed = True
        return out

    def used_terminals(self):
        return {s for _, rhs, _ in self.prods for s in rhs if s not in self.nonterms}

    def left_recursive(self):
        """Não-terminais que se podem derivar a si próprios na posição mais à esquerda."""
        left = {n: set() for n in self.nonterms}
        for lhs, rhs, _ in self.prods:
            for s in rhs:
                if s in self.nonterms:
                    left[lhs].add(s)
                if s not in self.nullable:
                    break
        out = set()
        for n in self.nonterms:
            seen, todo = set(), list(left[n])
            while todo:
                s = todo.pop()
                if s not in seen:
                    seen.add(s)
                    todo.extend(left[s])
            if n in seen:
                out.add(n)
        return out

    def ll1_conflicts(self):
        """Não-terminais em que um símbolo de avanço não chega para escolher a alternativa."""
        out = set()
        for n, alts in self.by_lhs.items():
            for i, a in enumerate(alts):
                for b in alts[i + 1:]:
                    fa, fb = self.first_of(a), self.first_of(b)
                    a_null = all(s in self.nullable for s in a)
                    b_null = all(s in self.nullable for s in b)
                    if fa & fb or (a_null and fb & self.follow[n]) or (b_null and fa & self.follow[n]):
                        out.add(n)
        return out

    def levels(self):
        """Componentes fortemente ligadas do grafo de dependências (algoritmo de Tarjan)."""
        index, low, stack, on_stack, comps = {}, {}, [], set(), []

        def visit(v):
            index[v] = low[v] = len(index)
            stack.append(v)
            on_stack.add(v)
            for w in self.calls[v]:
                if w not in index:
                    visit(w)
                    low[v] = min(low[v], low[w])
                elif w in on_stack:
                    low[v] = min(low[v], index[w])
            if low[v] == index[v]:
                comp = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.add(w)
                    if w == v:
                        break
                comps.append(comp)

        for n in sorted(self.nonterms):
            if n not in index:
                visit(n)
        return comps

    def height(self, comps):
        """Comprimento (em níveis) do caminho mais longo no grafo de componentes."""
        comp_of = {n: i for i, c in enumerate(comps) for n in c}
        memo = {}

        def h(i):
            if i not in memo:
                succ = {comp_of[w] for v in comps[i] for w in self.calls[v]} - {i}
                memo[i] = 1 + max((h(j) for j in succ), default=0)
            return memo[i]

        return max(h(i) for i in range(len(comps)))


def conflitos(grammar_text: str):
    """Devolve (mensagens de conflito shift/reduce, erro de conflito reduce/reduce ou None)."""
    avisos = []

    class Captura(logging.Handler):
        def emit(self, record):
            avisos.append(record.getMessage())

    handler, nivel, originais = Captura(), logger.level, logger.handlers[:]
    logger.handlers[:] = [handler]
    logger.setLevel(logging.DEBUG)
    try:
        Lark(grammar_text, parser="lalr", lexer="basic", debug=True, start="start" if "start:" in grammar_text else "s")
        return [a for a in avisos if "onflict" in a], None
    except GrammarError as e:
        return [a for a in avisos if "onflict" in a], str(e)
    finally:
        logger.handlers[:] = originais
        logger.setLevel(nivel)


def corpus():
    """Programas sintaticamente corretos usados nos testes e nos exemplos."""
    out = [src for _, src, esperado in CASOS if esperado in (OK, SEM)]
    out += [src for _, src, _ in CASOS_CODIGOS]
    out += [f.read_text(encoding="utf-8") for f in sorted(EXEMPLOS.glob("*/*.domo"))]
    return out


def cobertura(deriv: Lark, g: Grammar):
    """Produções da gramática exercitadas pelo corpus de testes."""
    origem = {alias: lhs for lhs, _, alias in g.prods if alias}

    def nome(child):
        return origem.get(child.data, str(child.data)) if isinstance(child, Tree) else child.type

    usadas = set()
    for src in corpus():
        for no in deriv.parse(src).iter_subtrees():
            usadas.add((origem.get(no.data, str(no.data)), tuple(nome(c) for c in no.children)))
    todas = {(lhs, rhs) for lhs, rhs, _ in g.prods}
    return len(todas & usadas), len(todas), sorted(todas - usadas)


def mutacao_apaga_token(parser: Lark, ficheiro: Path):
    """Apaga cada token do programa, um de cada vez, e regista em que fase o erro é apanhado."""
    src = ficheiro.read_text(encoding="utf-8")
    fases, silenciosos = Counter(), Counter()
    tokens, _ = lexical_analysis(parser, src)
    for t in tokens:
        mutado = src[:t.start_pos] + " " + src[t.end_pos:]
        arvore, erro = syntactic_analysis(parser, mutado)
        if erro:
            fases["sintática"] += 1
        elif SemanticAnalyzer().analyze(arvore):
            fases["semântica"] += 1
        else:
            fases["não detetado"] += 1
            silenciosos[t.type] += 1
    return len(tokens), fases, silenciosos


def main():
    falhas = []

    def verifica(descricao, ok, detalhe=""):
        print(f"  {'OK   ' if ok else 'FALHA'} {descricao}" + (f": {detalhe}" if detalhe else ""))
        if not ok:
            falhas.append(descricao)

    parser = build_parser()
    deriv = build_derivation_parser()
    g = Grammar(deriv)

    print("== 1. Dimensão ==")
    print(f"  Terminais (TERM):        {len(g.terms)}")
    print(f"  Não-terminais (VAR):     {len(g.nonterms)}")
    print(f"  Produções BNF (PROD):    {len(g.prods)}")

    print("\n== 2. Complexidade ==")
    tamanhos = [len(rhs) for _, rhs, _ in g.prods]
    alternativas = [len(a) for a in g.by_lhs.values()]
    print(f"  RHS médio / máximo:      {sum(tamanhos) / len(tamanhos):.2f} / {max(tamanhos)}")
    print(f"  Alternativas por regra:  {sum(alternativas) / len(alternativas):.2f} (máximo {max(alternativas)})")
    print(f"  McCabe médio (MCC):      {sum(a - 1 for a in alternativas) / len(alternativas) + 1:.2f}")
    print(f"  Produções vazias:        {sum(1 for t in tamanhos if t == 0)}")
    print(f"  Produções unitárias:     {sum(1 for _, r, _ in g.prods if len(r) == 1 and r[0] in g.nonterms)}")

    print("\n== 3. Estrutura do grafo de dependências ==")
    comps = g.levels()
    arcos = sum(len(v) for v in g.calls.values())
    n = len(g.nonterms)
    maior = max(comps, key=len)
    print(f"  Impureza de árvore (TIMP):   {200 * (arcos - n + 1) / ((n - 1) * (n - 2)):.1f}%")
    print(f"  Níveis, normalizado (CLEV):  {100 * len(comps) / n:.1f}% ({len(comps)} níveis)")
    print(f"  Níveis recursivos (NSLEV):   {sum(1 for c in comps if len(c) > 1)}")
    print(f"  Maior nível (DEP):           {len(maior)} ({', '.join(sorted(maior))})")
    print(f"  Altura (HEI):                {g.height(comps)}")

    print("\n== 4. Correção da gramática ==")
    inalc = g.nonterms - g.reachable()
    improd = g.nonterms - g.productive()
    sem_uso = g.terms - g.used_terminals()
    verifica("todos os não-terminais são alcançáveis", not inalc, ", ".join(sorted(inalc)))
    verifica("todos os não-terminais são produtivos", not improd, ", ".join(sorted(improd)))
    verifica("todos os terminais são usados", not sem_uso, ", ".join(sorted(sem_uso)))
    texto = GRAMMAR.read_text(encoding="utf-8")
    sr, rr = conflitos(texto)
    verifica("LALR(1) sem conflitos, logo não ambígua", not sr and not rr, f"{len(sr)} shift/reduce, {'com' if rr else '0'} reduce/reduce")
    controlo, _ = conflitos(DANGLING_ELSE)
    verifica("controlo: o detetor encontra o conflito do dangling else", bool(controlo), f"{len(controlo)} conflito(s)")

    print("\n== 5. Classe da gramática (informativo) ==")
    print(f"  Recursão à esquerda:     {', '.join(sorted(g.left_recursive())) or 'nenhuma'}")
    print(f"  Conflitos LL(1):         {', '.join(sorted(g.ll1_conflicts())) or 'nenhum'}")

    print("\n== 6. Conformidade com o relatório ==")
    literais = {t.pattern.value for t in parser.terminals if isinstance(t.pattern, PatternStr)}
    palavras = {w for w in literais if w.isalpha()}
    simbolos = literais - palavras
    verifica(f"palavras reservadas = Tabela 9 ({len(PALAVRAS_RESERVADAS)})", palavras == PALAVRAS_RESERVADAS,
             " ".join(sorted(palavras ^ PALAVRAS_RESERVADAS)))
    verifica(f"operadores e pontuação = Tabela 11 ({len(SIMBOLOS)})", simbolos == SIMBOLOS,
             " ".join(sorted(simbolos ^ SIMBOLOS)))
    codigos = set()
    for f in EXEMPLOS.glob("invalid_semantic/*.domo"):
        arvore, _ = syntactic_analysis(parser, f.read_text(encoding="utf-8"))
        codigos |= {e.code for e in SemanticAnalyzer().analyze(arvore)}
    verifica(f"códigos da Tabela 8 detetados nos exemplos ({len(CODIGOS_TABELA_8)})", CODIGOS_TABELA_8 <= codigos,
             " ".join(sorted(CODIGOS_TABELA_8 - codigos)))

    print("\n== 7. Cobertura da gramática pelos testes ==")
    cobertas, total, falta = cobertura(deriv, g)
    verifica("todas as produções são exercitadas", not falta, f"{cobertas}/{total}")
    for lhs, rhs in falta:
        print(f"        falta: {lhs} -> {' '.join(rhs) or 'ε'}")

    print("\n== 8. Deteção de erros: apagar um token de cada vez (informativo) ==")
    ficheiro = EXEMPLOS / "valid" / "03_full.domo"
    total, fases, silenciosos = mutacao_apaga_token(parser, ficheiro)
    print(f"  Programa: {ficheiro.name}, {total} mutantes")
    for fase in ("sintática", "semântica", "não detetado"):
        print(f"  {fase:<14} {fases[fase]:>4}  ({100 * fases[fase] / total:.1f}%)")
    print(f"  Tokens cuja remoção não é detetada: {dict(silenciosos.most_common())}")

    print(f"\n{'Todas as verificações passaram.' if not falhas else f'{len(falhas)} verificação(ões) falharam.'}")
    raise SystemExit(1 if falhas else 0)


if __name__ == "__main__":
    main()
