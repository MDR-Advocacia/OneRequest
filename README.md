# OneRequest - Painel de Gerenciamento de Solicitações

## 📖 Descrição

OneRequest é um sistema completo de automação (RPA) e visualização de dados construído para otimizar o fluxo de trabalho de solicitações jurídicas. O sistema utiliza robôs para coletar dados de um portal web, processa essas informações, e as armazena em um banco de dados centralizado.

Os dados são apresentados em um painel web moderno e interativo, que oferece ferramentas de gestão, visualização de KPIs, filtros, e um sistema de autenticação seguro com diferentes níveis de permissão para os usuários.

## ✨ Funcionalidades Principais

-   **Automação Robótica de Processos (RPA):**
    -   **Coletor de Tarefas:** Um robô (`coletaDadosNumeroSolicitacoes.py`) que varre o portal em busca de novas solicitações e as insere na fila de trabalho.
    -   **Sincronização de Status:** O mesmo robô identifica solicitações que foram finalizadas (não estão mais na lista principal) e atualiza seu status para "Respondido" no banco de dados.
    -   **Detalhador de Tarefas:** Um segundo robô (`main.py`) processa as solicitações pendentes, acessando páginas de detalhes, popups e APIs internas para enriquecer os dados.

-   **Painel Web Interativo (`server.py`):**
    -   **Dashboard de KPIs:** Cards que exibem um resumo dos prazos (Vencidas, Vencem Hoje, Vencem Amanhã, Futuras).
    -   **Gráfico de Recebimentos:** Visualização da quantidade de solicitações recebidas em um período de datas selecionável.
    -   **Tabela Inteligente:** Exibe todas as solicitações abertas com um "Farol" visual indicando a urgência de cada prazo.
    -   **Edição Direta:** Campos interativos na tabela para atribuir um responsável, adicionar anotações e mudar o status, com salvamento automático no banco de dados.
    -   **Filtros e Busca:** Permite filtrar as solicitações por responsável ou buscar por palavra-chave.
    -   **Histórico:** Uma página separada para visualizar todas as solicitações já respondidas.
    -   **Exportação para Excel:** Funcionalidade para exportar a lista de solicitações pendentes para uma planilha `.xlsx`.

-   **Segurança e Gestão de Usuários:**
    -   **Sistema de Login:** Acesso ao painel protegido por nome de usuário e senha.
    -   **Níveis de Permissão:** Dois tipos de usuário: **Admin** (acesso total) e **Usuário** (acesso apenas ao painel).
    -   **CRUD de Usuários:** Uma interface exclusiva para administradores criarem, editarem e deletarem os usuários do sistema.

## 🛠️ Tecnologias Utilizadas

-   **Backend:** Python
-   **Framework Web:** Flask
-   **Automação Web:** Playwright
-   **Banco de Dados:** SQLite
-   **Servidor de Produção:** Waitress
-   **Autenticação:** Flask-Login & Werkzeug
-   **Frontend:** HTML, CSS, JavaScript (com Chart.js para gráficos)
-   **Agendamento:** Módulo `schedule` do Python

## 📂 Estrutura do Projeto

onerequest/
│
├── bd/
│   ├── database.py         # Módulo de controle do banco de dados
│   ├── database.db         # Banco de dados externo (para lista de responsáveis)
│   └── solicitacoes.db     # Banco de dados principal da aplicação
│
├── RPA/
│   ├── coletaDadosNumeroSolicitacoes.py  # Robô 1: Coleta e sincroniza números
│   ├── main.py             # Robô 2: Detalha as solicitações pendentes
│   ├── navegador.py        # Módulo para controlar o navegador
│   └── portal_bb.py        # Módulo com as ações específicas do portal
│
├── static/
│   ├── css/                # Arquivos de estilo (CSS)
│   └── images/             # Imagens e logos
│
├── templates/
│   ├── index.html          # Template do painel principal
│   ├── login.html          # Template da página de login
│   └── ...                 # Outros templates HTML
│
├── server.py               # Servidor web Flask
├── scheduler.py            # Script para agendamento dos robôs
├── requirements.txt        # Lista de dependências Python
└── ...



## 🚀 Como Executar

### Pré-requisitos

-   Python 3.x instalado.
-   Um ambiente virtual (venv) é altamente recomendado.

### Instalação

1.  Clone ou copie os arquivos do projeto para uma pasta no seu computador.
2.  Abra um terminal, navegue até a pasta do projeto e crie um ambiente virtual:
    ```bash
    python -m venv venv
    ```
3.  Ative o ambiente virtual:
    -   No Windows: `venv\Scripts\activate`
    -   No macOS/Linux: `source venv/bin/activate`
4.  Instale todas as dependências necessárias:
    ```bash
    pip install -r requirements.txt
    ```

### Execução

O sistema foi projetado para rodar em dois processos separados: o **servidor do painel** e o **agendador dos robôs**.

**1. Para Iniciar o Painel Web:**

Execute o servidor Flask. Ele criará o banco de dados e o primeiro usuário `admin` (senha: `admin`) se eles não existirem.

```bash
python server.py