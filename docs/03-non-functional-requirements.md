# 03 — Requisitos Não Funcionais

## Segurança

| ID | Requisito |
|----|-----------|
| NFR-001 | O servidor HTTP escuta exclusivamente em `127.0.0.1`. Bind em `0.0.0.0` é bloqueado no código, não apenas na configuração. |
| NFR-002 | Nenhum endpoint aceita comando, argumento livre ou fragmento de shell vindo do cliente. |
| NFR-003 | Todo comando é montado como lista de argumentos (argv) e executado sem shell. `shell=True` é proibido. |
| NFR-004 | Todo path recebido é canonicalizado e validado contra uma allowlist de diretórios raiz antes de qualquer uso. |
| NFR-005 | Symlink que aponte para fora dos roots permitidos é rejeitado. |
| NFR-006 | Requisições que alteram estado exigem cabeçalho de origem próprio (proteção CSRF), porque o browser do usuário alcança `localhost`. |
| NFR-007 | Segredos nunca em código nem em banco em texto claro. Apenas em `.env`, fora do versionamento. |
| NFR-008 | Mensagem de erro devolvida ao cliente não expõe path de sistema fora do escopo do projeto nem conteúdo de variável de ambiente. |

## Performance

| ID | Requisito |
|----|-----------|
| NFR-010 | `GET /api/dashboard` responde em menos de 500 ms com 30 projetos, servindo de cache. |
| NFR-011 | Nenhuma requisição HTTP executa varredura de disco síncrona e ilimitada. |
| NFR-012 | Varredura de descoberta limita profundidade (padrão 3) e ignora diretórios de dependência. |
| NFR-013 | Health check tem timeout individual de 2 s e as verificações rodam concorrentemente. |
| NFR-014 | Resultado de comando de leitura (git status, docker ps) é cacheado com TTL curto (padrão 5 s) para absorver rajadas da UI. |

## Manutenibilidade

| ID | Requisito |
|----|-----------|
| NFR-020 | A camada HTTP não conhece `subprocess`, path de SO nem sintaxe de comando. |
| NFR-021 | Nenhum módulo passa de cerca de 300 linhas. Nenhuma função passa de cerca de 40 linhas. |
| NFR-022 | Toda porta, path e timeout vem de configuração. Nada hardcoded. |
| NFR-023 | Adapters de Git, Docker e SO são substituíveis por implementação fake nos testes. |
| NFR-024 | Toda decisão arquitetural relevante tem ADR correspondente. |

## Testabilidade

| ID | Requisito |
|----|-----------|
| NFR-030 | Cobertura mínima de 70% em `services/`, `runner/` e `detection/`. |
| NFR-031 | Nenhum teste unitário executa comando real de SO, Git ou Docker. |
| NFR-032 | Teste de integração que usa Git real opera em repositório temporário criado pelo próprio teste. |
| NFR-033 | Teste que exige Docker é marcado e pode ser desativado por marcador do pytest. |

## Portabilidade

| ID | Requisito |
|----|-----------|
| NFR-040 | Windows é a plataforma primária de referência. Linux e macOS funcionam por implementações alternativas do `OSAdapter`. |
| NFR-041 | Nenhum separador de path escrito à mão. Uso obrigatório de `pathlib`. |
| NFR-042 | Ausência de `git`, `docker` ou `code` degrada a funcionalidade correspondente sem derrubar a aplicação. |

## Observabilidade e logging

| ID | Requisito |
|----|-----------|
| NFR-050 | Log estruturado em JSON, em arquivo, com nível configurável. |
| NFR-051 | Toda execução de comando registra argv, código de saída e duração. |
| NFR-052 | Erro não tratado retorna 500 com identificador de correlação também presente no log. |

## Resiliência

| ID | Requisito |
|----|-----------|
| NFR-060 | Falha de um adapter, por exemplo Docker fora do ar, não impede a resposta dos demais dados. |
| NFR-061 | Todo comando externo tem timeout obrigatório. Processo travado é encerrado. |
| NFR-062 | Projeto cujo diretório foi movido ou apagado é marcado como `MISSING` e não causa erro em cascata. |

## Developer Experience do próprio DevCockpit

| ID | Requisito |
|----|-----------|
| NFR-070 | Subir o projeto em desenvolvimento exige um comando único. |
| NFR-071 | O frontend não tem etapa de build no MVP. ES modules servidos direto. |
| NFR-072 | Schema do banco versionado por migração desde a primeira versão. |
| NFR-073 | O `README.md` permite a um dev novo rodar o projeto em menos de 5 minutos. |
