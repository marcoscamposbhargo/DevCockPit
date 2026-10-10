# Política de segurança

O DevCockpit executa comandos na máquina de quem o usa. Isso é o produto — e é o
risco. Esta página diz o que ele garante, o que ele deliberadamente **não**
garante, e como avisar quando algo estiver errado.

## Reportar uma vulnerabilidade

**Não abra issue pública para falha de segurança.** Uma issue é indexada em
minutos e expõe quem já tem o painel instalado antes de existir correção.

Use um destes canais privados:

1. **GitHub Security Advisories** — aba *Security* › *Report a vulnerability*.
   É o caminho preferido: fica privado até a correção sair e gera CVE se for o
   caso.
2. **E-mail** — `marcoscamposaf@gmail.com`, com `[SECURITY]` no assunto.

Inclua, se possível: versão do DevCockpit, sistema operacional, passos para
reproduzir e o impacto que você enxerga. Prova de conceito ajuda muito.

**O que esperar:** este é um projeto pessoal, mantido por uma pessoa, sem
SLA. O compromisso honesto é responder em até 7 dias e, se a falha for
confirmada, publicar a correção e o aviso creditando quem reportou — a menos
que você prefira anonimato.

## O modelo de segurança

Quatro garantias estruturais, cada uma verificada por teste automatizado que
falha o build se a garantia cair:

1. **Escuta só em `127.0.0.1`.** Validado no código, não na configuração. Não
   existe opção para expor na rede.
2. **Nenhum comando vem do cliente.** A interface envia identificador de ação
   (`docker.up`); a tradução para argv é tabela fixa no código. Não existe
   endpoint que receba uma linha de comando. Execução sempre sem shell.
3. **Todo caminho é validado** contra uma allowlist de diretórios raiz, com
   resolução de symlink. A allowlist só é editável no disco, nunca pela API.
4. **`Host` e `Origin` validados** — fecha DNS rebinding, que é o ataque que
   derrota a checagem ingênua de origem.

O modelo completo, com ameaças numeradas, defesas e testes obrigatórios, está
em [`docs/07-security-model.md`](docs/07-security-model.md).

### Na camada de IA

5. **A IA não ganha capacidade nova.** `app/services/ai/actions.py` é um
   catálogo fechado: cada ação que o modelo pode propor aponta para uma rota
   que já existe como botão do painel. Um teste confere cada entrada contra o
   OpenAPI. Nome fora do catálogo vira recusa, nunca uma ação aproximada.
6. **Chave de API só no ambiente.** Nunca no banco, nunca no frontend, nunca em
   log. `configs/ai.yml` nomeia a *variável*; a carga do arquivo recusa
   qualquer campo com valor parecido com chave. Testes varrem as respostas das
   rotas e o HTML servido atrás da chave — inclusive fatias dela, que é o que
   um mascaramento parcial deixaria escapar.
7. **Pergunta marcada como privada não sai da máquina.** Vai para modelo local,
   sempre. Sem modelo local disponível, é recusada com explicação — nunca
   promovida para a nuvem, nem com pedido manual em contrário.

## Riscos conhecidos e aceitos

Estes **não** são vulnerabilidades: são consequências do que o produto é. Estão
aqui para você decidir com informação, não para serem reportados.

| Risco | Por que é aceito |
|---|---|
| Quem tem acesso ao seu usuário no SO controla o painel | Ele roda como você, na sua máquina. Não há autenticação porque não há fronteira a defender: quem chegou no seu usuário já tem mais poder que o painel. |
| O painel lê o conteúdo dos projetos cadastrados | É o que permite detectar stack, portas e montar contexto. Limitado pela allowlist de `configs/roots.yml`. |
| Com IA ligada, trechos de código podem ir para um provider externo | Só de projetos com IA ativa, e cada projeto tem interruptor próprio (*Excluir da IA*). Pergunta marcada como privada nunca sai. Com provider local, nada sai da máquina. |
| Executa `git` e `docker` de verdade | É o produto. O que ele **não** faz é expor verbo destrutivo: não há `docker system prune`, `git push` nem `git reset --hard` alcançável por nenhum caminho da API — e há teste que falha se alguém adicionar. |

## Versões suportadas

O projeto está em `0.x` e não mantém branches de versão. **Só a `main` recebe
correção de segurança.** Se você roda um fork ou um build antigo, atualize
antes de reportar.

## Escopo

**Dentro do escopo:** qualquer forma de fazer o painel executar comando fora do
catálogo de ações; escapar da allowlist de diretórios; alcançar a API de fora
do `localhost`; extrair chave de API por qualquer superfície; fazer uma
pergunta marcada como privada chegar a um provider de nuvem; injeção via
conteúdo de projeto (README, manifesto) que altere o comportamento do painel.

**Fora do escopo:** falha que exija acesso prévio ao seu usuário no SO;
vulnerabilidade em dependência de terceiro sem impacto demonstrável aqui
(reporte ao projeto de origem); ausência de autenticação (decisão de design,
ver tabela acima); e o fato de o painel executar comandos, que é a razão de
ele existir.
