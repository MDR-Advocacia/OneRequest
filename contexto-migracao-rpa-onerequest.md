# Contexto: OneRequest — RPAs migrados para Docker + Trigger de Execução Manual

## Situação anterior

- **Dashboard** (Flask + PostgreSQL): já rodava na AWS via Coolify/Docker
- **RPAs** (Playwright + Chrome): rodavam numa **máquina Windows local**, comunicando com o dashboard via API REST
- Para autenticar no portal `juridico.bb.com.br`, os RPAs usavam o **OneLog** (autenticação automatizada)
- Quando o OneLog falhava, dependia de login manual local (abrir Chrome na máquina)

## O que mudou

Os RPAs agora rodam **dentro do Docker na mesma EC2** do dashboard, como um service separado no `docker-compose.yml`. A máquina Windows local foi desativada.

---

## Arquitetura atual (3 containers)

```
docker-compose.yml
├── db       → PostgreSQL 16 Alpine
├── server   → Flask (dashboard + API REST), porta 5000
└── rpa      → Agendador + Worker HTTP + Playwright/Chromium headless, porta interna 5001
```

### Container `rpa`

Roda dois processos:
1. **Agendador** (`run_robos.py`): ciclos automáticos de hora em hora (7h-18h Brasília)
2. **Worker HTTP** (`rpa_worker.py`): aceita triggers manuais via API

O Chrome roda em modo **headless** (`RPA_HEADLESS=1`), sem GUI.

### Comunicação

```
Flow ──POST──▶ server:5000/api/rpa/executar ──proxy──▶ rpa:5001/executar
                  (X-API-Key: RPA_API_KEY)              (rede Docker interna)
```

---

## Endpoints para o Flow usar

### Sessão Manual (já existiam — proxy para o Flow)

Os RPAs consultam o servidor OneRequest, que faz proxy para o Flow:

- `GET  /api/rpa/sessao-manual` → proxy para `GET  flow/api/v1/onerequest/intake/sessao-manual-bb`
- `PUT  /api/rpa/sessao-manual/invalidar` → proxy para `PUT flow/api/v1/onerequest/intake/sessao-manual-bb/invalidar`

**Chave**: `FLOW_ONEREQUEST_API_KEY` (= `ONEREQUEST_INTAKE_API_KEY` do Flow)

### Trigger de Execução Manual (NOVO)

**Disparar um ciclo:**
```
POST /api/rpa/executar
Header: X-API-Key: <RPA_API_KEY>
```
Resposta: `{"status": "iniciado"}` (200) ou `{"status": "em_andamento"}` (409)

**Consultar status:**
```
GET /api/rpa/executar/status
Header: X-API-Key: <RPA_API_KEY>
```
Respostas possíveis:
- `{"status": "ocioso"}` — nenhuma execução recente
- `{"status": "em_andamento"}` — ciclo rodando
- `{"status": "sucesso", "codigo": 0, "saida": "..."}` — último ciclo OK
- `{"status": "erro", "codigo": 1, "saida": "...", "erro": "..."}` — último ciclo falhou

---

## Fluxo "Rodar Manual" (o que o Flow precisa implementar)

A ideia é: na tela de sessão manual do Flow (Distribuídos BB → Configuração → Sessão manual do BB), adicionar um botão **"Rodar OneRequest"** que:

1. **Cola a sessão no Flow** (já funciona — o operador cola o cURL, o Flow guarda)
2. **Dispara o ciclo no OneRequest**: `POST /api/rpa/executar` com a chave `RPA_API_KEY`
3. **Acompanha o status** (opcional): polling em `GET /api/rpa/executar/status` até `sucesso` ou `erro`

### Sequência completa:

```
Operador                  Flow                         OneRequest (AWS)
   |                        |                              |
   |-- cola cURL ---------->|                              |
   |                        |-- guarda sessão (já faz)     |
   |-- clica "Rodar" ----->|                              |
   |                        |--- POST /api/rpa/executar -->|
   |                        |<-- {"status": "iniciado"} ---|
   |                        |                              |-- rpa_worker dispara ciclo
   |                        |                              |-- robô busca sessão manual
   |                        |                              |   (GET /api/rpa/sessao-manual
   |                        |                              |    → proxy → Flow)
   |                        |                              |-- injeta cookies, navega
   |                        |                              |
   |                        |--- GET .../executar/status ->|
   |                        |<-- {"status": "sucesso"} ----|
   |<-- "Execução OK" -----|                              |
```

### Configuração necessária no Flow

- **`ONEREQUEST_API_URL`**: URL do OneRequest (ex.: `https://onerequest.mdradvocacia.com`)
- **`ONEREQUEST_RPA_API_KEY`**: a mesma `RPA_API_KEY` configurada no OneRequest

### Configuração necessária no OneRequest (.env / Coolify)

- **`RPA_API_KEY`**: chave que protege os endpoints `/api/rpa/*`
- **`FLOW_ONEREQUEST_API_KEY`**: chave para o proxy de sessão manual (= `ONEREQUEST_INTAKE_API_KEY` do Flow)
- **`FLOW_API_URL`**: URL do Flow (default: `https://flow.dunatecnologia.com`)
- **`RPA_HEADLESS=1`**: obrigatório no container (sem GUI)
- **`ONELOG_USERNAME` / `ONELOG_PASSWORD`**: credenciais do OneLog (mantidas como fallback)
- **`BB_USUARIO` / `BB_SENHA`**: credenciais do portal BB (fallback do fallback)

---

## Arquivos novos/modificados no OneRequest

| Arquivo | O que faz |
|---|---|
| `Dockerfile.rpa` | Imagem Docker com Python + Playwright + Chromium headless |
| `entrypoint_rpa.sh` | Lança worker HTTP em background + agendador em foreground |
| `rpa_worker.py` | Worker HTTP (porta 5001): `POST /executar`, `GET /executar/status`, `GET /health` |
| `run_robos_ciclo.py` | Single-shot: roda 1 ciclo completo e sai (usado pelo trigger) |
| `docker-compose.yml` | Novo service `rpa` com healthcheck e expose 5001 |
| `RPA/navegador.py` | Dual-mode: `RPA_HEADLESS=1` → Playwright launch, senão → .bat/CDP |
| `RPA/coletaDadosNumeroSolicitacoes.py` | Adaptado para headless (mesmo padrão) |
| `server.py` | Rotas `POST /api/rpa/executar` e `GET /api/rpa/executar/status` (proxy para container rpa) |

---

## Ordem de prioridade de login dos RPAs

1. **Login manual local** (`RPA_LOGIN_MANUAL=1`) — desativado no Docker, mas mantido no código
2. **Sessão manual remota** — cookies colados no Flow, consultados via proxy
3. **OneLog** — autenticação automatizada (com retry/backoff)
4. **Login direto SSO** — credenciais `BB_USUARIO`/`BB_SENHA` (último recurso)
