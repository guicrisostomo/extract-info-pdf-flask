from celery import Celery

# Configuração do Celery com Redis como broker
app = Celery(
    "worker",
    broker="redis://redis:6379/0",  # URL do Redis
    backend="redis://redis:6379/0"  # Backend para armazenar resultados
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
)

app.autodiscover_tasks(['tasks', 'tasks.fila_celery.reatribuir_entregas_para_motoboy_ocioso'])