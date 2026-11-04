# Qualidade da linguagem e da gramática (Tarefa 4)

Os valores da gramática são calculados por `python qualidade.py`, a partir de `domo.lark` e da bateria de testes.
Sempre que a gramática mudar, volte a correr o script e atualize as tabelas.

**Conclusão.** A gramática é correta, não ambígua e totalmente coberta pelos testes. A linguagem é pequena e cumpre o objetivo de detetar erros antes de chegar à casa. O ponto fraco principal é de ortogonalidade (construções que só aceitam literais), e não de sintaxe.

## 1. Qualidade da gramática

### Correção

| Propriedade | Resultado | Como se verifica |
|---|---|---|
| Gramática reduzida | Sim: todos os não-terminais são alcançáveis e produtivos, e todos os terminais são usados | Análise do grafo de produções |
| Não ambiguidade | Sim: LALR(1) com 0 conflitos shift/reduce e 0 reduce/reduce | Uma gramática LALR(1) sem conflitos é não ambígua |
| Fiabilidade do detetor de conflitos | Encontra 1 conflito numa gramática de controlo com *dangling else* | Evita concluir "0 conflitos" a partir de um detetor que não funciona |
| Conformidade com o relatório | 38 palavras reservadas (Tabela 9) e 22 símbolos (Tabela 11), iguais aos da gramática | Comparação automática |
| Cobertura pelos testes | 97/97 produções exercitadas | Árvores de derivação dos programas de teste |

### Dimensão e complexidade

| Métrica | Valor | Leitura |
|---|---|---|
| Terminais / não-terminais / produções | 65 / 41 / 97 | Escala adequada a uma linguagem pequena |
| RHS médio / máximo | 2,06 / 8 | O máximo é `group_decl`, pela sua pontuação |
| Alternativas por regra (média / máximo) | 2,37 / 9 | O máximo é `stmt` e `primary`, uma alternativa por instrução ou por forma de valor |
| Produções vazias | 9 | Consequência de escrever opcionais e listas em BNF puro |
| Produções unitárias | 25 | Sobretudo a cadeia de precedência das expressões e `decl`/`stmt` |
| Impureza de árvore (TIMP) | 4,1% | Quase uma árvore: as regras dependem pouco umas das outras |
| Níveis (CLEV) | 58,5% (24 níveis) | Boa separação em camadas |
| Níveis recursivos (NSLEV) | 3 | Os esperados: instruções, expressões e zonas |
| Maior nível (DEP) | 9 | Instruções compostas: `block`, `stmt`, `if_stmt`, etc. |
| Altura (HEI) | 11 | Dominada pelos níveis de precedência das expressões |

### Classe da gramática e decisões

- **A gramática é LALR(1) mas não LL(1), por opção.** A recursão à esquerda em `expr`, `and_expr`, `add_expr` e `mul_expr` dá associatividade à esquerda sem regras adicionais. Em `stmt`, a atribuição e o comando começam ambos por `ref`, e `rel_expr` tem o mesmo tipo de conflito com `add_expr`. Um analisador LALR resolve estes casos sem fatorizar a gramática.
- **A precedência está na própria gramática**, numa regra por nível. O custo é a altura e as produções unitárias. Os prefixos `?` e `_` do Lark evitam que esse custo chegue à árvore.
- **Os operadores relacionais não são associativos**, por isso `1 < 2 < 3` é erro de sintaxe, em vez de uma comparação entre `bool` e `int` para a semântica rejeitar.
- **A gramática é permissiva de propósito.** Os tipos de dispositivo e os membros são `ID`, e `ref` é um caminho genérico, pelo que acrescentar um tipo ao catálogo não altera a gramática. O custo é que `Hall.door.lock` tem a mesma forma para zona, dispositivo e comando, e só a semântica os distingue.
- **As chavetas obrigatórias eliminam o *dangling else*.** A gramática de controlo mostra o conflito que a linguagem evita.

### Sensibilidade a erros de escrita

Apagou-se cada um dos 472 tokens de `03_full.domo`, um de cada vez:

| Fase que deteta | Mutantes | % |
|---|---:|---:|
| Sintática | 466 | 98,7% |
| Semântica | 1 | 0,2% |
| Não detetado | 5 | 1,1% |

