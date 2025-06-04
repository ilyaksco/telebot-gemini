import logging
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL_NAME, GEMINI_SYSTEM_INSTRUCTION
import supabase_manager
import config


logger = logging.getLogger(__name__)

try:
    from google.generativeai.types import GenerationConfig, ThinkingConfig
    GENERATION_CONFIG_SUPPORTED = True
    logger.debug("GenerationConfig dan ThinkingConfig berhasil diimpor.")
except ImportError:
    logger.warning("Tidak dapat mengimpor GenerationConfig atau ThinkingConfig. Kontrol thinking budget mungkin tidak didukung oleh versi SDK ini.")
    GenerationConfig = None
    ThinkingConfig = None
    GENERATION_CONFIG_SUPPORTED = False



gemini_model_base = None
gemini_model_thinking = None
active_chats = {}

def configure_models():
    """Mengkonfigurasi model AI dasar dan thinking."""
    global gemini_model_base, gemini_model_thinking
    api_key_valid = True
    models_configured_successfully = True

    if not config.GEMINI_API_KEY:
        logger.error("Kunci API Gemini tidak ada.")
        api_key_valid = False
        return False

    if api_key_valid:
        try:
            genai.configure(api_key=config.GEMINI_API_KEY)
        except Exception as e:
             logger.error(f"Gagal mengkonfigurasi API Key Gemini: {e}")
             api_key_valid = False
             return False


    if api_key_valid:
        try:
            gemini_model_base = genai.GenerativeModel(
                config.GEMINI_MODEL_NAME,
                system_instruction=config.GEMINI_SYSTEM_INSTRUCTION
            )
            logger.info(f"Model dasar Gemini '{config.GEMINI_MODEL_NAME}' berhasil dikonfigurasi.")
        except Exception as e:
            logger.error(f"Gagal mengkonfigurasi model dasar Gemini '{config.GEMINI_MODEL_NAME}': {e}")
            gemini_model_base = None
            models_configured_successfully = False

    
    if api_key_valid:
        try:
            if config.THINKING_MODEL_NAME:
                gemini_model_thinking = genai.GenerativeModel(
                    config.THINKING_MODEL_NAME,
                    system_instruction=config.GEMINI_SYSTEM_INSTRUCTION
                )
                logger.info(f"Model thinking Gemini '{config.THINKING_MODEL_NAME}' berhasil dikonfigurasi.")
            else:
                logger.warning("Nama model thinking tidak diatur di config, fitur /td akan menggunakan model dasar.")
                gemini_model_thinking = gemini_model_base # Fallback

        except Exception as e:
            logger.error(f"Gagal mengkonfigurasi model thinking Gemini '{config.THINKING_MODEL_NAME}': {e}")
            gemini_model_thinking = None

    
    if not supabase_manager.supabase_client and config.SUPABASE_URL and config.SUPABASE_KEY:
         supabase_manager.init_supabase_client()

    return models_configured_successfully and gemini_model_base is not None


