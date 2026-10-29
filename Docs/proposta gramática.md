# Linguagem de domótica: gramática (Fase 1) 



## Parte A: Gramática

### A.1 Convenções

- `'texto'` = terminal (palavra reservada ou símbolo)
- `MAIÚSCULAS` = token com estrutura (`ID`, `INT`, `REAL`, `STRING`, `TIME`)
- `X?` opcional, `X*` zero ou mais, `( ... | ... )` alternativa
- Comentários com `//`

### A.2 Estrutura do programa

```ebnf
Program     ::= 'home' STRING '{' Decl* '}'

Decl        ::= ZoneDecl | DeviceDecl | VarDecl | GroupDecl | SceneDecl | RuleDecl

ZoneDecl    ::= 'zone' ID '{' Decl* '}'                       
DeviceDecl  ::= 'device' ID ':' ID ';'
VarDecl     ::= ( 'var' | 'const' ) ID ':' Type '=' Expr ';'
Type        ::= 'int' | 'real' | 'bool' | 'string' | 'time'
GroupDecl   ::= 'group' ID '=' '[' Ref ( ',' Ref )* ']' ';'  
SceneDecl   ::= 'scene' ID Block
```

### A.3 Regras e eventos

```ebnf
RuleDecl    ::= 'rule' ID ( 'priority' INT )? 'on' Event ( 'when' Expr )? Block
Event       ::= 'change' Ref
              | 'signal' Ref
              | 'at' TIME
              | 'every' Duration
Duration    ::= INT Unit
Unit        ::= 'sec' | 'min' | 'hour'
```

### A.4 Instruções

```ebnf
Block       ::= '{' Stmt* '}'                                 

Stmt        ::= VarDecl
              | Ref '=' Expr ';'              // atribuição (variável ou propriedade)
              | Ref '(' Args? ')' ';'         // comando a um dispositivo
              | IfStmt
              | RepeatStmt
              | ForStmt
              | 'wait' Duration ';'
              | 'notify' STRING ';'
              | 'activate' Ref ';'

IfStmt      ::= 'if' '(' Expr ')' Block ( 'else' ( Block | IfStmt ) )?
RepeatStmt  ::= 'repeat' Expr 'times' Block
ForStmt     ::= 'for' ID 'in' Ref Block
Args        ::= Expr ( ',' Expr )*                            
```

### A.5 Referências e expressões

```ebnf
Ref         ::= ID | Ref '.' ID

Expr        ::= Expr 'or' AndExpr  | AndExpr
AndExpr     ::= AndExpr 'and' NotExpr | NotExpr
NotExpr     ::= 'not' NotExpr | RelExpr
RelExpr     ::= AddExpr RelOp AddExpr | AddExpr
RelOp       ::= '==' | '!=' | '<' | '<=' | '>' | '>='
AddExpr     ::= AddExpr ( '+' | '-' ) MulExpr | MulExpr
MulExpr     ::= MulExpr ( '*' | '/' | '%' ) Unary | Unary
Unary       ::= '-' Unary | Primary
Primary     ::= INT | REAL | STRING | TIME | 'true' | 'false' | 'now'
              | Ref | '(' Expr ')'
```

### A.6 Precedência de operadores (da menor para a maior)

| Nível | Operadores | Associatividade |
|---|---|---|
| 1 | `or` | esquerda |
| 2 | `and` | esquerda |
| 3 | `not` | prefixo |
| 4 | `==` `!=` `<` `<=` `>` `>=` | **não associativa** (`a < b < c` é inválido) |
| 5 | `+` `-` | esquerda |
| 6 | `*` `/` `%` | esquerda |
| 7 | `-` (unário) | prefixo |

### A.7 Léxico

