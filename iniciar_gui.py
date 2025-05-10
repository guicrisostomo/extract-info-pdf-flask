import tkinter as tk
from tkinter import messagebox
import subprocess
import os
import time
import threading

# Variável global para o processo do servidor
server_process = None

# Caminho para o arquivo de log
log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_logs.txt")

def iniciar_servidor():
    global server_process
    if server_process is None:
        try:
            # Abre o arquivo de log em modo de anexar
            log_file = open(log_file_path, 'a')
            
            # Inicia o servidor Flask usando subprocess
            server_process = subprocess.Popen(
                ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"],
                stdout=log_file,  # Redireciona stdout para o arquivo de log
                stderr=log_file,  # Redireciona stderr para o arquivo de log
                creationflags=subprocess.CREATE_NO_WINDOW  # Oculta o terminal no Windows
            )
            messagebox.showinfo("Sucesso", "Servidor iniciado com sucesso!")
            btn_iniciar.config(text="Desligar Servidor", command=desligar_servidor)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao iniciar o servidor: {e}")

def desligar_servidor():
    global server_process
    if server_process is not None:
        try:
            # Finaliza o processo do servidor
            server_process.terminate()
            server_process.wait()
            server_process = None
            messagebox.showinfo("Sucesso", "Servidor desligado com sucesso!")
            btn_iniciar.config(text="Iniciar Servidor", command=iniciar_servidor)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao desligar o servidor: {e}")
    else:
        messagebox.showwarning("Aviso", "O servidor não está em execução.")

def acessar_logs():
    try:
        # Verifica se o arquivo de log existe
        if not os.path.exists(log_file_path):
            with open(log_file_path, 'w') as f:
                f.write("Arquivo de log criado.\n")
        
        # Abre o arquivo de log no editor de texto padrão
        os.startfile(log_file_path)
    except Exception as e:
        messagebox.showerror("Erro", f"Não foi possível acessar os logs: {e}")

def verificar_servidor():
    global server_process
    while True:
        if server_process is None or server_process.poll() is not None:
            # Se o servidor não está em execução, tenta reiniciá-lo
            try:
                iniciar_servidor()
            except Exception as e:
                print(f"Erro ao reiniciar o servidor: {e}")
        time.sleep(10)  # Verifica a cada 10 segundos

# Configuração da interface gráfica
app = tk.Tk()
app.title("Gerenciador de Servidor Flask")

# Botão para iniciar/desligar o servidor
btn_iniciar = tk.Button(app, text="Iniciar Servidor", command=iniciar_servidor, width=20)
btn_iniciar.pack(pady=20)

# Botão para acessar os logs
btn_logs = tk.Button(app, text="Acessar Logs", command=acessar_logs, width=20)
btn_logs.pack(pady=10)

# Botão para sair
btn_sair = tk.Button(app, text="Sair", command=app.quit, width=20)
btn_sair.pack(pady=10)

# Inicia a verificação do servidor em uma thread separada
threading.Thread(target=verificar_servidor, daemon=True).start()

# Loop principal da interface
app.mainloop()