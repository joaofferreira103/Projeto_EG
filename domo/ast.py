"""AST elaborado da linguagem Domo.

Cada nó guarda só a estrutura do programa (o que o pretty-printer precisa para o
voltar a escrever). A informação semântica vem em campos à parte, preenchidos por
builder.py a partir da análise semântica:

- Ref.res: o que a referência designa (símbolo, membro, categoria, tipo, acesso);
- Expr.type: o tipo da expressão;
- Decl.sym e For.sym: o símbolo criado pela declaração.

Esses campos e as posições (line, col) não entram na igualdade entre nós, por isso
dois programas com a mesma estrutura são iguais (==) mesmo vindos de textos diferentes.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple, Union


def _pos():
    return field(default=0, kw_only=True, compare=False, repr=False)


def _info():
    return field(default=None, kw_only=True, compare=False, repr=False)


@dataclass
class Node:
    line: int = _pos()
    col: int = _pos()


# ---------------------------------------------------------------- Expressões

@dataclass
class Expr(Node):
    type: Optional[str] = _info()          # int, real, bool, string, time; None se não se conhece


@dataclass
class IntLit(Expr):
    value: int


@dataclass
class RealLit(Expr):
    value: float


@dataclass
class StrLit(Expr):
    value: str                             # sem as aspas


@dataclass
class TimeLit(Expr):
    hour: int
    minute: int

    @property
    def minutes(self) -> int:
        """Minutos desde as 00:00."""
        return self.hour * 60 + self.minute


@dataclass
class BoolLit(Expr):
    value: bool


@dataclass
class Now(Expr):
    pass


@dataclass
class Ref(Expr):
    path: Tuple[str, ...]                  # ("Floor1", "Living", "lamp", "brightness")
    res: Any = _info()                     # semantic.Resolution, ou None se não resolveu

    @property
    def symbol(self):
        """Variável, constante, dispositivo, grupo, cena ou zona designado.
        Num acesso a membro (lamp.brightness) é o dispositivo."""
        return self.res.symbol if self.res else None

    @property
    def member(self) -> Optional[str]:
        """Propriedade, comando ou evento acedido; None se não for um acesso a membro."""
        return self.res.member if self.res else None

    @property
    def kind(self) -> Optional[str]:
        """var, const, device, group, scene, zone, property, command ou event."""
        return self.res.kind if self.res else None

    def __str__(self) -> str:
        return ".".join(self.path)


@dataclass
class Unary(Expr):
    op: str                                # "-" ou "not"
    operand: Expr


@dataclass
class Binary(Expr):
    op: str                                # or and == != < <= > >= + - * / %
    left: Expr
    right: Expr


# ---------------------------------------------------------------- Instruções

@dataclass
class Duration(Node):
    amount: int
    unit: str                              # sec, min, hour

    @property
    def seconds(self) -> int:
        return self.amount * {"sec": 1, "min": 60, "hour": 3600}[self.unit]


@dataclass
class Stmt(Node):
    pass


@dataclass
class Block(Node):
    stmts: List[Stmt]


@dataclass
class VarDecl(Stmt):
    """var/const, ao nível da zona ou dentro de um bloco."""
    name: str
    var_type: str
    init: Expr
    const: bool = False
    sym: Any = _info()


@dataclass
class Assign(Stmt):
    target: Ref
    value: Expr


@dataclass
class Command(Stmt):
    target: Ref                            # lamp.fade_to: dispositivo + comando
    args: List[Expr]


@dataclass
class If(Stmt):
    cond: Expr
    then: Block
    orelse: Union[Block, "If", None] = None


@dataclass
class Repeat(Stmt):
    count: Expr
    body: Block


@dataclass
class For(Stmt):
    var: str
    group: Ref
    body: Block
    sym: Any = _info()                     # símbolo da variável do ciclo (um dispositivo)


@dataclass
class Wait(Stmt):
    duration: Duration


@dataclass
class Notify(Stmt):
    message: str


@dataclass
class Activate(Stmt):
    scene: Ref


# ---------------------------------------------------------------- Eventos

@dataclass
class Event(Node):
    pass


@dataclass
class OnChange(Event):
    target: Ref                            # propriedade


@dataclass
class OnSignal(Event):
    target: Ref                            # evento de um dispositivo


@dataclass
class At(Event):
    time: TimeLit


@dataclass
class Every(Event):
    period: Duration


# ---------------------------------------------------------------- Declarações

@dataclass
class Decl(Node):
    pass


@dataclass
class Device(Decl):
    name: str
    device_type: str
    sym: Any = _info()


@dataclass
class Group(Decl):
    name: str
    members: List[Ref]
    sym: Any = _info()


@dataclass
class Scene(Decl):
    name: str
    body: Block
    sym: Any = _info()


@dataclass
class Rule(Decl):
    name: str
    priority: Optional[int]
    event: Event
    guard: Optional[Expr]
    body: Block
    sym: Any = _info()


@dataclass
class Zone(Decl):
    name: str
    decls: List[Union[Decl, VarDecl]]
    sym: Any = _info()


@dataclass
class Program(Node):
    name: str
    decls: List[Union[Decl, VarDecl]]

    def walk(self):
        """Todos os nós do programa, em pré-ordem."""
        return walk(self)


def walk(node):
    """Percorre node e os seus descendentes em pré-ordem (só nós do AST)."""
    yield node
    for f in node.__dataclass_fields__.values():
        if not f.compare:
            continue
        value = getattr(node, f.name)
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, Node):
                yield from walk(item)