| Categoria                                | Elementos                                                                         |
| ---------------------------------------- | --------------------------------------------------------------------------------- |
| Palavras reservadas (estrutura)          | `home zone device var const group scene rule priority`                            |
| Palavras reservadas (eventos/instruções) | `on when change signal at every if else repeat times for in wait notify activate` |
| Palavras reservadas (valores/operadores) | `true false now and or not`                                                       |
| Tipos                                    | `int real bool string time`                                                       |
| Unidades de tempo                        | `sec min hour`                                                                    |
| `ID`                                     | letra seguida de letras, dígitos ou `_`                                           |
| `INT` / `REAL`                           | `30` / `21.5`                                                                     |
| `STRING`                                 | texto entre aspas `"..."`                                                         |
| `TIME`                                   | `hh:mm`, por exemplo `22:30`                                                      |
| Símbolos                                 | `{ } ( ) [ ] , ; : . = == != < <= > >= + - * / %`                                 |
| Comentários e espaços                    | `//` até ao fim da linha; espaços ignorados                                       |

**Pontos a documentar no léxico:** `TIME` (`22:30`) vs o `:` das declarações; `min`/`sec`/`hour` como palavras reservadas (um `ID` chamado `min` deixa de ser possível); `%` só como operador de resto.

### A.8 Exemplo de programa válido

```
home "Casa" {
  const comfort : real = 21.0;

  zone Living {
    device lamp   : dimmer;
    device heater : thermostat;
    device motion : presence;
    var visits : int = 0;

    zone Corner {
      device reading : dimmer;
    }
  }

  group lights = [ Living.lamp, Living.Corner.reading ];

  scene Night {
    for l in lights {
      l.off();
    }
    notify "Boa noite";
  }

  scene Alert {
    repeat 3 times {
      Living.lamp.on();
      wait 1 sec;
      Living.lamp.off();
      wait 1 sec;
    }
  }

  rule Arrive priority 2 on change Living.motion when Living.motion.detected == true {
    Living.visits = Living.visits + 1;
    if (now > 18:00) {
      Living.lamp.on();
      Living.lamp.brightness = 60;
    } else {
      Living.lamp.on();
    }
  }

  rule Heat on every 10 min when Living.heater.temperature < comfort {
    Living.heater.set(comfort);
  }

  rule Bedtime on at 22:30 {
    activate Night;
  }
}
```


# Estrutura da gramática

## Programa
- Um programa é um único `home "nome" { ... }` com uma lista de declarações lá dentro.

## Declarações (`Decl`)
Seis tipos, que podem aparecer na casa ou dentro de uma zona.

- `zone`: contém outras declarações, por isso as zonas aninham-se (é o mecanismo de âmbitos hierárquicos)
- `device nome : tipo;`: o tipo do dispositivo é um `ID` e fica por validar na semântica
- `var` / `const nome : tipo = expr;`: tipos `int`, `real`, `bool`, `string`, `time`
- `group nome = [ref, ref, ...];`: conjunto de referências, para iterar com `for`
- `scene nome { ... }`: bloco de instruções reutilizável, sem parâmetros
- `rule nome [priority N] on evento [when expr] { ... }`: reação a um evento

## Eventos (`Event`)
Quatro gatilhos.

- `change Ref`: mudança de um dispositivo ou variável
- `signal Ref`: sinal externo (ainda por definir)
- `at TIME`: hora fixa
- `every INT unidade`: periódico (`sec`, `min`, `hour`)

## Instruções (`Stmt`)
Dentro de blocos `{ ... }`.

- Declaração local de `var`/`const`
- Atribuição `Ref = Expr;` (a variáveis ou propriedades)
- Comando a dispositivo `Ref(args);`
- Controlo de fluxo: `if/else` (com `else if`), `repeat N times`, `for x in grupo`
- Domínio: `wait duração;`, `notify "texto";`, `activate cena;`

## Referências
- `Ref` é um caminho com pontos (`Living.Corner.lamp`), recursivo à esquerda
- Serve para dispositivos, variáveis, grupos, cenas e propriedades. Quem decide o que é cada um é a semântica.

## Expressões
Sete níveis, da menor para a maior precedência.

- `or` → `and` → `not` → comparação (não associativa) → `+ -` → `* / %` → menos unário → primário
- Primários: literais (`INT`, `REAL`, `STRING`, `TIME`, `true`, `false`), `now`, `Ref` e parênteses
- A precedência está codificada nos níveis, por isso não há ambiguidade

