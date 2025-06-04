# Telegram Gemini Bot 

## Fitur Utama

* Merespons pesan teks menggunakan Google Gemini.
* Dapat menerima satu atau beberapa gambar (album) dan mendeskripsikannya.
* Dapat berfungsi di grup, merespons jika di reply atau di triger dengan perintah khusus (misalnya `/ai`, `/ask`).
* Perintah khusus untuk meminta AI berpikir/menalar.
* Menyimpan riwayat chat per pengguna di Supabase, sehingga konteks tidak hilang saat bot di-restart.
* Banyak aspek bot dapat dikonfigurasi melalui file `config.py`.

## Persyaratan

1.  **Akun PythonAnywhere (Jika kalian deploy di Pythonanywhere.com):** atau kalian bisa deploy di VPS Pribadi kalian.
2.  **Akun Supabase:** kalian memerlukan akun [Supabase](https://supabase.com) untuk menyimpan riwayat percakapan.
3.  **Kunci API Telegram:** Dapatkan token bot dari [@BotFather](https://t.me/BotFather) di Telegram.
4.  **Kunci API Gemini:** Dapatkan kunci API dari [Google AI Studio](https://aistudio.google.com/apikey).
5.  **Kunci dan URL Supabase:** Dapatkan **URL Proyek** dan **Kunci API (`service_role` secret)** dari pengaturan proyek Supabase kalian (Project Settings > Data API).
6.  **Versi Python:** Direkomendasikan Python 3.10 keatas.

## Langkah-langkah Penyiapan di PythonAnywhere

1.  **Buka Konsol Bash:**
    * Login ke akun PythonAnywhere.
    * Buka tab "Consoles".
    * Mulai konsol "Bash" baru.

2.  **Clone Repository:**
    * Di dalam konsol Bash, clone repository ini:
        ```bash
        git clone https://github.com/ilyaksco/telebot-gemini.git
        ```
        * jika kalian belum menginstall git, install dulu:
        ```bash
        sudo apt-get install git-all
        ```
    * Masuk ke direktori proyek:
        ```bash
        cd telebot-gemini
        ```

3.  **Buat dan Aktifkan Lingkungan Virtual (Virtual Environment):**
    * Sangat disarankan untuk menggunakan lingkungan virtual:
        ```bash
        python3.11 -m venv myenv 
        ```
    * Aktifkan lingkungan virtual:
        ```bash
        source myenv/bin/activate
        ```
    * kalian akan melihat `(myenv)` di awal baris perintah jika berhasil.

4.  **Siapkan Proyek Supabase:**
    * Login ke dashboard Supabase kalian.
    * Buat proyek baru jika belum ada.
    * Masuk ke "SQL Editor".
    * Jalankan SQL berikut untuk membuat tabel `chat_history`:
        ```sql
        CREATE TABLE chat_history (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            message_timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'model')),
            content TEXT NOT NULL
        );
        CREATE INDEX idx_chat_history_chat_id_timestamp ON chat_history (chat_id, message_timestamp DESC);
        ```
    * Catat **URL Proyek** dan **Kunci API `service_role`** dari menu "Project Settings" > "Data API". 

5.  **Buat Berkas `.env`:**
    * Kembali ke konsol Bash (di dalam direktori `telebot-gemini`).
    * Buat berkas bernama `.env`:
        ```bash
        nano .env
        ```
    * Masukkan kunci API dan URL kalian dengan format berikut:
        ```dotenv
        TELEGRAM_TOKEN=NilaiTokenBotTelegramKalian
        GEMINI_API_KEY=NilaiKunciAPIGeminiKalian
        SUPABASE_URL=URLProyekSupabaseKalian
        SUPABASE_KEY=KunciAPIServiceRoleSupabaseKalian
        ```
    * Simpan berkas dan keluar (`Ctrl+X`, lalu `Y`, lalu `Enter`).

6.  **Instal Pustaka yang Dibutuhkan:**
    * Pastikan kalian masih berada di dalam direktori proyek (`telebot-gemini-multimodal`) dan lingkungan virtual (`myenv`) aktif.
    * Instal semua pustaka dari `requirements.txt`:
        ```bash
        pip install -r requirements.txt
        ```

7.  **Jalankan Bot (Untuk Tes):**
    * Pastikan `myenv` aktif.
    * Jalankan skrip utama bot:
        ```bash
        python main.py
        ```
    * Periksa output log di konsol untuk memastikan tidak ada error saat startup. Coba kirim pesan ke bot kalian.
    * Hentikan bot dengan `Ctrl+C`.

## Konfigurasi Tambahan (Opsional via `config.py`)

kalian dapat menyesuaikan bot dengan mengedit file `config.py`:

* **`GEMINI_SYSTEM_INSTRUCTION`**: Ubah instruksi sistem dasar untuk AI Gemini.
* **`GEMINI_MODEL_NAME`**: Ganti model Gemini utama yang digunakan (misal: `gemini-2.0-flash`).
* **`GROUP_TRIGGER_COMMANDS`**: Tambah atau ubah daftar perintah teks (diawali `/`) yang akan memicu respons bot di grup (selain reply). Contoh: `["/ai apa itu AI?"]`.
* **Fitur Pemahaman Gambar:**
    * `IMAGE_UNDERSTANDING_ENABLED`: Setel `True` atau `False`.
    * `MAX_IMAGE_INPUT`: Atur batas maksimal gambar per album/permintaan (misalnya `5`).
    * `DEFAULT_PROMPT_FOR_IMAGE_IF_NO_CAPTION`: Teks prompt default jika gambar dikirim tanpa caption.
* **Fitur Penalaran:**
`THINKING_MODEL_NAME`: Tentukan model Gemini khusus untuk perintah `/td` (misal: `gemini-2.5-flash-preview-04-17`).
