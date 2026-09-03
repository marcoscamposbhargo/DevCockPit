# T-14 — passo a passo

Única task manual do ciclo `ai-harness-mvp` (ver `tasks.md`). Precisa da sua
máquina, das suas chaves e de confirmação humana em dois pontos que a spec
deliberadamente não chutou. Faça tudo numa sessão só — o passo 4 deixa o painel
instalado sem abrir até o passo 5 terminar.

## 0. Antes de começar

- [ ] Feche o DevCockpit se estiver aberto.
- [ ] Tenha em mãos: chave da DeepSeek, chave da Moonshot (Kimi).

## 1. Confirmar os identificadores reais (não pule — é o ponto que a spec deixou em aberto de propósito)

Uma busca automatizada nesta sessão trouxe `deepseek-v4-flash`/`deepseek-v4-pro`
e `kimi-k3`/`kimi-k2.6` como nomes possíveis, mas foram vistos só por resumo de
IA sobre a página, não a documentação crua — e são posteriores ao corte de
conhecimento do assistente, que não pode validá-los de memória. Não os use sem
conferir.

Abra você mesmo, de preferência o **painel de billing/uso** de cada fornecedor
(ele só lista o que você pode realmente chamar, ao contrário da doc geral que
pode listar modelo em preview ou descontinuado):

- **DeepSeek**: `https://platform.deepseek.com` (billing/uso) ou
  `https://api-docs.deepseek.com/quick_start/pricing` (preço documentado).
- **Moonshot/Kimi**: `https://platform.moonshot.ai` (ou `platform.kimi.ai`,
  para onde a Moonshot andou redirecionando) — página de billing, ou
  `/docs/models` para a lista de modelos.

Anote, para cada provider:

| Campo | DeepSeek | Kimi (Moonshot) |
|---|---|---|
| `base_url` | | |
| identificador do modelo principal | | |
| preço entrada (por 1M tokens) | | |
| preço saída (por 1M tokens) | | |
| janela de contexto (tokens) | | |
| data em que você confirmou | | |

## 2. Escrever `configs/ai.yml`

```powershell
Copy-Item configs\ai.example.yml configs\ai.yml
```

Abra `configs/ai.yml` e substitua **só os quatro `<confirmar-na-T-14>`** e os
dois `context_window: 0` pelos valores que você anotou no passo 1. Não mexa em
mais nada — o resto do arquivo (provider `local`, cadeia de fallback, limiares
de roteamento) já está correto.

Depois, no bloco `precos:`, acrescente as duas entradas que faltam (o exemplo
só tem `local-codigo`, de propósito — preço de nuvem não podia ser chutado):

```yaml
precos:
  local-codigo:
    input_por_milhao: 0.0
    output_por_milhao: 0.0
    anotado_em: "2026-09-03"

  deepseek-principal:
    input_por_milhao: <valor do passo 1>
    output_por_milhao: <valor do passo 1>
    anotado_em: "<data em que você confirmou>"

  kimi-principal:
    input_por_milhao: <valor do passo 1>
    output_por_milhao: <valor do passo 1>
    anotado_em: "<data em que você confirmou>"
```

Se não quiser confirmar o preço agora, **não invente um número** — deixe o
modelo fora da tabela `precos`. A tela mostra "não medido" em vez de um valor
errado (P-02), e você completa depois sem quebrar nada.

`configs/ai.yml` não é versionado (está no `.gitignore`), então não precisa se
preocupar em "sujar" o repositório.

## 3. Colocar as chaves no `.env`

Abra o `.env` da instalação (a mesma pasta de `data/` e `logs/` do
`DevCockpit.exe`, ou o `.env` do repositório se for rodar pelo código) e
acrescente, se ainda não existirem:

```
DEVCOCKPIT_AI_KEY_DEEPSEEK=<sua chave>
DEVCOCKPIT_AI_KEY_MOONSHOT=<sua chave>
```

As outras quatro variáveis (`DEVCOCKPIT_AI_CONFIG_FILE`,
`DEVCOCKPIT_AI_MAX_ATTEMPTS`) já têm default no código (`./configs/ai.yml` e
`3`) — só declare no `.env` se quiser um valor diferente.

Depois de confirmar que as chaves estão no `.env`, pode apagar `chave.txt` da
raiz do repositório (nunca foi versionado, mas não tem mais razão de existir
solto no disco):

```powershell
Remove-Item chave.txt
```

## 4. Aplicar a migração 010 e reconstruir o executável — **nesta ordem, sem pular etapa**

Isto é o ponto de maior risco operacional do ciclo. Fazer só a migração sem
reconstruir deixa o `.exe` instalado quebrado (ele carrega o catálogo de
migrações empacotado nele mesmo, e passa a não reconhecer a revisão nova do
banco).

```powershell
# 1. Parar o processo, se estiver rodando
Get-Process DevCockpit -ErrorAction SilentlyContinue | Stop-Process -Force
# confira que não voltou sozinho antes de seguir
Start-Sleep -Seconds 2
Get-Process DevCockpit -ErrorAction SilentlyContinue

# 2. Aplicar a migração no banco de produção
#    (settings.resolve reescreve caminho relativo — o banco real é este, não
#    o data/devcockpit.db do repositório)
$env:DEVCOCKPIT_DATABASE_URL = "sqlite:///C:/Users/User/DevCockpit/data/devcockpit.db"
.venv\Scripts\python.exe -m alembic upgrade head

# 3. Reconstruir
.venv\Scripts\python.exe -m PyInstaller devcockpit.spec --noconfirm

# 4. Reinstalar por cima, preservando configs/data/logs/.env
#    (eles ficam FORA de _internal, não se perdem)
Remove-Item -Recurse -Force "C:\Users\User\DevCockpit\_internal"
Copy-Item -Recurse -Force "dist\DevCockpit\_internal" "C:\Users\User\DevCockpit\_internal"
Copy-Item -Force "dist\DevCockpit\DevCockpit.exe" "C:\Users\User\DevCockpit\DevCockpit.exe"
```

Se o `robocopy`/`Copy-Item` reclamar de arquivo travado, confira de novo que o
processo não voltou sozinho (já aconteceu nesta máquina) antes de repetir.

## 5. Verificação ao vivo (fecha REQ-05 e REQ-11 de verdade)

Abra o DevCockpit e confira, nesta ordem:

- [ ] **Configurações → AI Providers**: DeepSeek e Kimi aparecem como
      "conectado", local como "conectado" se o Ollama estiver rodando.
- [ ] Pergunta comum no chat → responde por DeepSeek ou Kimi, com custo
      aparecendo na tela de AI Usage (não "não medido", já que você preencheu
      o preço).
- [ ] **Ollama parado** (`Stop-Process` no processo do Ollama, ou pare o
      serviço) + pergunta marcada como privada (ex.: menciona um `.env` ou uma
      senha) → precisa **recusar com explicação**, nunca ir para a nuvem. Isto
      é o teste mais importante de todos: é a garantia de que nada privado sai
      da máquina.
- [ ] Chave da DeepSeek errada de propósito (troque um caractere no `.env` e
      reinicie) → a pergunta falha, mas **sem** tentar duas vezes o mesmo
      provider com a mesma chave errada.
- [ ] O painel instalado abre sem erro de "Can't locate revision".

Quando os cinco itens passarem, marque o checkbox de T-14 em `tasks.md` e a
spec `ai-harness-mvp` está encerrada de ponta a ponta.
