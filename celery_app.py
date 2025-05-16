from celery import Celery

# Configuração do Celery com Redis como broker
celery_app = Celery(
    "tasks",
    broker="redis://redis:6379/0",  # URL do Redis
    backend="redis://redis:6379/0"  # Backend para armazenar resultados
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,
)