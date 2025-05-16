import logging
import os
from supabase import create_client


logging.basicConfig(
    filename="api_logs.txt",  # Nome do arquivo de log
    level=logging.INFO,       # Nível de log
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)