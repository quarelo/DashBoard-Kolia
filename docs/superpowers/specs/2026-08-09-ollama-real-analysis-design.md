# Integração real da análise com Ollama

## Objetivo

Substituir os resumos e embeddings mockados do serviço FastAPI por chamadas
reais ao Ollama, mantendo os contratos HTTP e a persistência existentes.

## Configuração de modelos

O modelo gerador é definido por `OLLAMA_MODEL` no `.env`. O Docker Compose
repassa esse valor ao container como `MODEL`, lido no Python por
`settings.model`. Não haverá nome de modelo fixo no código.

O modelo de embeddings continua separado, definido por `EMBEDDING_MODEL` e
repassado ao container com o mesmo nome.

## Instalação e ausência de modelo

O FastAPI não baixa modelos durante o startup ou durante uma requisição. Se o
modelo configurado estiver ausente, a análise termina com status `FAILED` e
uma mensagem orientando a execução de `./ia/install-model.sh`.

O instalador lê `OLLAMA_MODEL` do `.env`, consulta os modelos instalados e,
quando o modelo estiver ausente, oferece ao operador:

1. baixar o modelo configurado;
2. escolher outro modelo e atualizar `OLLAMA_MODEL` no `.env`;
3. cancelar.

O mesmo fluxo é aplicado ao `EMBEDDING_MODEL` necessário para embeddings.

## Fluxo da análise

Para cada chunk sanitizado, o serviço chama `/api/generate` com resposta em
JSON e valida o formato retornado. Em seguida chama `/api/embed` e valida se o
vetor tem exatamente `EMBEDDING_DIM` dimensões. Cada resumo e embedding é
persistido em `ai.meeting_chunks`.

Após processar os chunks, o serviço envia os resumos parciais ao modelo para
obter a consolidação final e persiste o resultado em
`ai.meeting_analyses.final_summary`.

## Contratos e erros

As funções de integração têm timeouts explícitos e propagam mensagens úteis
para indisponibilidade do Ollama, modelo ausente, JSON inválido e dimensão de
embedding incompatível. Qualquer falha marca a análise como `FAILED`; não há
fallback silencioso para dados mockados.

## Testes

Os testes unitários usam um transporte HTTP controlado para validar payloads,
parsing, erros e dimensão do embedding sem depender de rede. A validação
end-to-end usa os containers reais, executa `/analisar` e confirma no Postgres
que resumo e embedding vieram do fluxo real.
