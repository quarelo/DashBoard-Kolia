# API de Chat RAG por Reunião — Design

## Objetivo

Criar uma API de perguntas e respostas vinculada a uma análise de reunião. A
API deve aceitar histórico curto na própria requisição, recuperar evidências
somente da reunião indicada e produzir respostas rápidas, citadas e estritamente
fundamentadas. Quando a transcrição não sustentar uma resposta, a API deve dizer
que não encontrou essa informação em vez de completar lacunas.

## Escopo

Esta primeira entrega inclui somente a API do serviço `ia-service` e seus testes
unitários/de rota. Não inclui frontend, persistência de sessões ou mensagens,
streaming, autenticação nova, nem reprocessamento da transcrição gigante.

## Contrato HTTP

### Requisição

`POST /analises/{analysis_id}/chat`

```json
{
  "question": "Quantas licenças foram discutidas?",
  "history": [
    {"role": "user", "content": "Qual produto foi apresentado?"},
    {"role": "assistant", "content": "Foi apresentado o CRM."}
  ],
  "top_k": 4
}
```

Regras de entrada:

- `question`: entre 2 e 500 caracteres após remoção de espaços externos;
- `history`: opcional, no máximo 6 mensagens, somente papéis `user` e
  `assistant`, com até 1.000 caracteres por mensagem;
- o histórico deve alternar papéis e terminar com uma resposta do assistente;
- `top_k`: de 1 a 6, com padrão 4.

### Resposta

```json
{
  "analysis_id": "uuid",
  "answer": "Foram discutidas 20 licenças para vendedores e uma estimativa de 25 usuários para o CRM.",
  "citations": [
    {
      "chunk_id": "uuid",
      "chunk_index": 21,
      "excerpt": "trecho recuperado da transcrição",
      "similarity": 0.81
    }
  ],
  "grounded": true,
  "fallback_reason": null
}
```

`grounded` será verdadeiro somente quando houver evidência semanticamente
aceitável e a resposta tiver sido gerada a partir dela. Uma resposta sem base
terá `grounded=false`, nenhuma citação e uma razão de fallback estável.

## Arquitetura e fluxo

1. A rota valida a entrada e confirma que a análise existe e está `DONE` com
   todos os embeddings prontos.
2. Uma consulta semântica é formada pela pergunta atual mais uma reformulação
   curta e determinística baseada no histórico. O histórico não é enviado ao
   modelo de embeddings como diálogo completo.
3. O RAG recupera até `top_k` chunks exclusivamente pelo `analysis_id`.
4. Evidências abaixo do limiar configurável de similaridade são descartadas.
5. Se nenhuma evidência sobreviver, a API responde imediatamente que a
   informação não foi encontrada, sem chamar o modelo gerador.
6. Com evidências válidas, o serviço monta um prompt contendo instruções,
   histórico limitado, trechos numerados e a pergunta.
7. O Ollama faz uma única geração curta com temperatura baixa, modo de
   raciocínio desativado e limite de saída próprio do chat.
8. A resposta retorna somente as citações recuperadas que foram disponibilizadas
   ao modelo. O modelo nunca pode inventar índices de chunks.

O serviço terá responsabilidades separadas:

- `rag_service`: recuperação e filtro das evidências da análise;
- novo `chat_service`: reformulação da consulta, montagem segura do prompt,
  política de fallback e chamada ao LLM;
- `llm_service`: operação genérica de geração textual configurada para chat;
- schemas e rota: validação e tradução de erros para HTTP.

## Qualidade, velocidade e contexto

O ponto inicial será uma janela efetiva de 8.192 tokens no Ollama. A chamada de
chat reservará no máximo 512 tokens para saída. O prompt usará no máximo seis
mensagens recentes e quatro evidências, com tamanho limitado, mantendo margem
para instruções e tokenização.

O caminho normal executará exatamente uma geração de embedding e uma geração de
texto. Não haverá segunda chamada automática para crítica ou reparo, pois isso
duplicaria a latência na máquina CPU-only. Respostas curtas e temperatura entre
0 e 0,2 serão usadas para favorecer consistência.

O modelo inicial continuará configurável. O baseline será o modelo já instalado
no ambiente, sem exigir download durante a implementação ou os testes.

## Prevenção de alucinação

O sistema não confiará somente no prompt. A política terá barreiras anteriores e
posteriores à geração:

