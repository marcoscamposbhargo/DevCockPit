# ADR-001 — FastAPI como framework backend

- **Status:** Aceito
- **Data:** 2026-08-21
- **Fase:** 0

## Contexto

O DevCockpit precisa expor uma API REST local consumida por um frontend
estático, executar operações de I/O concorrentes (health checks de vários
serviços, comandos externos), servir streams (SSE para logs e progresso de job)
e validar entrada de forma rigorosa, porque a entrada alimenta construção de
comando.

Há também um objetivo secundário declarado no PRD: o projeto serve como estudo
de arquitetura, o que dá peso à legibilidade e à documentação automática.

## Decisão

Usar **FastAPI** com Pydantic v2 e `pydantic-settings`, servido por Uvicorn.

## Alternativas consideradas

| Alternativa | Por que não |
|-------------|-------------|
| **Flask** | síncrono por padrão; concorrência de health check e SSE exigiriam trabalho extra; validação de entrada seria manual, o que é ruim quando a entrada alimenta comando |
| **Django + DRF** | ORM, admin, migrations e sistema de apps são peso morto aqui; tempo de startup alto para uma ferramenta local |
| **Litestar** | tecnicamente adequado e comparável; ecossistema e material de referência menores, o que atrapalha o objetivo de estudo |
| **Node/Express** | fugiria da stack Python pedida e perderia acesso direto a bibliotecas de sistema em Python |

## Consequências

Positivas:
- validação de entrada declarativa, alinhada à defesa D2 do modelo de segurança
- `async` nativo: health checks concorrentes e SSE sem gambiarra
- OpenAPI gerado, que serve de contrato verificável contra `06-api-specification.md`
- injeção de dependência do próprio framework atende a substituição de adapter
  nos testes (NFR-023)

Negativas:
- código `async` misturado com `subprocess` exige disciplina; a execução de
  comando é encapsulada em `CommandRunner` justamente para isolar isso
- Pydantic v2 tem curva de aprendizado em validadores customizados

Neutras:
- o schema OpenAPI fica exposto localmente; irrelevante dado o bind loopback

## Notas

O endpoint de documentação automática (`/docs`) fica habilitado: é ferramenta de
dev e o servidor não é acessível de fora.
