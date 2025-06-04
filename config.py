import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi Kunci API

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not TELEGRAM_TOKEN:
    logging.warning("Token Telegram tidak ditemukan! Atur di Secrets.")
if not GEMINI_API_KEY:
    logging.warning("Kunci API Gemini tidak ditemukan! Atur di Secrets.")
if not SUPABASE_URL or not SUPABASE_KEY:
    logging.warning("SUPABASE_URL atau SUPABASE_KEY tidak ditemukan. Fitur Supabase tidak akan aktif.")

# Konfigurasi Gemini
# Pilih model Gemini yang ingin kamu gunakan, pastikan kamu menggunakan nama model yang benar yang diambil dari nama versi yang ada di https://ai.google.dev/gemini-api/docs/models    (contoh: gemini-2.0-flash)
GEMINI_MODEL_NAME = 'gemini-2.0-flash'

# INTRUKSI SISTEM (SYSTEM PROMPT) UNTUK GEMINI
# Gunakan ini untuk mengatur kepribadian atau persona AI.
# Ubah teks di bawah ini sesuai keinginan kamu.
GEMINI_SYSTEM_INSTRUCTION = "menjadi orang yang sangat pintar"

# Pengaturan untuk Image Understanding
IMAGE_UNDERSTANDING_ENABLED = True  # True untuk aktifkan, False untuk nonaktifkan
MAX_IMAGE_INPUT = 5               # Batas maksimal gambar yang bisa diproses dalam satu permintaan
MEDIA_GROUP_PROCESSING_DELAY = 2.5 # Detik (misalnya 2-3 detik) untuk menunggu semua gambar dalam album terkumpul
DEFAULT_PROMPT_FOR_IMAGE_IF_NO_CAPTION = "Jelaskan semua gambar ini dan apa kaitannya satu sama lain" # Prompt default jika gambar dikirim tanpa caption sama sekali

# Konfigurasi Perintah (commands)
# jika ada commands yang lain tambahkan di sini, jangan lupa di daftarkan di bot_handlers.py dan di main.py di bagian application.add_handler(CommandHandler(command_name, handler_func))

COMMANDS = {
    "start": "start",               # /start memanggil fungsi start
    "reset": "reset_chat",          # /reset memanggil fungsi reset_chat
    "about": "about",               # /about memanggil fungsi about
    "help": "help_command",         # /help memanggil fungsi help_command
    "td": "think_deeper_command",
}

# untuk grupp
# tambahkan perintah sesuka kalian, Pastikan perintah diawali dengan karakter /
GROUP_TRIGGER_COMMANDS = ["/ai", "/ask"]

# untuk ingatan
# Jumlah maksimal pesan yang diambil dari history untuk konteks Gemini
CHAT_HISTORY_MESSAGES_LIMIT = 20

# fitur thiking
THINKING_MODEL_NAME = 'gemini-2.5-flash-preview-04-17'
THINKING_BUDGET = 4096 
THINKING_INDICATOR_MESSAGE = "🤔 Sedang berpikir mendalam..."

