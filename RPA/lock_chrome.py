"""Lock global de uso do Chrome.

Evita que dois robos (numeros, detalhes, status do dia) abram/fechem o MESMO Chrome
(porta de depuracao 9222 / perfil unico) ao mesmo tempo. Como cada robo, ao terminar,
mata o processo da porta 9222, dois rodando juntos derrubavam o Chrome um do outro.

Com este lock, so um robo usa o Chrome por vez; o outro aguarda liberar.
Inclui deteccao de lock orfao: se o processo dono morrer, o lock e reassumido.
"""
import os
import sys
import time
import subprocess

LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome.lock")


def _pid_vivo(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                f'tasklist /FI "PID eq {pid}" /NH',
                shell=True, capture_output=True, text=True, errors="ignore", timeout=10,
            )
            return str(pid) in (out.stdout or "")
        except Exception:
            return True  # na duvida, considera vivo (nao rouba o lock)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class LockChrome:
    """Lock entre processos baseado em arquivo (criacao atomica O_EXCL)."""

    def __init__(self, timeout_segundos=900, poll_segundos=3):
        self.timeout = timeout_segundos
        self.poll = poll_segundos
        self._fd = None

    def acquire(self):
        deadline = time.monotonic() + self.timeout
        avisou = False
        while True:
            try:
                self._fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self._fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    pid = int((open(LOCK_PATH).read().strip() or "0"))
                except Exception:
                    pid = 0
                # Lock orfao (dono morreu) -> reassume.
                if pid and not _pid_vivo(pid):
                    print(f"    ♻️ Lock do Chrome orfao (PID {pid} morto). Reassumindo.")
                    try:
                        os.remove(LOCK_PATH)
                    except Exception:
                        pass
                    continue
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        "Timeout aguardando o lock do Chrome (outro robo segue em execucao)."
                    )
                if not avisou:
                    print(f"    ⏳ Outro robo esta usando o Chrome (PID {pid}). Aguardando liberar...")
                    avisou = True
                time.sleep(self.poll)

    def release(self):
        # So libera/remove o lock se ESTE processo for o dono (senao apagaria o lock de outro robo).
        if self._fd is None:
            return
        try:
            os.close(self._fd)
        except Exception:
            pass
        self._fd = None
        try:
            os.remove(LOCK_PATH)
        except Exception:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
