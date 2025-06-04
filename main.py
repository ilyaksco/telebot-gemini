import logging
import sys
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import config
import bot_handlers
import gemini_client
#import supabase_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Memulai bot...")

    if not config.TELEGRAM_TOKEN:
        logger.critical("CRITICAL: Token Telegram tidak ditemukan!")
        sys.exit("Token Telegram tidak ditemukan.")

    if not gemini_client.configure_models():
        logger.warning("WARNING: Gagal mengkonfigurasi satu atau lebih model Gemini! Fitur AI mungkin terbatas.")
        if not gemini_client.gemini_model_base:
             logger.critical("CRITICAL: Model dasar Gemini gagal dikonfigurasi! Bot tidak bisa berjalan.")
             sys.exit("Model dasar Gemini gagal.")


    application = Application.builder().token(config.TELEGRAM_TOKEN).build()

    registered_commands = []
    if hasattr(config, 'COMMANDS') and isinstance(config.COMMANDS, dict):
        for command_name, function_name_str in config.COMMANDS.items():
            try:
                handler_func = getattr(bot_handlers, function_name_str)
                application.add_handler(CommandHandler(command_name, handler_func))
                registered_commands.append(f"/{command_name}")
                logger.info(f"Command /{command_name} berhasil didaftarkan ke fungsi {function_name_str}.")
            except AttributeError:
                logger.error(f"ERROR: Fungsi '{function_name_str}' tidak ditemukan di bot_handlers.py untuk command '/{command_name}'. Command ini tidak akan berfungsi.")
            except Exception as e:
                logger.error(f"ERROR: Gagal mendaftarkan command '/{command_name}' : {e}")
    else:
        logger.warning("Variabel COMMANDS tidak ditemukan atau bukan dictionary di config.py.")

    if registered_commands:
        logger.info(f"Command yang terdaftar: {', '.join(registered_commands)}")
    else:
        logger.info("Tidak ada command eksplisit yang terdaftar dari config.COMMANDS.")

    if config.IMAGE_UNDERSTANDING_ENABLED:
        application.add_handler(MessageHandler(filters.PHOTO, bot_handlers.handle_photo_message))
        logger.info("MessageHandler untuk foto (IMAGE_UNDERSTANDING_ENABLED=True) telah ditambahkan.")
    else:
        logger.info("Fitur pemahaman gambar dinonaktifkan via config. IMAGE_UNDERSTANDING_ENABLED=False.")

    application.add_handler(MessageHandler(filters.TEXT & (~filters.UpdateType.EDITED_MESSAGE), bot_handlers.handle_message))
    logger.info("MessageHandler untuk pesan teks biasa telah ditambahkan.")

    logger.info("Bot siap menerima pesan...")
    application.run_polling()
    logger.info("Bot dihentikan.")


if __name__ == '__main__':
    main()
