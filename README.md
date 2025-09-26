-----

# OneRequest - Painel de Controle de Assessoria

O OneRequest é um painel de controle projetado para gerenciar e monitorar solicitações do módulo de assessoria de um portal bancário. A aplicação web, desenvolvida em Flask, centraliza as solicitações, permitindo que os usuários acompanhem prazos, distribuam tarefas e gerenciem o fluxo de trabalho de forma eficiente. O sistema conta com robôs de automação (RPA) para coletar e atualizar dados de forma automática.

## Funcionalidades Principais

  * **Dashboard Intuitivo:** Visualização rápida de solicitações pendentes com um sistema de "farol" (vermelho, amarelo, verde) que indica a urgência com base nos prazos.
  * **KPIs (Indicadores-Chave de Performance):** Métricas em tempo real que exibem a quantidade de solicitações vencidas, as que vencem hoje, amanhã e em datas futuras.
  * **Filtros e Buscas:** Ferramentas para filtrar solicitações por responsável e realizar buscas por número de solicitação, número do processo ou título.
  * **Gráfico de Recebimentos:** Um gráfico dinâmico que mostra o volume de solicitações recebidas ao longo de um período selecionável (por padrão, os últimos 15 dias).
  * **Gerenciamento de Usuários:** Uma área administrativa para criar, editar e deletar usuários, com controle de permissões (administrador e usuário padrão).
  * **Exportação de Dados:** Funcionalidade para exportar a lista de solicitações pendentes para um arquivo Excel (`.xlsx`).
  * **Automação com RPA:** Robôs que operam em segundo plano para:
      * Coletar novos números de solicitações periodicamente.
      * Buscar os detalhes completos de cada solicitação (título, prazo, processo, etc.).

## Como Funciona

O sistema é dividido em duas partes principais: a **Aplicação Web** e os **Robôs de Automação (RPA)**.

### Aplicação Web (`server.py`)

A aplicação Flask serve como a interface principal para os usuários. Ela é responsável por:

  * Exibir o painel com as solicitações e os KPIs.
  * Controlar a autenticação de usuários e o gerenciamento de sessões.
  * Fornecer endpoints de API para alimentar o gráfico de recebimentos e atualizar informações.
  * Permitir a edição de campos como "Responsável", "Anotação" e "Status".

### Robôs de Automação (RPA)

Os robôs são scripts Python agendados para executar tarefas de coleta de dados de forma automática:

1.  **Coleta de Números (`scheduler_coleta_numeros.py`):**

      * Este robô é executado a cada hora.
      * Ele acessa o portal do banco para identificar novas solicitações e insere seus números no banco de dados local.

2.  **Detalhamento de Solicitações (`scheduler_detalhes.py`):**

      * Este robô é executado a cada duas horas.
      * Ele busca no banco de dados as solicitações que ainda não possuem detalhes (como título, prazo, etc.).
      * Para cada uma, ele acessa a página específica da solicitação no portal e coleta todas as informações, atualizando o registro no banco de dados.

### Banco de Dados (`bd/database.py`)

O projeto utiliza um banco de dados **SQLite** para armazenar todas as informações. As principais tabelas são:

  * `solicitacoes`: Armazena todos os dados relacionados às solicitações, incluindo números, detalhes, prazos e status.
  * `usuarios`: Guarda as informações de login (nome, hash de senha e permissão) dos usuários do sistema.

## Como Executar o Projeto

Para colocar o sistema em funcionamento, siga os passos abaixo.

### Pré-requisitos

  * Python 3.x
  * Dependências listadas no arquivo `RPA/requirements.txt`.

### Instalação

1.  **Clone o repositório:**

    ```bash
    git clone https://github.com/MDR-Advocacia/OneRequest.git
    cd OneRequest
    ```

2.  **Instale as dependências:**

    ```bash
    pip install -r RPA/requirements.txt
    ```

### Execução

O sistema requer que três componentes principais sejam executados simultaneamente:

1.  **Aplicação Web:**
    Inicie o servidor Flask para que os usuários possam acessar o painel.

    ```bash
    python server.py
    ```

    O painel estará acessível em `http://localhost:5000`. O primeiro login padrão é `admin` com a senha `admin`.

2.  **Robô de Coleta de Números:**
    Este robô precisa rodar continuamente para buscar novas solicitações.

    ```bash
    python scheduler_coleta_numeros.py
    ```

3.  **Robô de Detalhamento de Solicitações:**
    Este robô também precisa rodar continuamente para preencher os detalhes das novas solicitações.

    ```bash
    python scheduler_detalhes.py
    ```

Recomenda-se utilizar um gerenciador de processos como o `pm2` ou configurar serviços no sistema operacional para garantir que os robôs e o servidor web continuem em execução.

## Estrutura do Projeto

```
/
|-- RPA/
|   |-- main.py                    # Orquestrador principal do robô de detalhamento
|   |-- coletaDadosNumeroSolicitacoes.py # Script do robô de coleta de números
|   |-- navegador.py               # Módulo para controle do navegador (Playwright)
|   |-- portal_bb.py               # Funções específicas para interagir com o portal
|   `-- requirements.txt           # Dependências Python dos robôs
|
|-- bd/
|   |-- database.py                # Módulo de gerenciamento do banco de dados SQLite
|   `-- solicitacoes.db            # Arquivo do banco de dados (criado na primeira execução)
|
|-- static/                        # Arquivos estáticos (CSS, imagens)
|   |-- css/
|   `-- images/
|
|-- templates/                     # Templates HTML (Flask)
|   |-- index.html                 # Página principal (dashboard)
|   |-- login.html                 # Página de login
|   |-- respondidas.html           # Página de solicitações respondidas
|   `-- usuarios.html              # Página de gerenciamento de usuários
|
|-- server.py                      # Arquivo principal da aplicação Flask
|-- scheduler_coleta_numeros.py    # Agendador do robô de coleta de números
`-- scheduler_detalhes.py          # Agendador do robô de detalhamento
```
