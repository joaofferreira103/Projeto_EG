# Teste do LarkAG (Fase 0 da Parte II)

Objetivo: decidir se a gramática de atributos da Parte I ([GRAMATICA_ATRIBUTOS.md](../../docs/GRAMATICA_ATRIBUTOS.md)) pode ser escrita e executada com o [LarkAG](https://pypi.org/project/lark-ag) (`lark-ag 1.0.2`, Faria, Baptista e Henriques, SLATE 2024), em vez de `semantic.py`.

```
pip install --no-deps lark-ag==1.0.2      # --no-deps mantém lark==1.3.1
python experimentos/larkag/spike_larkag.py
```

O teste usa um subconjunto do Domo: declarações `var` com tipo, `+`, literais e nomes, com os atributos `decls`, `env` e `type` e os erros `typeMismatch` e `undeclared` como condições de contexto (`CC`).

## Resultados

| Critério | Resultado |
|---|---|
| Funciona com `lark==1.3.1` | Sim |
| Aceita `domo.lark` | **Não.** `?regra`, `_regra` e `-> alias` são rejeitados, e cada alternativa tem de ter um bloco `ER{}`. Os nomes de regra com `_` (`zone_decl`, `var_decl`, `and_expr`...) partem o código gerado, que identifica o símbolo por `node.data.split('_')[0]`. |
| Parser LALR + lexer `basic` | **Não.** O parser é sempre `Lark(grammar)`: Earley com lexer dinâmico, sem opções. As palavras reservadas deixam de ser garantidas pelo lexer, e as 0 conflitos LALR da Parte I deixam de se aplicar. |
| Atributos L-atribuídos (blocos do Domo) | Sim, mas só depois de reordenar as equações à mão (ver abaixo). |
| Atributos não L-atribuídos (zonas do Domo: `env` depende de `decls` do próprio nó) | **Não.** O avaliador visita cada filho uma só vez. O ciclo de dependências não é detetado: o código gerado lê `decls` antes de o calcular e dá `AttributeError`. |
| Vários erros num programa | **Não.** Uma `CC` falhada lança uma exceção e a avaliação para no primeiro erro. |
| Posição (linha/coluna) dos erros | **Não.** As `CC` têm só uma mensagem fixa, e o parser não guarda posições. |

Bugs encontrados no gerador:

1. **Equações perdidas.** Uma equação `filho.herdado = ...` em que o filho aparece pela primeira vez é substituída pela visita ao filho, porque ambas ficam guardadas na mesma chave. Contorno: escrever antes uma equação que leia um atributo sintetizado desse filho.
2. **Tokens repetidos.** Um token referido duas vezes na mesma equação (`str(TYPE) ... str(TYPE)`) é substituído duas vezes e gera Python inválido. Contorno: `(lambda t: ...)(str(TYPE))`.
3. Não se pode escrever `ID.value`, porque `.value` é lido como um atributo. Usa-se `str(ID)`.
4. O código das equações tem de caber numa linha e não pode conter `;` nem `->`.

## Decisão

Ficamos com a semântica em Python ([semantic.py](../../domo/semantic.py)). Para usar o LarkAG teríamos de:
- reescrever a gramática e mudar de LALR para Earley, perdendo resultados da Parte I;
- deixar de detetar vários erros com a sua posição;
- deixar de suportar a ordem livre das declarações nas zonas, que é uma decisão central da linguagem.

O LarkAG serve para as partes L-atribuídas, como os tipos das expressões dentro dos blocos. Uma demonstração pequena nesse subconjunto continua possível, se for útil para o relatório.
