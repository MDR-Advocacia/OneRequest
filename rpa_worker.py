"""Worker HTTP no container RPA: recebe triggers de execução manual e roda o ciclo dos robôs.

Roda junto com o agendador (run_robos.py): o agendador cuida dos ciclos automáticos
de hora em hora, e este worker aceita POST /executar para disparos manuais (ex.: botão
no Flow). O lock do Chrome garante que nunca rodem dois ciclos simultâneos.

Porta interna: 5001 (não exposta ao mundo — só o container server acessa via rede Docker).
"""
import os
import sys
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

PYTHON_EXE = sys.executable
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

_em_andamento = False
_resultado = None
_lock = threading.Lock()


def _rodar_ciclo():
    global _em_andamento, _resultado
    try:
        r = subprocess.run(
            [PYTHON_EXE, os.path.join(PROJECT_DIR, 'run_robos_ciclo.py')],
            capture_output=True, text=True, timeout=1800,
            cwd=PROJECT_DIR,
        )
        _resultado = {
            'status': 'sucesso' if r.returncode == 0 else 'erro',
            'codigo': r.returncode,
            'saida': (r.stdout or '')[-3000:],
            'erro': (r.stderr or '')[-1000:],
        }
    except Exception as exc:
        _resultado = {'status': 'erro', 'mensagem': str(exc)}
    finally:
        with _lock:
            _em_andamento = False


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.rstrip('/') != '/executar':
            self._json(404, {'status': 'erro', 'mensagem': 'Rota não encontrada.'})
            return
        global _em_andamento, _resultado
        with _lock:
            if _em_andamento:
                self._json(409, {'status': 'em_andamento', 'mensagem': 'Já existe uma execução em andamento.'})
                return
            _em_andamento = True
            _resultado = None
        threading.Thread(target=_rodar_ciclo, daemon=True).start()
        self._json(200, {'status': 'iniciado'})

    def do_GET(self):
        if self.path.rstrip('/') == '/health':
            self._json(200, {'status': 'ok'})
            return
        if self.path.rstrip('/') != '/executar/status':
            self._json(404, {'status': 'erro', 'mensagem': 'Rota não encontrada.'})
            return
        with _lock:
            em_andamento = _em_andamento
        if em_andamento:
            self._json(200, {'status': 'em_andamento'})
        elif _resultado is None:
            self._json(200, {'status': 'ocioso'})
        else:
            self._json(200, _resultado)

    def log_message(self, format, *args):
        print(f"[worker] {args[0]}")


if __name__ == '__main__':
    port = int(os.environ.get('RPA_WORKER_PORT', '5001'))
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"[worker] Escutando na porta {port}")
    server.serve_forever()