## Léxico
- Tokens com estrutura: `ID`, `INT`, `REAL`, `STRING`, `TIME`
- Palavras reservadas: estrutura (`home zone device...`), eventos e instruções (`on when if...`), tipos e unidades de tempo
- Comentários com `//`

## O que fica para a semântica
Ou seja, a gramática de atributos.

- Resolução de nomes e âmbitos
- Tipos das expressões
- Validade dos comandos para cada tipo de dispositivo
- `const` não atribuível e `for` só sobre grupos
- `activate` só sobre cenas



### A.9 Programas sintaticamente válidos mas semanticamente inválidos

| Código | Problema | Propriedade |
|---|---|---|
| `Living.sofa.on();` | dispositivo não declarado | resolução de nomes |
| `device lamp : dimmer;` duas vezes na mesma zona | duplicado no âmbito | resolução de nomes |
| `device x : frigorifico;` | tipo de dispositivo desconhecido | catálogo de dispositivos |
| `Living.motion.on();` | comando inexistente para o tipo `presence` | catálogo de dispositivos |
| `Living.lamp.brightness = "alto";` | `string` atribuída a propriedade `int` | tipos |
| `comfort = 22.0;` | atribuição a `const` | mutabilidade |
| `for x in Living { ... }` | `Living` não é grupo | tipos de `Ref` |
| `repeat "tres" times { ... }` | `repeat` exige `int` | tipos |
| `activate Heat;` | `Heat` é regra, não cena | tipos de `Ref` |
| `scene A { activate A; }` | ciclo de cenas | grafo (Parte II) |

---

## Parte B: Notas sobre a Linguagem

### B.1 A mensagem central

> *"A linguagem é pequena na sintaxe e rica na semântica. A complexidade vem de o programa ser **reativo** (eventos), **hierárquico** (zonas aninhadas) e **tipado** (catálogo de dispositivos), e não de termos muitas construções."*

Esta frase responde diretamente ao receio do professor. Convém dizê-la logo no início e voltar a ela na conclusão.

### B.2 Estrutura sugerida (cada slide com tempo)

| # | Slide | Tempo | O que dizer |
|---|---|---|---|
| 1 | Domínio e propósito | 1 min | Quem usa (instalador/utilizador), que problema resolve: detetar erros de configuração *antes* de chegarem ao hub |
| 2 | A linguagem num exemplo | 1,5 min | Mostrar o programa A.8 e apontar os conceitos: zonas, dispositivos, grupos, cenas, regras com evento |
| 3 | Léxico | 0,5 min | Tabela A.7, só os casos delicados (`TIME`, palavras reservadas) |
| 4 | Gramática | 2 min | Estrutura em 3 blocos: declarações / instruções / expressões. Mostrar a precedência |
| 5 | Semântica fora da sintaxe | 2 min | Tabela A.9: cada erro é sintaticamente válido, por isso precisamos de atributos |
| 6 | Gramática de atributos | 1,5 min | `env` herdado, `type` sintetizado, `errors` acumulados, com 2 ou 3 regras de exemplo |
| 7 | Qualidade e conclusão | 1,5 min | Ambiguidade, recursão à esquerda, ligação à Parte II |

Se o tempo apertar, cortem o slide 3 e juntem-no ao 4.


### B.3 O que cobre dos requisitos mínimos

| Requisito | Onde |
|---|---|
| Variáveis e declarações | `var`, `const`, `device`, `group` |
| Scopes | `zone` aninhadas, blocos, variável de `for` |
| Expressões e estado | `Expr`, atribuição a variáveis e propriedades |
| Construções aninhadas | blocos, `if` dentro de `for`, zonas dentro de zonas |
| Ramificação | `if/else`, guarda `when` |
| Repetição | `repeat`, `for`, `every` |
| Semântica não sintática | tabela A.9 |

### B.4 Gramática de atributos: o que apresentar (a "receita")

Para cada propriedade semântica, a pergunta a fazer é *"que informação precisa de viajar, e em que direção?"*

