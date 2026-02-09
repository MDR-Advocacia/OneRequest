import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
from dotenv import load_dotenv

load_dotenv()

class NavSelenium:
    def __init__(self):
        self.driver = None
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.profile_path = os.path.join(base_dir, 'chrome_profile_onesid')

    def iniciar(self):
        print("🚀 Iniciando navegador (Modo ONE-SID + Eager)...")
        
        if not os.path.exists(self.profile_path):
            os.makedirs(self.profile_path)
        
        options = uc.ChromeOptions()
        
        # --- OTIMIZAÇÕES ---
        options.add_argument(f"--user-data-dir={self.profile_path}")
        options.add_argument("--no-first-run")
        options.add_argument("--password-store=basic")
        
        # O PULO DO GATO PARA TIMEOUTS:
        # Não espera carregar tudo (imagens/scripts pesados). Liberou o DOM, liberou o robô.
        options.page_load_strategy = 'eager' 
        
        self.driver = uc.Chrome(
            options=options, 
            version_main=144, 
            use_subprocess=True
        )
        
        self.driver.set_script_timeout(60)
        self.driver.set_page_load_timeout(60)
        
        return self.driver

    def fazer_login(self):
        print("🔐 Verificando login...")
        try:
            self.driver.get('https://juridico.bb.com.br/wfj/')
            time.sleep(5)
            
            if "juridico.bb.com.br/wfj" in self.driver.current_url and "login" not in self.driver.current_url:
                print("✅ Sessão recuperada! Login pulado.")
                return True
                
            print("⚠️ Sessão expirada. Redirecionando para login...")
            self.driver.get('https://loginweb.bb.com.br/sso/XUI/?realm=/paj&goto=https://juridico.bb.com.br/wfj#login')
            
            wait = WebDriverWait(self.driver, 60)

            if "Just a moment" in self.driver.title or "challenge" in self.driver.current_url:
                print("🛑 Cloudflare detectado! Resolva manualmente.")
                while "challenge" in self.driver.current_url:
                    time.sleep(1)
                print("✅ Cloudflare superado!")

            try:
                usuario = os.getenv("BB_USUARIO")
                senha = os.getenv("BB_SENHA")

                if usuario:
                    elem_user = wait.until(EC.visibility_of_element_located((By.ID, "idToken1")))
                    elem_user.clear()
                    elem_user.send_keys(usuario)
                    self.driver.find_element(By.ID, "loginButton_0").click()

                if senha:
                    elem_pass = wait.until(EC.visibility_of_element_located((By.ID, "idToken3")))
                    elem_pass.send_keys(senha)
                    self.driver.find_element(By.CSS_SELECTOR, "input#loginButton_0[name='callback_4']").click()
            except: pass

            print("⏳ Aguardando Home...")
            wait.until(EC.url_contains("juridico.bb.com.br/wfj"))
            print("✅ Login realizado!")
            return True

        except Exception as e:
            print(f"❌ Erro no login: {e}")
            return False

    def fechar(self):
        if self.driver:
            print("🏁 Encerrando navegador...")
            try: self.driver.quit()
            except: pass