async def generate_response(prompt: str, chat_id: int) -> str | None:
    """
    Mengirim prompt ke Gemini menggunakan sesi chat yang sesuai (mempertahankan histori).
    Membuat sesi baru jika belum ada untuk chat_id tersebut.
    """
    global gemini_model_base

    if gemini_model_base is None:
        logger.error("Model dasar Gemini belum diinisialisasi.")
        return "Maaf, koneksi ke AI sedang bermasalah (Model dasar tidak siap)."

    if not supabase_manager.supabase_client:
        logger.warning("Supabase tidak aktif. Bot akan berjalan tanpa riwayat percakapan persisten.")
        
        try:
            chat_session_no_history = gemini_model_base.start_chat(history=[])
            response_no_history = await chat_session_no_history.send_message_async(prompt)
            if response_no_history.prompt_feedback and response_no_history.prompt_feedback.block_reason:
                reason = response_no_history.prompt_feedback.block_reason
                logger.warning(f"Permintaan (tanpa history Supabase) diblokir oleh Gemini untuk chat {chat_id} karena: {reason}")
                return f"Maaf, permintaan Anda tidak dapat diproses karena alasan keamanan: {reason}."
            return response_no_history.text
        except Exception as e_no_history:
            logger.error(f"Error saat generate content dari Gemini (tanpa history Supabase) untuk chat {chat_id}: {e_no_history}")
            return "Maaf, terjadi kesalahan saat menghubungi AI (tanpa history). Silakan coba lagi nanti."

    retrieved_history = supabase_manager.get_chat_history(chat_id)
    logger.debug(f"Riwayat yang diambil dari Supabase untuk chat {chat_id}: {len(retrieved_history)} pesan.")

    chat_session = gemini_model_base.start_chat(history=retrieved_history)

    logger.info(f"Mengirim prompt ke Gemini (Chat ID: {chat_id}): '{prompt[:100]}...' dengan {len(retrieved_history)} pesan history.")

    logger.info(f"Mengirim prompt ke Gemini (Chat ID: {chat_id}): '{prompt[:100]}...'")
    try:
        response = await chat_session.send_message_async(prompt)

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason
            logger.warning(f"Permintaan diblokir oleh Gemini (Chat ID: {chat_id}) karena: {reason}")
            return f"Maaf, permintaan Anda tidak dapat diproses karena alasan keamanan: {reason}. Riwayat chat mungkin terpengaruh."

        gemini_reply = response.text
        logger.info(f"Menerima balasan dari Gemini (Chat ID: {chat_id}): '{gemini_reply[:100]}...'")

        supabase_manager.add_message_to_history(chat_id, "user", prompt)
        supabase_manager.add_message_to_history(chat_id, "model", gemini_reply)

        return gemini_reply

    except Exception as e:
        logger.error(f"Terjadi error saat generate content dari Gemini (Chat ID: {chat_id}): {e}")
        return "Maaf, terjadi kesalahan saat menghubungi AI. Silakan coba lagi nanti."

async def generate_multimodal_response(chat_id: int, prompt_parts: list, text_prompt_for_history: str | None) -> str | None:
    """
    Menghasilkan respons dari Gemini berdasarkan input multimodal (teks dan/atau gambar).
    Menyimpan versi teks dari percakapan ke Supabase jika diaktifkan.

    Args:
        chat_id: ID chat pengguna.
        prompt_parts: List yang berisi bagian-bagian prompt. Bisa berupa string (untuk teks)
                      atau dictionary (untuk gambar, dengan format yang dikenali Gemini).
        text_prompt_for_history: Versi teks dari prompt pengguna (misalnya caption)
                                 untuk disimpan ke riwayat chat.
    Returns:
        String balasan dari Gemini, atau None jika terjadi error.
    """
    global gemini_model_base

    if gemini_model_base is None:
        logger.error("Model dasar Gemini belum diinisialisasi untuk multimodal.")
        return "Maaf, koneksi ke AI sedang bermasalah (Model dasar tidak siap)."

    retrieved_text_history = []
    if supabase_manager.supabase_client:
        retrieved_text_history = supabase_manager.get_chat_history(chat_id)
        logger.debug(f"Riwayat teks yang diambil dari Supabase untuk chat {chat_id}: {len(retrieved_text_history)} pesan.")
    else:
        logger.warning("Supabase tidak aktif. Pemrosesan multimodal akan berjalan tanpa riwayat percakapan persisten.")

    chat_session = gemini_model_base.start_chat(history=retrieved_text_history)

    
    num_images = sum(1 for part in prompt_parts if isinstance(part, dict) and 'inline_data' in part)
    logger.info(f"Mengirim ke Gemini untuk chat {chat_id}: prompt dengan {num_images} gambar. Teks utama (jika ada): '{text_prompt_for_history}'")

    try:
        response = await chat_session.send_message_async(prompt_parts)

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason
            logger.warning(f"Permintaan multimodal diblokir oleh Gemini (Chat ID: {chat_id}) karena: {reason}.")
            return f"Maaf, permintaan Anda (dengan gambar) tidak dapat diproses karena alasan keamanan: {reason}."

        gemini_reply_text = response.text
        logger.info(f"Menerima balasan multimodal dari Gemini (Chat ID: {chat_id}): '{gemini_reply_text[:100]}...'")

        if supabase_manager.supabase_client and text_prompt_for_history:
            supabase_manager.add_message_to_history(chat_id, "user", text_prompt_for_history)
            supabase_manager.add_message_to_history(chat_id, "model", gemini_reply_text)

        return gemini_reply_text

    except Exception as e:
        logger.error(f"Error saat generate content multimodal dari Gemini (Chat ID: {chat_id}): {e}", exc_info=True)
        return "Maaf, terjadi kesalahan saat memproses permintaan gambar Anda dengan AI."

