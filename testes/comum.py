"""Utilitários partilhados pelos testes."""
from pathlib import Path

EXEMPLOS = Path(__file__).resolve().parent.parent / "examples"

OK, LEX, SYN, SEM = "OK", "LEX", "SYN", "SEM"


def prog(body: str) -> str:
    """Programa mínimo à volta de um conjunto de declarações."""
    return f'home "t" {{ {body} }}'


def stm(body: str) -> str:
    """Programa mínimo à volta de um conjunto de instruções (numa cena S)."""
    return prog(f"scene S {{ {body} }}")


def exemplo(caminho: str) -> str:
    """Texto de um ficheiro de examples/ (ex.: 'valid/03_full.domo')."""
    return (EXEMPLOS / caminho).read_text(encoding="utf-8")


def casos_de_ficheiros():
    """Os exemplos válidos têm de passar todas as fases."""
    for f in sorted((EXEMPLOS / "valid").glob("*.domo")):
        yield (f"valid/{f.name}", f.read_text(encoding="utf-8"), OK)


def casos_de_ficheiros_codigos():
    """Os ficheiros inválidos têm de falhar com o código indicado em '// expect:'."""
    for f in sorted((EXEMPLOS / "invalid_semantic").glob("*.domo")):
        src = f.read_text(encoding="utf-8")
        yield (f"invalid_semantic/{f.name}", src, [src.split("expect:")[1].split()[0]])


class Relatorio:
    """Conta e mostra os resultados. Cada verifica() é um teste."""

    def __init__(self):
        self.passados = 0
        self.total = 0

    def secao(self, titulo: str):
        print(f"\n== {titulo} ==")

    def verifica(self, ok: bool, descricao: str, detalhe="") -> bool:
        self.total += 1
        self.passados += bool(ok)
        print(f"{'✓' if ok else '✗'}  {descricao}" + ("" if ok or not detalhe else f"   ({detalhe})"))
        return ok

    def nota(self, texto: str):
        """Informação que não conta como teste (ex.: verificação ignorada)."""
        print(f"-  {texto}")
