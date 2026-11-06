"""Login manual assistido do Portal Jurídico do BB.

Use quando o login automático (OneLog/SSO) estiver com problema e você quiser
operar com um login feito a mão, SEM parar os robôs.

O que faz:
  1. Abre o Chrome do robô (mesmo perfil/porta, respeitando o lock — espera um
     ciclo em andamento terminar).
  2. Abre a tela de login do portal e ESPERA você logar na janela.
  3. Ao confirmar o login, SALVA os cookies da sessão num arquivo
     (padrão: C:\\temp\\bb_sessao_manual.json).

Depois disso, com RPA_LOGIN_MANUAL=1 no .env, os robôs agendados reaproveitam
essa sessão automaticamente a cada ciclo. Quando a sessão do portal expirar,
é só rodar este script de novo.

Para voltar ao login automático: remova (ou ponha 0) o RPA_LOGIN_MANUAL no .env.

Uso:
  python RPA/login_manual.py            # espera padrão (15 min) para você logar
  python RPA/login_manual.py 1800       # espera 1800s (30 min)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except Exception:
    pass

from navegador import Navegador
import portal_bb


def main():
    espera = int(sys.argv[1]) if len(sys.argv) > 1 else int(
        os.getenv("RPA_LOGIN_MANUAL_ESPERA_HELPER_SEG", "900")
    )
    caminho = portal_bb.arquivo_sessao_manual()
    print(f">>> LOGIN MANUAL — a sessão será salva em: {caminho}")
    print(f">>> Você tem até {espera}s para concluir o login na janela do Chrome.\n")

    nav = Navegador()
    try:
        nav.iniciar()
        portal_bb.capturar_sessao_manual(nav.context, espera_seg=espera, caminho=caminho)
        print("\n✅ Pronto! Sessão salva. Os robôs vão reaproveitar enquanto ela for válida.")
        print("   (Com RPA_LOGIN_MANUAL=1 no .env.)")
    except Exception as e:
        print(f"\n❌ Não foi possível capturar a sessão manual: {e}")
        sys.exit(1)
    finally:
        nav.fechar()


if __name__ == "__main__":
    main()
