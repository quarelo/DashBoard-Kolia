# Handoff — IA progressiva e fundação RAG

Data: 2026-08-16
Branch: `ia-feature`

## Estado atual

- Serviço local CPU-only usando `gemma3:1b` para summaries e
  `nomic-embed-text` para embeddings.
- Transcrição de pior caso: 40.008 tokens, 48 chunks de 1.000 tokens.
- Pipeline híbrido: extração determinística em 100% dos chunks e no máximo
  15 chunks relevantes/distribuídos enviados ao LLM.
- Resumo preliminar persistido imediatamente.
- Progresso do resumo e dos embeddings exposto separadamente.
- RAG disponível em `POST /analises/{analysis_id}/buscar` depois de todos os
  embeddings terminarem.
- Chatbot continua fora do escopo e é o próximo consumidor provável do RAG.

## Benchmark final

Análise: `0432b055-def1-4304-a815-a3b78373fcf2`

- Resposta aceita/prévia: 0,284 s.
- Parcial com seis inferências: 256,621 s (4min16,6s).
- Resumo completo: 599,841 s (9min59,8s).
- Estado `DONE`, incluindo 48 embeddings: 774,020 s (12min54s).
- Sem erro; resumo e embeddings em 100%.
- Memória máxima amostrada: Ollama 1,204 GiB; IA 74,68 MiB;
  PostgreSQL 49,26 MiB.
- CPU máxima amostrada: Ollama 409,11%; IA 2,18%.
- Relatório local (ignorado pelo Git):
  `ia/logs/endpoint-giant-hybrid15.json`.

## Gates de qualidade validados

- CRM para 25 pessoas.
- Discussão de 20 licenças e 40 usuários.
- Plano para segunda-feira.
- Substituição de 27 máquinas para Windows 11.
- Novo estudo de cloud em março ou abril.
- Busca RAG sobre Windows 11 retorna o chunk 48 em primeiro lugar, contendo
  `27 máquinas`, com similaridade 0,7631.
- Suíte final: 66 testes aprovados.

## Configuração importante

- `MAX_TOKENS_PER_CHUNK=1000`
- `MAX_LLM_CHUNKS=15`
- `PARTIAL_CHUNK_COUNT=6`
- `CHUNK_PROCESSING_CONCURRENCY=1`
- A variante de 2.500 tokens foi abortada: uma chamada levou cerca de dois
  minutos e projetou mais de 30 minutos, portanto chunks maiores pioraram o
  desempenho nesta máquina.

## Decisões e cuidados

- O resumo fica disponível antes dos embeddings; `DONE` representa também a
  prontidão do RAG.
- Resultados do LLM são complementados, e não substituídos, por evidências
  determinísticas para evitar perda de números e prazos explícitos.
- Fatos individuais são limitados a 320 caracteres para impedir respostas
  patológicas do modelo.
- O arquivo `ia/tests/test_analisar.py` contém a fixture gigante, permanece
  não rastreado e não deve ser alterado nem commitado.
- Não reexecutar `rebuild_hybrid_summary.py` repetidamente em produção sem
  necessidade; ele existe para reparar análises híbridas anteriores.

## Próximos passos sugeridos

1. Adicionar autenticação/autorização ao endpoint RAG antes da exposição
   pública.
2. Criar o chatbot usando somente evidências retornadas pelo RAG e citações de
   `chunk_index`.
3. Adicionar métricas persistentes por estágio e exportação para observabilidade.
4. Repetir o benchmark na VPS final e ajustar `MAX_LLM_CHUNKS` conforme CPU.
5. Avaliar redução/estruturação de `metricas_negocio`, que deliberadamente
   retém mais evidências para garantir recall no pior caso.

## Comandos úteis

```bash
docker compose run --rm --no-deps -v "$PWD/ia:/app" ia-service python -m pytest -q
python ia/scripts/endpoint_benchmark.py \
  --input ia/tests/test_analisar.py \
  --output ia/logs/endpoint-giant-hybrid15.json \
  --timeout 1800



```
1. Produto — Identifica qual produto TOTVS está sendo mencionado.

2. Persona — Identifica o perfil profissional envolvido na conversa.

3. Sentimento — Avalia a percepção geral do cliente sobre a reunião.

4. Risco de Churn — Detecta sinais de possível cancelamento ou insatisfação.

5. Oportunidade Comercial — Identifica possibilidades de venda ou expansão de algo já existente no portfolio 

6. Score de Oportunidade — Prioriza oportunidades conforme potencial comercial identificado.

7. Budget — Estima valores financeiros mencionados na negociação.

8. Gap de Produto — Detecta necessidades não atendidas pelo portfólio atual.

9. Problemas Identificados — Resume dores, dificuldades e obstáculos relatados.

10. Feedback do Produto — Avalia opiniões sobre produtos já utilizados.

11. Evidências — Mostra trechos que sustentam cada insight gerado.

12. Recomendação de Ação — Sugere próximos passos baseados nos insights encontrados.

13. Dúvidas em aberto - Encontra dúvidas que não foram esclarecidas para o cliente

## Estado da validação final — 2026-08-19

- Analysis ID da execução completa: `58c36af8-bf0d-4804-936d-67c430f8695b`.
- Entrada: `ia/tests/test_analisar.py`, 40.008 tokens.
- Resultado: `DONE`, 22/22 chunks e 22/22 embeddings.
- Tempo total observado: 1.465,1 s (24min25s).
- Resumos Ollama: 1.347,4 s (22min27s).
- Maior amostra de CPU do Ollama: aproximadamente 401%.
- Maior memória observada: Ollama aproximadamente 1,22 GiB; IA aproximadamente 116 MiB.
- Suíte Docker após as alterações: 73 testes passando.

### Melhorias já aplicadas

- Concorrência padrão de chunks em 2.
- Todos os chunks continuam sendo enviados ao Ollama.
- Prompt diferencia demonstração hipotética de fato real do cliente.
- Churn não considera pedido/ordem cancelada como cancelamento contratual.
- Budget filtra métricas operacionais e busca licenças/orçamento.
- Consolidação cruza resumos com a transcrição original para produto, persona,
  sentimento, gaps e problemas.
- Busca semântica por categorias implementada com pgvector em
  `/analises/{analysis_id}/evidencias`.

### Pendências prioritárias para continuar

1. O campo `budget` ainda retorna parágrafos de licenciamento em vez de valores
   objetivos e quantidades (20/25/40 licenças, valores R$ citados e indicação
   de que não houve orçamento final aprovado).
2. `oportunidade_comercial` ainda confunde temas operacionais (CNPJ e Windows
   11) com venda/expansão TOTVS.
3. `recomendacao_acao` ainda captura frases narrativas e precisa retornar
   somente ações reais, responsáveis e prazos.
4. `evidencias` está saturada por duplicações de produto/persona; reservar
   espaço para budget, gaps, problemas e decisões.
5. `feedback_produto` ainda está fraco e deve incluir elogios à integração,
   modo offline e dashboards, além das críticas de customização/importação.

Ao retomar, usar o mesmo Analysis ID/JSON final como baseline e não repetir a
execução de 24 minutos sem antes testar essas correções em unitários e em uma
amostra de chunks.
