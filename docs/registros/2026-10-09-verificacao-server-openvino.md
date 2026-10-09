# Verificação de experimentos-openvino/server.py (2026-10-09)

- Base: `ab5323e` (branch `claude/gallant-mccarthy-3ds9oz`). O SHA do commit da correção está na descrição do PR.
- Escopo: início, erro e encerramento do servidor, com stubs sintéticos (sem modelo, rede ou chaves).

## Defeito encontrado (1)
Falha ao carregar o modelo imprimia "ERRO CRÍTICO" e chamava `exit()` sem argumento:
o processo terminava com **código 0** (sucesso), então supervisores/scripts não detectavam a falha.
Além disso `exit()` é do módulo `site` (indisponível com `python -S`) e a mensagem ia para stdout.

Correção: `sys.exit(1)` e mensagem em stderr.

## Comandos e resultados
- `python3 -I <repro com stubs>` antes da correção: `SystemExit code: None`, rc=0 (defeito reproduzido).
- `pip install pytest numpy` (dependências do CI).
- `python3 -m pytest -q test` antes: 9 passed. Depois: 11 passed.
- Novo `test/test_server_encerramento.py`: sem a correção o teste de falha **falha**; com ela passa.

## Limitações
- OpenVINO, optimum, transformers, fastapi e uvicorn foram substituídos por stubs; endpoint
  `/v1/chat/completions`, GPU real e `uvicorn.run` não foram exercitados.
- Não verificados (só lidos): `apply_chat_template` com `msg.dict()` (depreciado no pydantic v2),
  `split("<|assistant|>")` e `usage` zerado — não são defeitos de início/erro/encerramento.