| Propriedade | Atributo | Direção | Porquê |
|---|---|---|---|
| Resolução de nomes | `env` (tabela de símbolos) | **herdado**: do pai para os filhos | o que está visível num ponto depende do que foi declarado *acima* e à volta |
| Declarações de uma zona | `decls` | **sintetizado**: dos filhos para o pai | a zona só sabe o que declara depois de ver o seu conteúdo |
| Tipo de uma expressão | `type` | **sintetizado** | o tipo de `a + b` calcula-se a partir dos tipos de `a` e `b` |
| Erros semânticos | `errors` | sintetizado (ou acumulador global) | recolher problemas ao longo da árvore |

Sugestão de núcleo (para não exagerar): **resolução de nomes + tipos + validade de comandos ao dispositivo**. Cenas, ciclos e conflitos ficam para a Parte II.

**Exemplo de regra a mostrar** (atribuição `Ref '=' Expr ';'`):

```
Stmt → Ref '=' Expr ';'
   Ref.env  = Stmt.env
   Expr.env = Stmt.env
   Stmt.errors = Ref.errors ∪ Expr.errors
                 ∪ ( Ref.type ≠ Expr.type      ? {"tipos incompatíveis"} : ∅ )
                 ∪ ( Ref.isConst               ? {"atribuição a const"}  : ∅ )
```

**Nota prática:** se propagar listas de erros pela árvore ficar pesado, um **acumulador global de erros** é uma alternativa mais simples. Mencionem-na como decisão de desenho e justifiquem.

### B.5 Qualidade da linguagem e da gramática (Tarefa 4)

Pontos prontos a usar, que mostram que a gramática foi pensada:

- **Sem ambiguidade nas expressões:** a precedência está codificada nos níveis (`Expr → AndExpr → NotExpr → RelExpr → AddExpr → MulExpr → Unary → Primary`).
- **Sem *dangling else*:** `if` e `else` exigem sempre `Block` com chavetas. O `else if` é tratado explicitamente em `IfStmt`.
- **Comparações não encadeáveis:** `RelExpr` não é recursiva, por isso `a < b < c` é erro de sintaxe, o que evita um bug de leitura comum.
- **Recursão à esquerda:** presente em `Expr`, `AndExpr`, `AddExpr`, `MulExpr` e `Ref`. É adequada para parsers LR/ascendentes. Para um parser descendente (LL) teria de ser transformada em iteração, e convém dizer qual ferramenta pretendem usar.
- **Fatorização:** `Stmt` tem duas alternativas que começam por `Ref` (atribuição vs comando). Num LL(1) obrigaria a fatorar à esquerda; em LR não há problema.
- **Distinção atribuição vs comando e variável vs propriedade:** é deliberadamente deixada à semântica (a sintaxe só vê `Ref`). É uma boa decisão de projeto, mas tem de ser justificada.
- **Tipo do dispositivo como `ID`:** `device lamp : dimmer` aceita qualquer identificador na gramática. Isto mantém a gramática pequena e extensível, e a verificação passa para o catálogo na semântica.
- **Legibilidade:** palavras-chave em inglês e estrutura próxima do domínio. Pontos fracos a admitir: `min`/`sec`/`hour` ocupam nomes de identificadores.



### B.6 Decisões em aberto

Resolvam antes de apresentar, porque o professor vai perguntar:

1. **Âmbitos:** regras e cenas podem estar dentro de zonas? A gramática diz que sim (`Decl` dentro de `ZoneDecl`). Se sim, como se resolvem `activate Night` e `Ref` de dentro da zona?
2. **Ordem de declaração:** é preciso declarar antes de usar, ou os nomes ao nível da zona são visíveis em qualquer ordem?
3. **Coerção numérica:** `int` pode ser usado onde se espera `real`? (por exemplo `comfort : int` a comparar com `temperature`)
4. **Catálogo de dispositivos:** fixo na linguagem (recomendado) ou declarável? Qual a lista de tipos?
5. **O que é um `signal Ref`?** Evento externo, ou o `Ref` aponta para algo declarado (por exemplo um dispositivo)? Convém definir, porque é a parte mais vaga do enunciado da linguagem.
6. **`wait` dentro de regras:** bloqueia a regra? Isto interessa à Parte II (análise de fluxo).
7. **Quais as propriedades que entram na gramática de atributos** (núcleo vs extras).