- isolamento obrigatório por `analysis_id` em toda consulta ao banco;
- limiar mínimo configurável de similaridade;
- fallback imediato quando não houver evidência suficiente;
- instrução explícita para não usar conhecimento externo nem inferir valores,
  nomes, responsáveis ou datas;
- transcrição delimitada como dado não confiável, impedindo que instruções
  encontradas nos chunks substituam as regras do sistema;
- resposta limitada às evidências enviadas;
- citações construídas pelo servidor, nunca aceitas livremente do texto do
  modelo;
- validação pós-geração para resposta vazia, erro, timeout ou texto incompatível
  com a política de desconhecimento.

Mensagem padrão quando a informação não existir:

`Não encontrei essa informação na transcrição desta reunião.`

Não é possível garantir matematicamente zero alucinação em um modelo generativo.
Este contrato reduz o risco e torna explícito que respostas sem suporte devem
virar desconhecimento. Métricas futuras poderão medir respostas não sustentadas.

## Fallbacks e erros

- análise inexistente: HTTP 404;
- análise ou embeddings ainda não prontos: HTTP 409;
- entrada inválida: HTTP 422;
- nenhuma evidência acima do limiar: HTTP 200, `grounded=false`,
  `fallback_reason="insufficient_evidence"`;
- timeout, indisponibilidade ou resposta vazia do Ollama: HTTP 200 com a mensagem
  segura, `grounded=false` e `fallback_reason="model_unavailable"`;
- erro inesperado de infraestrutura fora desses casos: HTTP 503, sem expor
  detalhes internos.

O fallback de indisponibilidade não tentará responder usando apenas similaridade,
porque os trechos recuperados podem não resolver corretamente a pergunta.

## Testes e baseline de reunião

O desenvolvimento seguirá TDD. Cada comportamento terá teste falhando antes da
implementação. Os testes não executarão novamente o benchmark de 24 minutos e
não dependerão de um Ollama real.

Testes unitários cobrirão:

- validação e limites do contrato;
- isolamento da busca por `analysis_id`;
- reformulação de perguntas de continuação usando histórico;
- limite de mensagens e evidências no prompt;
- resistência a instruções maliciosas dentro da transcrição;
- filtro pelo limiar de similaridade;
- fallback sem chamada ao LLM quando faltarem evidências;
- timeout, indisponibilidade e resposta vazia do modelo;
- resposta fundamentada com citações fornecidas pelo servidor.

Testes da rota cobrirão sucesso, 404, 409, 422 e fallbacks HTTP 200.

A transcrição grande existente será usada como catálogo de casos de regressão,
com fixtures pequenas extraídas dos fatos já validados:

- CRM estimado para 25 pessoas;
- 20 vendedores e discussão de 40 usuários;
- plano/proposta para segunda-feira;
- substituição de 27 máquinas por incompatibilidade com Windows 11;
- novo estudo de cloud em março ou abril;
- pergunta sem resposta que obrigatoriamente deve retornar desconhecimento.

Essas fixtures permitem corrigir erros de recuperação e resposta rapidamente sem
alterar ou executar integralmente `ia/tests/test_analisar.py`.

## Configuração

Serão adicionadas configurações explícitas e documentadas para:

- contexto do Ollama: 8.192 tokens;
- saída máxima do chat: 512 tokens;
- temperatura do chat: baixa;
- máximo de mensagens: 6;
- máximo de evidências: 6, padrão 4;
- tamanho máximo de cada evidência;
- limiar mínimo de similaridade;
- timeout de geração do chat.

O `NUM_CTX` atualmente solto no `.env` não será tratado como fonte efetiva. A
configuração do Compose e as opções enviadas ao Ollama terão nomes consistentes.

## Critérios de aceite

- uma pergunta sustentada retorna resposta, `grounded=true` e ao menos uma
  citação pertencente à análise solicitada;
- perguntas de continuação podem usar até seis mensagens enviadas pelo cliente;
- perguntas sem sustentação não chamam o gerador e retornam a mensagem padrão;
- falhas conhecidas do Ollama retornam fallback seguro;
- nenhuma evidência de outra análise pode aparecer na resposta;
- todos os novos testes e a suíte existente passam;
- os casos conhecidos da reunião gigante permanecem cobertos por regressões
  rápidas e determinísticas.
