import tkinter as tk
from tkinter import messagebox
import subprocess

# Variável global para o processo do servidor
server_process = None

def iniciar_servidor():
    global server_process
    if server_process is None:
        try:
            # Inicia o servidor Flask usando subprocess


            server_process = subprocess.Popen(
                ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW  # Oculta o terminal no Windows
            )
            messagebox.showinfo("Sucesso", "Servidor iniciado com sucesso!")
            btn_iniciar.config(text="Desligar Servidor", command=desligar_servidor)
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao iniciar o servidor: {e}")
    else:
        messagebox.showwarning("Aviso", "O servidor já está em execução.")

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

# Configuração da interface gráfica
app = tk.Tk()
app.title("Gerenciador de Servidor Flask")

# Botão para iniciar/desligar o servidor
btn_iniciar = tk.Button(app, text="Iniciar Servidor", command=iniciar_servidor, width=20)
btn_iniciar.pack(pady=20)

# Botão para sair
btn_sair = tk.Button(app, text="Sair", command=app.quit, width=20)
btn_sair.pack(pady=10)

# Loop principal da interface
app.mainloop()