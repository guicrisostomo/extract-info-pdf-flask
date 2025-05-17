from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
from load_files import supabase, logger
from tasks_helpers import entregador_ocioso

def have_orders_in_progress(motoboy_uid: uuid.UUID) -> Optional[uuid.UUID]:
    res = supabase.table("routes") \
        .select("id") \
        .eq("in_progress", True) \
        .eq("motoboy_uid", motoboy_uid) \
        .limit(1).execute()
    logger.info(f"Ultimo checkin: {res.data}")
    logger.info(res)
    if res.data:
        return uuid.UUID(res.data[0]["id"])
    return None

def motoboys_ociosos(usuario_uids: list[uuid.UUID], limite_minutos=15) -> list[uuid.UUID]:
    ociosos = []
    now = datetime.now(timezone.utc)
    for uid in usuario_uids:

        order_in_progress = have_orders_in_progress(uid)
        if order_in_progress is None:
            ociosos.append(uid)
            continue
    return ociosos

def obtem_motoboys():
    motoboys = supabase.table("tb_user") \
        .select("uid") \
        .eq("typeUserId", 1) \
        .eq("fg_ativo", True) \
        .eq("cnpj", "1") \
        .execute()
    return [uuid.UUID(motoboy["uid"]) for motoboy in motoboys.data]
