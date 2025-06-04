import logging
from supabase import create_client, Client
from datetime import datetime, timezone
import config

logger = logging.getLogger(__name__)

supabase_client: Client | None = None
CHAT_HISTORY_TABLE = "chat_history"

def init_supabase_client():
    global supabase_client
    if config.SUPABASE_URL and config.SUPABASE_KEY:
        try:
            supabase_client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
            logger.info("Klien Supabase berhasil diinisialisasi.")
        except Exception as e:
            logger.error(f"Gagal menginisialisasi klien Supabase: {e}")
            supabase_client = None
    else:
        logger.warning("URL atau Kunci Supabase tidak ada di konfigurasi. Fitur Supabase akan dinonaktifkan.")
        supabase_client = None

def add_message_to_history(chat_id: int, role: str, content: str) -> bool:
    if not supabase_client:
        logger.warning("Supabase client tidak tersedia. Pesan tidak bisa ditambahkan ke riwayat.")
        return False
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        response = supabase_client.table(CHAT_HISTORY_TABLE).insert({
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "message_timestamp": timestamp
        }).execute()

        if hasattr(response, 'error') and response.error:
            error_detail = response.error
            error_message = error_detail.message if hasattr(error_detail, 'message') else str(error_detail)
            logger.error(f"Error Supabase saat menambahkan pesan untuk chat_id {chat_id}: {error_message}")
            return False
        elif hasattr(response, 'data') and response.data:
            logger.debug(f"Pesan untuk chat_id {chat_id} berhasil ditambahkan ke riwayat Supabase.")
            return True
        else:
            logger.warning(f"Respons Supabase saat menambahkan pesan untuk chat_id {chat_id} tidak memiliki data yang diharapkan atau error yang jelas (data: {hasattr(response, 'data')}, error attr: {hasattr(response, 'error')}). Menganggap berhasil karena tidak ada exception. Response: {str(response)[:200]}")
            return True
    except Exception as e:
        logger.error(f"Pengecualian (exception) saat menambahkan pesan ke Supabase untuk chat_id {chat_id}: {e}", exc_info=True)
        return False

def get_chat_history(chat_id: int) -> list:
    if not supabase_client:
        logger.warning("Supabase client tidak tersedia. Tidak bisa mengambil riwayat chat.")
        return []
    try:
        response = supabase_client.table(CHAT_HISTORY_TABLE)\
            .select("role, content")\
            .eq("chat_id", chat_id)\
            .order("message_timestamp", desc=True)\
            .limit(config.CHAT_HISTORY_MESSAGES_LIMIT)\
            .execute()

        formatted_history = []
        if hasattr(response, 'data') and response.data:
            for item in reversed(response.data):
                formatted_history.append({"role": item["role"], "parts": [{"text": item["content"]}]})
            logger.debug(f"Mengambil {len(formatted_history)} pesan dari riwayat Supabase untuk chat_id {chat_id}.")
        elif hasattr(response, 'error') and response.error:
            error_detail = response.error
            error_message = error_detail.message if hasattr(error_detail, 'message') else str(error_detail)
            logger.error(f"Error Supabase saat mengambil riwayat chat untuk chat_id {chat_id}: {error_message}")
        return formatted_history
    except Exception as e:
        logger.error(f"Error (exception) mengambil riwayat chat dari Supabase untuk chat_id {chat_id}: {e}", exc_info=True)
        return []

def delete_chat_history_db(chat_id: int) -> bool:
    if not supabase_client:
        logger.warning("Supabase client tidak tersedia. Tidak bisa menghapus riwayat chat.")
        return False
    try:
        response = supabase_client.table(CHAT_HISTORY_TABLE).delete().eq("chat_id", chat_id).execute()

        if hasattr(response, 'error') and response.error:
            error_detail = response.error
            error_message = error_detail.message if hasattr(error_detail, 'message') else str(error_detail)
            logger.error(f"Error Supabase saat menghapus riwayat untuk chat_id {chat_id}: {error_message}")
            return False
        elif hasattr(response, 'data'): 
            logger.info(f"Riwayat chat untuk chat_id {chat_id} berhasil diproses untuk penghapusan dari Supabase.")
            return True
        else:
            logger.warning(f"Respons Supabase saat menghapus riwayat untuk chat_id {chat_id} tidak memiliki atribut 'data' atau 'error' yang jelas. Menganggap berhasil karena tidak ada exception. Response: {str(response)[:200]}")
            return True
    except Exception as e:
        logger.error(f"Pengecualian (exception) saat menghapus riwayat chat dari Supabase untuk chat_id {chat_id}: {e}", exc_info=True)
        return False

init_supabase_client()
