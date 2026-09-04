## 2026-08-25 (continuação) — Sessão 21: a IA passa a agir, com você confirmando

Retomada para a Fase 3. Terminou com "sobe o kiteasy" ligando o ambiente —
depois de um clique em Confirmar.

### Medi antes de construir, porque o desenho dependia disso

Duas perguntas que decidiam se a Fase 3.4 se sustentava num provedor local. Um
modelo pequeno consegue escolher uma ação de um registro fechado? E consegue
achar o projeto certo entre os 18 cadastrados?

| | Escolher a ação | Recusar o que não existe | Achar o projeto |
|---|---|---|---|
| `qwen2.5-coder:3b` | 5 de 6 | **falhou** — propôs `environment.up` para "deploy em produção" | — |
| `qwen2.5-coder:7b` | 6 de 6 | acertou | **7 de 7** |

O 7b corrigiu "smartdah" para `smartdash` e recusou projeto inexistente. Isso
**valida a sua escolha dele como padrão** — que a medição anterior não tinha
sustentado. Rotear é tarefa muito mais fácil que diagnosticar, e é justamente
na parte perigosa (recusar o que não existe) que o modelo maior ganha.

### O desenho

`app/services/ai/actions.py` é um catálogo fechado de doze coisas que o painel
**já faz por botão**, cada uma apontando para a rota daquele botão. Um teste
confere contra o OpenAPI que nenhuma aponta para rota inexistente.

O fluxo é: o modelo escolhe um nome da lista → o servidor valida → a tela
mostra e você confirma → a execução vai pela rota de sempre. A IA não ganha
caminho de execução próprio, que é a defesa D-A3 ao pé da letra.

Vira recusa, nunca ação aproximada: nome fora do registro, projeto inventado,
JSON quebrado, e ação que precisa de projeto sem projeto resolvido.

O erro que mais preocupava — ação certa no **projeto errado** — tem teste
próprio: com dois projetos "OperaLaby ..." cadastrados, "sobe o operalaby" não
propõe nada. Propor no projeto errado é pior que não propor, porque parece que
funcionou.

### Regra primeiro, modelo no empate

Medido contra o painel real:

| Frase | Tempo | Caminho |
|---|---|---|
| `sobe o kiteasy` | **0,2 s** | regra |
| `abre o site3d no vscode` | 0,2 s | regra |
| `sobe o smartdah` | 15,6 s | modelo, corrigindo o nome |
| `como desfaço um commit?` | — | sem proposta; vira pergunta normal |
| `faz o deploy em produção` | — | recusado, não existe no registro |

Num provedor local, 0,2 s contra 15 s é a diferença entre usar e não usar. E a
regra é código: funciona com o Ollama fechado.

### Um defeito de isolamento achado de brinde

Dois testes de IA começaram a falhar. Causa: `Settings` lê `DEVCOCKPIT_*` do
ambiente, e esta máquina agora tem essas variáveis definidas. A suíte estava
afirmando algo sobre **a configuração da máquina** em vez de sobre o código —
passaria em qualquer outra. Uma fixture autouse limpa as variáveis antes de
cada teste.

### O empacotamento

O `Remove-Item` falhou com `VCRUNTIME140.dll` travada. Desta vez o culpado não
era o próprio app: era o **VS Code**, com a DLL carregada. Fechar o editor de
quem está trabalhando não é opção, então conferi o hash — idêntica nos dois
builds — e copiei o resto com `robocopy`, verificando arquivo por arquivo que a
instalação ficou idêntica ao build.

635 testes (24 novos), `ruff` limpo, app no ar na 8765.

### Continua com você

- [ ] **decidir o modelo padrão.** `setx OLLAMA_KEEP_ALIVE 60m` segura o 7b na
      RAM (custa 5 GB presos, resolve os 143 s frios, não os 34 s quentes); ou
      voltar o 3b, que responde em 0,7 s quente
- [ ] `ollama rm llama3.2:3b` e `llama3.2:1b` — 3,3 GB parados
- [ ] **Fase 3, o que falta**: perfis de especialista, command palette (`/plan`,
      `/find-bugs`), e `actor="ai"` ponta a ponta na auditoria — hoje a
      execução da ação confirmada é registrada como ação do usuário, que é
      verdade parcial: quem propôs foi a IA
- [ ] o painel não gerencia o Ollama (modelos, o que está na RAM, descarregar)
- [ ] `Dockerfile`, `docker-compose.yml` e `.dockerignore` seguem sem decisão
- [ ] conferir a aba Docker com o Docker Desktop **desligado** (desde 21/08)

---

