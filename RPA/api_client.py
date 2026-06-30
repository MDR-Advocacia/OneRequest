"""
Cliente HTTP que substitui o acesso direto ao banco de dados nos RPAs.
Expõe funções com os mesmos nomes de bd/database.py, mas faz chamadas
HTTP para a API REST do servidor OneRequest na AWS.

Configuração via variáveis de ambiente:
  RPA_API_URL  - URL base da API (ex: https://onerequest.mdradvocacia.com/api/rpa)
  RPA_API_KEY  - Chave de autenticação
"""

import os
import requests

API_URL = os.environ.get('RPA_API_URL', 'http://localhost:5000/api/rpa')
API_KEY = os.environ.get('RPA_API_KEY', '')
TIMEOUT = 30


def _headers():
    return {'X-API-Key': API_KEY, 'Content-Type': 'application/json'}


def _get(endpoint):
    resp = requests.get(f"{API_URL}{endpoint}", headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post(endpoint, data):
    resp = requests.post(f"{API_URL}{endpoint}", json=data, headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _put(endpoint, data):
    resp = requests.put(f"{API_URL}{endpoint}", json=data, headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def inicializar_banco():
    pass


def obter_solicitacoes_abertas_db():
    data = _get('/solicitacoes/abertas')
    return data['numeros']


def sincronizar_portal(numeros_portal):
    return _post('/solicitacoes/sync', {'numeros_portal': list(numeros_portal)})


def obter_solicitacoes_pendentes():
    data = _get('/solicitacoes/pendentes')
    return data['numeros']


def atualizar_detalhes_solicitacao(dados_solicitacao):
    return _put('/solicitacoes/detalhes', dados_solicitacao)


def obter_solicitacoes_vencem_hoje():
    data = _get('/solicitacoes/vencem-hoje')
    return data['numeros']


def atualizar_status_portal(numero_solicitacao, status_portal):
    return _put('/solicitacoes/status-portal', {
        'numero_solicitacao': numero_solicitacao,
        'status_portal': status_portal,
    })