async def generate_thinking_response(chat_id: int, prompt_parts: list, text_prompt_for_history: str | None) -> str | None:
    """Menghasilkan respons dari model THINKING (/td) Gemini."""
    global gemini_model_thinking

    if gemini_model_thinking is None:
        logger.error("Model thinking Gemini (/td) belum diinisialisasi atau gagal dikonfigurasi.")
        return "Maaf, fitur berpikir mendalam (/td) saat ini tidak tersedia."

    retrieved_text_history = []
    if supabase_manager.supabase_client:
        retrieved_text_history = supabase_manager.get_chat_history(chat_id)
        logger.debug(f"[TD] Riwayat teks yang diambil dari Supabase untuk chat {chat_id}: {len(retrieved_text_history)} pesan.")
    else:
        logger.warning("[TD] Supabase tidak aktif. Pemrosesan /td akan berjalan tanpa riwayat.")

    gen_config_td = None
    if GENERATION_CONFIG_SUPPORTED and config.THINKING_BUDGET is not None:
        try:
            think_config = ThinkingConfig(thinking_budget=config.THINKING_BUDGET)
            gen_config_td = GenerationConfig(thinking_config=think_config)
            logger.info(f"[TD] Menggunakan thinking_budget={config.THINKING_BUDGET} untuk chat {chat_id}.")
        except Exception as e_cfg:
            logger.warning(f"[TD] Gagal membuat GenerationConfig/ThinkingConfig (mungkin tidak didukung model {config.THINKING_MODEL_NAME}): {e_cfg}")
            gen_config_td = None
    elif not GENERATION_CONFIG_SUPPORTED:
         logger.debug(f"[TD] SDK tidak mendukung GenerationConfig/ThinkingConfig. Menggunakan default model.")
    else:
         logger.info(f"[TD] THINKING_BUDGET tidak diatur (None). Menggunakan default model {config.THINKING_MODEL_NAME}.")

    chat_session_td = gemini_model_thinking.start_chat(history=retrieved_text_history)

    num_images = sum(1 for part in prompt_parts if isinstance(part, dict) and 'inline_data' in part)
    logger.info(f"[TD] Mengirim ke model {config.THINKING_MODEL_NAME} untuk chat {chat_id}: prompt dengan {num_images} gambar. Teks: '{text_prompt_for_history}'")

    try:
        response = await chat_session_td.send_message_async(
            prompt_parts,
            generation_config=gen_config_td
        )

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason
            logger.warning(f"[TD] Permintaan diblokir oleh Gemini (Chat ID: {chat_id}) karena: {reason}.")
            return f"Maaf, permintaan berpikir mendalam Anda tidak dapat diproses karena alasan keamanan: {reason}."

        gemini_reply_text = response.text
        logger.info(f"[TD] Menerima balasan dari model THINKING (Chat ID: {chat_id}): '{gemini_reply_text[:100]}...'")

        if supabase_manager.supabase_client and text_prompt_for_history:
            supabase_manager.add_message_to_history(chat_id, "user", f"[TD] {text_prompt_for_history}")
            supabase_manager.add_message_to_history(chat_id, "model", gemini_reply_text)

        return gemini_reply_text

    except Exception as e:
        logger.error(f"Error saat generate content dari model THINKING ({config.THINKING_MODEL_NAME}) (Chat ID: {chat_id}): {e}", exc_info=True)
        return "Maaf, terjadi kesalahan saat mencoba berpikir mendalam."


def reset_chat_history(chat_id: int) -> bool:
    """Menghapus riwayat percakapan untuk chat_id tertentu dari Supabase."""
    if not supabase_manager.supabase_client:
        logger.warning("Supabase tidak aktif. Tidak dapat mereset riwayat percakapan.")
        return True

    logger.info(f"Mereset riwayat percakapan dari Supabase untuk chat_id {chat_id}.")
    return supabase_manager.delete_chat_history_db(chat_id)
