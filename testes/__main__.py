"""Corre a bateria de testes.

Uso (na raiz do repositório):
    python -m testes                 # todas as secções
    python -m testes gramatica ast   # só algumas: gramatica, ast
"""
import sys

from . import test_ast, test_gramatica
from .comum import Relatorio

SECOES = {"gramatica": test_gramatica, "ast": test_ast}


def main(argv):
    pedidas = argv or list(SECOES)
    desconhecidas = [s for s in pedidas if s not in SECOES]
    if desconhecidas:
        print(f"secções desconhecidas: {', '.join(desconhecidas)} (existem: {', '.join(SECOES)})")
        return 2
    r = Relatorio()
    for nome in pedidas:
        SECOES[nome].correr(r)
    print(f"\n{r.passados}/{r.total} testes passaram")
    return 0 if r.passados == r.total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