Os 5 mutantes não detetados são programas válidos com outro significado: remover `not` (2), o `-` de `-1.5`, o `else` de `else if`, e `comfort` em `comfort - heater.current_temp`, que passa a menos unário. Nenhuma gramática os pode rejeitar.

Esta medida avalia a redundância da sintaxe, não a análise semântica, que quase não é posta à prova ao apagar tokens. A semântica é avaliada na secção seguinte.

## 2. Qualidade da linguagem

| Critério | Avaliação | Pontos fortes | Limitações |
|---|---|---|---|
| Adequação ao domínio | Boa | Zonas, dispositivos, regras ECA, `time`, `wait` e `every` são construções da linguagem. O raciocínio "quando X, se Y, faz Z" escreve-se diretamente | `at` não distingue dias da semana (limitação assumida) |
| Legibilidade | Boa | Palavras-chave em vez de símbolos. `rule r on signal x when y { ... }` lê-se como a regra que exprime. Chavetas obrigatórias | O `.` serve para zonas, dispositivos e membros |
| Simplicidade | Boa | 38 palavras reservadas, 5 tipos, 8 tipos de dispositivo, sem funções nem tipos do utilizador | Alguns nomes naturais estão reservados: `on`, `at`, `min`, `time` |
| Ortogonalidade | Média | `if`, `when`, `repeat` e `for` não exigem parênteses, de forma uniforme | Ver "Construções que só aceitam literais" |
| Fiabilidade | Boa | Os 15 códigos da Tabela 8 são detetados antes da execução. Cada execução de regra termina, por não haver `while` e por as cenas não poderem ser cíclicas | Ver "Erros ainda não detetados" |
| Extensibilidade | Boa | Um novo tipo de dispositivo só altera o catálogo | A gramática aceita comandos com vários argumentos, mas nenhum comando do catálogo os usa ainda |

### Construções que só aceitam literais

Testado: estes casos são erros de sintaxe, embora `repeat n times` aceite uma expressão.

| Construção | Efeito |
|---|---|
| `notify m;` com `m : string` | Só aceita um texto literal, por isso o tipo `string` quase não tem utilidade: nenhum comando recebe `string` |
| `on at t` com `t : time` | Obriga a repetir a hora. O Anexo A declara `const morning = 07:00` e depois escreve `on at 07:00` |
| `wait n min`, `on every n min` | Não é possível parametrizar durações com uma constante |

O caso de `at` e `every` tem uma justificação possível: um valor conhecido em compilação simplifica o agendamento. Mas essa justificação suportaria uma `const`, que também é conhecida em compilação, e não só um literal.

### Erros ainda não detetados

Testado: estes programas são aceites.

| Programa | Observação |
|---|---|
| `lamp.brightness = n;` com `n` variável | O intervalo só se verifica quando o valor é conhecido antes da execução, como em `lamp.brightness = 150;` (`outOfRange`) |
| `x = 1 / n;` com `n` variável | Pela mesma razão, só se rejeita um divisor conhecido, como em `1 / 0` (`divisionByZero`). A linguagem ainda não define o que acontece na execução |
| `repeat -1 times { }` | A semântica de uma contagem negativa não está definida |
| `group g = [a, a];` | O relatório não decide sobre elementos repetidos |
| Ciclos entre regras | Assumido no relatório e deixado para a Parte II |

### Pequenas incoerências de desenho

- **"Um só mecanismo por alteração" (Tabela 7):** `lamp.brightness = 40` e `lamp.fade_to(40)` alteram ambos `brightness`. A diferença é a transição gradual, mas convém dizê-lo para a afirmação não parecer contraditória.
- **Catálogo:** `light` e `dimmer` têm `toggle()`, mas `plug` não.
- **Concatenação de strings:** o verificador aceita `"a" + "b"`, mas o relatório não a define e, como `notify` só aceita literais, o resultado quase não tem uso.

## 3. Melhorias propostas, por prioridade

1. Permitir uma expressão em `notify`, ou pelo menos uma referência a `string`. Dá utilidade ao tipo `string`.
2. Aceitar uma constante em `at`, `every` e `wait`, verificada na semântica.
3. Definir o comportamento na execução de `repeat` com contagem negativa, de uma divisão por uma variável com valor zero e de um valor fora do intervalo.
