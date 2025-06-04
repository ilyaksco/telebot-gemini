import logging
import asyncio
from telegram import Update, Message
from telegram.constants import ChatAction, ParseMode, ChatType
from telegram.ext import ContextTypes, CallbackContext
from telegram.error import BadRequest, RetryAfter, TelegramError
import gemini_client
import config
from config import (
    GROUP_TRIGGER_COMMANDS,
    IMAGE_UNDERSTANDING_ENABLED,
    MAX_IMAGE_INPUT,
    MEDIA_GROUP_PROCESSING_DELAY,
    DEFAULT_PROMPT_FOR_IMAGE_IF_NO_CAPTION,
)

from markdown_utils import ensure_valid_markdown

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = getattr(config, 'TELEGRAM_MAX_MESSAGE_LENGTH',
                                      4096)
THINKING_INDICATOR_MESSAGE = getattr(config, 'THINKING_INDICATOR_MESSAGE',
                                     "🤔 Sedang berpikir mendalam...")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.message.chat_id
    if gemini_client.reset_chat_history(chat_id):
        logger.info(
            f"Riwayat chat untuk {chat_id} direset karena perintah /start.")
    else:
        logger.info(
            f"Tidak ada riwayat chat aktif untuk {chat_id} untuk direset saat /start."
        )
    await update.message.reply_html(
        f"Halo {user.mention_html()}! aku adalah bot AI yang terhubung ke Gemini. ",
    )
    logger.info(
        f"User {user.id} ({user.first_name}) memulai bot di chat {chat_id}.")


async def handle_message(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user_message = message.text
    user = update.effective_user
    chat_id = message.chat_id
    chat_type = message.chat.type
    message_id = message.message_id

    if not user_message:
        logger.debug(
            f"Pesan tanpa teks diterima dari {user.id} di chat {chat_id}. Diabaikan."
        )
        return

    logger.info(
        f"Menerima pesan (message_id: {message_id}) dari {user.id} ({user.first_name}) di chat {chat_id} (tipe: {chat_type}): \"{user_message[:100]}\""
    )

    should_respond = False
    actual_message_to_process = user_message
    trigger_command_used = None

    if chat_type == ChatType.PRIVATE:
        should_respond = True
        logger.debug(f"Pesan di private chat {chat_id}. Bot akan merespon.")
    elif chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        logger.debug(f"Pesan di grup {chat_id}. Mengecek kondisi respon...")
        bot_id = context.bot.id
        if message.reply_to_message and message.reply_to_message.from_user.id == bot_id:
            should_respond = True
            actual_message_to_process = user_message
            logger.info(
                f"Pesan di grup {chat_id} adalah reply ke bot. Teks diproses: \"{actual_message_to_process[:100]}\"."
            )
        else:
            msg_lower = user_message.lower()
            for trigger_command_config in GROUP_TRIGGER_COMMANDS:
                trigger = trigger_command_config.lower()
                if msg_lower.startswith(trigger):
                    if len(msg_lower) == len(trigger):
                        should_respond = True
                        actual_message_to_process = ""
                        trigger_command_used = trigger_command_config
                        logger.info(
                            f"Pesan di grup {chat_id} adalah trigger command '{trigger_command_config}' saja."
                        )
                        break
                    elif len(msg_lower) > len(trigger) and msg_lower[len(
                            trigger)].isspace():
                        should_respond = True
                        actual_message_to_process = user_message[
                            len(trigger):].strip()
                        trigger_command_used = trigger_command_config
                        logger.info(
                            f"Pesan di grup {chat_id} menggunakan trigger '{trigger_command_config}'. Teks diproses: \"{actual_message_to_process[:100]}\"."
                        )
                        break
            if not should_respond:
                logger.debug(
                    f"Pesan di grup {chat_id} bukan reply ke bot dan tidak menggunakan trigger. Bot tidak merespon."
                )

    if not should_respond:
        logger.debug(
            f"Kondisi respon tidak terpenuhi untuk pesan di chat {chat_id}. Bot tidak mengirim balasan."
        )
        return

    if not actual_message_to_process and chat_type in [
            ChatType.GROUP, ChatType.SUPERGROUP
    ] and trigger_command_used:
        logger.info(
            f"Pesan proses kosong setelah trigger command '{trigger_command_used}' di grup {chat_id}."
        )
        await message.reply_text(
            f"Mohon sertakan pertanyaan Anda setelah `{trigger_command_used}` atau periksa /help.",
            parse_mode=ParseMode.MARKDOWN)
        return

    if not actual_message_to_process and not (
            chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]
            and trigger_command_used):
        logger.info(
            f"Pesan proses kosong (bukan dari trigger command di grup) di chat {chat_id}. Bot tidak mengirim ke Gemini."
        )

        return

    await context.bot.send_chat_action(chat_id=chat_id,
                                       action=ChatAction.TYPING)
    text_parts = [actual_message_to_process
                  ] if actual_message_to_process else []

    gemini_reply_raw = await gemini_client.generate_multimodal_response(
        chat_id=chat_id,
        prompt_parts=text_parts,
        text_prompt_for_history=actual_message_to_process
        if actual_message_to_process else None)

    if gemini_reply_raw:
        gemini_reply_markdown = ensure_valid_markdown(gemini_reply_raw)
        try:
            await message.reply_text(gemini_reply_markdown,
                                     parse_mode=ParseMode.MARKDOWN)
            logger.info(
                f"Mengirim balasan Gemini (Markdown) ke chat {chat_id} (reply ke message_id: {message.message_id})"
            )
        except BadRequest as e:
            if "can't parse entities" in str(e).lower():
                logger.warning(
                    f"Gagal mengirim sebagai Markdown ke chat {chat_id}: {e}. Mencoba plain text."
                )
                gemini_reply_plain = gemini_reply_raw  # Kirim teks asli jika Markdown gagal total
                try:
                    await message.reply_text(gemini_reply_plain)
                    logger.info(
                        f"Mengirim balasan Gemini (Plain Text Fallback) ke chat {chat_id} (reply ke message_id: {message.message_id})"
                    )
                except Exception as fallback_e:
                    logger.error(
                        f"Gagal mengirim fallback plain text ke chat {chat_id}: {fallback_e}",
                        exc_info=True)
                    await message.reply_text(
                        "Maaf, saya kesulitan mengirim balasan. Silakan coba lagi."
                    )
            else:
                logger.error(
                    f"Error BadRequest (bukan parsing) saat mengirim balasan ke chat {chat_id}: {e}",
                    exc_info=True)
                await message.reply_text(
                    "Maaf, terjadi kesalahan saat mengirim balasan.")
        except Exception as e:
            logger.error(
                f"Error tak terduga saat mengirim balasan ke chat {chat_id}: {e}",
                exc_info=True)
            await message.reply_text(
                "Maaf, terjadi kesalahan tak terduga saat mengirim balasan.")
    else:
        await message.reply_text(
            "Maaf, terjadi kesalahan internal saat memproses permintaan Anda.")
        logger.error(
            f"Gagal mendapatkan balasan valid dari gemini_client untuk chat {chat_id} untuk pesan: \"{actual_message_to_process[:100]}\""
        )


async def reset_chat(update: Update,
                     context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user = update.effective_user
    if gemini_client.reset_chat_history(chat_id):
        await update.message.reply_text(
            "Oke, saya telah melupakan percakapan kita sebelumnya di chat ini."
        )
        logger.info(
            f"User {user.id} ({user.first_name}) mereset riwayat di chat {chat_id}."
        )
    else:
        await update.message.reply_text(
            "Gagal mereset riwayat atau memang belum ada percakapan.")
        logger.warning(
            f"User {user.id} ({user.first_name}) mencoba mereset riwayat di chat {chat_id}, operasi reset mengembalikan False."
        )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat_id = update.message.chat_id
    logger.info(
        f"User {user.id} ({user.first_name}) memanggil /about di chat {chat_id}."
    )

    about_text_raw = (
        "*🤖Telegram Gemini Bot Multimodal*\n\n"
        "Bot ini menggunakan Google Gemini untuk merespons pesan teks dan menganalisis gambar.\n\n"
        "Beberapa fitur utama:\n"
        "- Merespons pesan teks.\n"
        "- Menganalisis satu atau beberapa gambar.\n"
        "- Berfungsi di grup (jika di-reply atau dipicu dengan perintah).\n\n"
        "Untuk daftar perintah, ketik `/help`.")

    about_text_markdown = ensure_valid_markdown(about_text_raw)
    await update.message.reply_text(about_text_markdown,
                                    parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    logger.info(
        f"User {user.id} ({user.first_name}) memanggil /help di chat {update.message.chat_id}."
    )

    trigger_commands_text_list = [f"`{cmd}`" for cmd in GROUP_TRIGGER_COMMANDS]
    trigger_commands_text = ", ".join(trigger_commands_text_list)
    if not GROUP_TRIGGER_COMMANDS:
        trigger_commands_text = "(tidak ada yang diatur di config.py)"
        example_command = "/ai"
    else:
        example_command = GROUP_TRIGGER_COMMANDS[0]

    help_text_raw = (
        "Butuh bantuan? Berikut beberapa perintah yang bisa Anda gunakan:\n\n"
        "`/start` - Memulai atau memulai ulang bot dan mereset percakapan.\n"
        "`/reset` - Melupakan seluruh percakapan kita di chat ini.\n"
        "`/about` - Informasi tentang bot ini.\n"
        "`/help` - Menampilkan pesan bantuan ini.\n"
        f"`/td` - Meminta AI berpikir lebih mendalam tentang suatu topik.\n\n"
        f"**Cara Berinteraksi dengan AI:**\n"
        f"- Di chat pribadi dengan saya, Anda bisa langsung mengirimkan pesan atau pertanyaan.\n"
        f"- Anda juga bisa mengirim gambar (dengan atau tanpa caption) untuk dijelaskan oleh AI (maks {MAX_IMAGE_INPUT} gambar per album).\n"
        f"- Di grup, Anda bisa:\n"
        f"  1. Membalas (reply) salah satu pesan saya.\n"
        f"  2. Menggunakan perintah pemicu seperti `{example_command} pertanyaan Anda`.\n"
        f"  3. Mengirim foto dengan caption yang berisi perintah pemicu (misal: `{example_command} jelaskan foto ini`).\n\n"
        f"Perintah pemicu teks yang aktif di grup saat ini: {trigger_commands_text}"
    )
    help_text_markdown = ensure_valid_markdown(help_text_raw)
    await update.message.reply_text(help_text_markdown,
                                    parse_mode=ParseMode.MARKDOWN)


async def handle_photo_message(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> None:
    if not IMAGE_UNDERSTANDING_ENABLED:
        return

    message = update.message
    user = update.effective_user
    chat_id = message.chat_id
    chat_type = message.chat.type
    bot_id = context.bot.id

    should_respond = False
    actual_caption_to_process = message.caption
    trigger_command_used_info = None

    if chat_type == ChatType.PRIVATE:
        should_respond = True
        logger.debug(f"Foto di private chat {chat_id}. Bot akan merespon.")
    elif chat_type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        logger.debug(f"Foto di grup {chat_id}. Mengecek kondisi respon...")
        if message.reply_to_message and message.reply_to_message.from_user.id == bot_id:
            should_respond = True
            
            logger.info(
                f"Foto di grup {chat_id} adalah reply ke bot. Bot akan merespon."
            )
        elif message.caption:
            caption_lower = message.caption.lower()
            for trigger_command_config in GROUP_TRIGGER_COMMANDS:
                trigger = trigger_command_config.lower()
                if caption_lower.startswith(trigger):
                    should_respond = True
                    if len(caption_lower) == len(trigger) or caption_lower[len(
                            trigger)].isspace():
                        actual_caption_to_process = message.caption[
                            len(trigger):].strip()
                        trigger_command_used_info = trigger_command_config
                        logger.info(
                            f"Foto di grup {chat_id} menggunakan trigger command '{trigger_command_config}' di caption. Caption diproses: \"{actual_caption_to_process}\"."
                        )
                    else:  
                        should_respond = False  
                    break
            if not should_respond and message.caption:  
                logger.debug(
                    f"Foto di grup {chat_id} (dengan caption) bukan reply ke bot dan caption tidak menggunakan trigger. Bot tidak merespon."
                )
        else:  
            logger.debug(
                f"Foto di grup {chat_id} (tanpa caption) bukan reply ke bot. Bot tidak merespon."
            )

    if not should_respond:
        logger.debug(
            f"Kondisi respon tidak terpenuhi untuk foto di chat {chat_id} (message_id: {message.message_id}). Bot tidak memproses foto."
        )
        return

    photo_file_id = message.photo[-1].file_id
    logger.info(
        f"Memproses foto dari user {user.id} ({user.first_name}) di chat {chat_id}. File ID: {photo_file_id}, Caption Asli: '{message.caption}', Caption untuk AI: '{actual_caption_to_process}'"
    )

    if message.media_group_id:
        media_group_id_str = str(message.media_group_id)
        logger.debug(
            f"Foto adalah bagian dari media group: {media_group_id_str}")

        if 'media_groups' not in context.bot_data:
            context.bot_data['media_groups'] = {}
        if chat_id not in context.bot_data['media_groups']:
            context.bot_data['media_groups'][chat_id] = {}
        if media_group_id_str not in context.bot_data['media_groups'][chat_id]:
            context.bot_data['media_groups'][chat_id][media_group_id_str] = []

        current_images_in_group = context.bot_data['media_groups'][chat_id][
            media_group_id_str]
        is_duplicate = any(img['message_id'] == message.message_id
                           for img in current_images_in_group)

        if not is_duplicate and len(current_images_in_group) < MAX_IMAGE_INPUT:
            current_images_in_group.append({
                'file_id':
                photo_file_id,
                'caption_for_ai':
                actual_caption_to_process,
                'original_caption':
                message.caption,
                'message_id':
                message.message_id,
                'is_reply_to_bot':
                (message.reply_to_message
                 and message.reply_to_message.from_user.id == bot_id),
                'trigger_command_used_info':
                trigger_command_used_info
            })
            logger.debug(
                f"Foto {photo_file_id} (msg_id: {message.message_id}) ditambahkan ke media group {media_group_id_str}. Total: {len(current_images_in_group)}"
            )
        elif not is_duplicate and len(
                current_images_in_group) >= MAX_IMAGE_INPUT:
            logger.warning(
                f"Media group {media_group_id_str} sudah mencapai batas {MAX_IMAGE_INPUT} gambar. Foto {photo_file_id} (msg_id: {message.message_id}) tidak ditambahkan."
            )
            notified_key = f"notified_overflow_{chat_id}_{media_group_id_str}"
            if not context.bot_data.get(notified_key):
                await message.reply_text(
                    f"Anda mengirim terlalu banyak gambar dalam satu album. Hanya {MAX_IMAGE_INPUT} gambar pertama yang akan diproses.",
                    quote=True)
                context.bot_data[notified_key] = True
        elif is_duplicate:
            logger.debug(
                f"Foto {photo_file_id} (msg_id: {message.message_id}) adalah duplikat dalam media group {media_group_id_str}, diabaikan."
            )

        job_name = f"process_media_group_{chat_id}_{media_group_id_str}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for old_job in current_jobs:
            old_job.schedule_removal()
            logger.debug(f"Job lama '{old_job.name}' dihapus untuk direset.")
        context.job_queue.run_once(process_media_group_callback,
                                   MEDIA_GROUP_PROCESSING_DELAY,
                                   data={
                                       'media_group_id': media_group_id_str,
                                       'chat_id': chat_id,
                                       'user_id': user.id
                                   },
                                   name=job_name)
        logger.debug(
            f"Job '{job_name}' dijadwalkan/direset dalam {MEDIA_GROUP_PROCESSING_DELAY} detik."
        )
    else:
        logger.debug(f"Foto {photo_file_id} adalah gambar tunggal.")
        await context.bot.send_chat_action(chat_id=chat_id,
                                           action=ChatAction.TYPING)
        try:
            photo_tg_file = await context.bot.get_file(photo_file_id)
            image_bytes = bytes(await photo_tg_file.download_as_bytearray())

            prompt_parts = []
            text_prompt = actual_caption_to_process
            if not text_prompt and trigger_command_used_info:
                text_prompt = DEFAULT_PROMPT_FOR_IMAGE_IF_NO_CAPTION
            elif not text_prompt:
                text_prompt = DEFAULT_PROMPT_FOR_IMAGE_IF_NO_CAPTION

            if text_prompt:
                prompt_parts.append(text_prompt)

            image_part_dict = {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            }
            prompt_parts.append(image_part_dict)

            logger.info(
                f"Mengirim 1 gambar dan prompt '{text_prompt}' ke Gemini untuk chat {chat_id}."
            )
            gemini_reply_raw = await gemini_client.generate_multimodal_response(
                chat_id=chat_id,
                prompt_parts=prompt_parts,
                text_prompt_for_history=text_prompt)

            if gemini_reply_raw:
                gemini_reply_markdown = ensure_valid_markdown(gemini_reply_raw)
                await message.reply_text(gemini_reply_markdown,
                                         parse_mode=ParseMode.MARKDOWN,
                                         quote=True)
            else:
                await message.reply_text(
                    "Maaf, saya tidak bisa memproses gambar ini saat ini.",
                    quote=True)  
        except Exception as e:
            logger.error(
                f"Error saat memproses foto tunggal {photo_file_id} untuk chat {chat_id}: {e}",
                exc_info=True)
            await message.reply_text(
                "Terjadi kesalahan saat memproses gambar Anda.",
                quote=True)  


async def process_media_group_callback(context: CallbackContext):
    job_data = context.job.data
    media_group_id_str = job_data['media_group_id']
    chat_id = job_data['chat_id']

    logger.info(
        f"Callback dipanggil untuk memproses media group {media_group_id_str} dari chat {chat_id}."
    )

    media_group_images_data = None
    if 'media_groups' in context.bot_data and \
       chat_id in context.bot_data['media_groups'] and \
       media_group_id_str in context.bot_data['media_groups'][chat_id]:
        media_group_images_data = context.bot_data['media_groups'][
            chat_id].pop(media_group_id_str)
        if not context.bot_data['media_groups'][chat_id]:
            context.bot_data['media_groups'].pop(chat_id)
        if not context.bot_data['media_groups']:
            context.bot_data.pop('media_groups')
    context.bot_data.pop(f"notified_overflow_{chat_id}_{media_group_id_str}",
                         None)

    if not media_group_images_data:
        logger.warning(
            f"Tidak ada data gambar valid ditemukan untuk media group {media_group_id_str} di chat {chat_id} pada saat callback."
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id,
                                       action=ChatAction.TYPING)
    prompt_parts = []
    final_text_prompt = None

    for img_detail in media_group_images_data:
        if img_detail.get('trigger_command_used_info') or img_detail.get(
                'is_reply_to_bot'):
            final_text_prompt = img_detail.get(
                'caption_for_ai', "")  
            if final_text_prompt:
                logger.info(
                    f"Menggunakan caption dari gambar yang di-trigger/reply: '{final_text_prompt}' untuk media group."
                )
            else:  
                logger.info(
                    f"Gambar di-trigger/reply tapi caption_for_ai kosong. Akan menggunakan prompt default jika tidak ada caption lain."
                )
            break

    if final_text_prompt is None:
        for img_detail in media_group_images_data:
            if img_detail.get('caption_for_ai'):
                final_text_prompt = img_detail.get('caption_for_ai')
                logger.info(
                    f"Menggunakan caption_for_ai pertama yang tersedia: '{final_text_prompt}' untuk media group."
                )
                break

    if not final_text_prompt:
        final_text_prompt = DEFAULT_PROMPT_FOR_IMAGE_IF_NO_CAPTION
        logger.info(
            f"Tidak ada caption signifikan. Menggunakan prompt default: '{final_text_prompt}'."
        )

    if final_text_prompt is not None:
        prompt_parts.append(final_text_prompt)
    text_prompt_for_history = final_text_prompt

    images_processed_count = 0
    first_message_id_in_group = media_group_images_data[0].get(
        'message_id') if media_group_images_data else None

    for img_detail in media_group_images_data:
        if images_processed_count >= MAX_IMAGE_INPUT:
            logger.warning(
                f"Mencapai batas MAX_IMAGE_INPUT ({MAX_IMAGE_INPUT}) saat memproses gambar untuk media group {media_group_id_str}"
            )
            break
        try:
            photo_tg_file = await context.bot.get_file(img_detail['file_id'])
            image_bytes = bytes(await photo_tg_file.download_as_bytearray())
            image_part_dict = {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_bytes
                }
            }
            prompt_parts.append(image_part_dict)
            images_processed_count += 1
        except Exception as e:
            logger.error(
                f"Gagal mengunduh atau membuat Part untuk file_id {img_detail['file_id']} dalam media group {media_group_id_str}: {e}",
                exc_info=True)

    if images_processed_count == 0:
        logger.warning(
            f"Tidak ada gambar yang berhasil diunduh/diproses untuk media group {media_group_id_str}."
        )
        try:
            await context.bot.send_message(
                chat_id,
                "Maaf, saya gagal memproses gambar-gambar yang Anda kirim dalam album ini.",
                reply_to_message_id=first_message_id_in_group)
        except Exception:
            await context.bot.send_message(
                chat_id,
                "Maaf, saya gagal memproses gambar-gambar yang Anda kirim dalam album ini."
            )
        return

    logger.info(
        f"Mengirim {images_processed_count} gambar dan prompt '{text_prompt_for_history}' dari media group {media_group_id_str} ke Gemini."
    )
    reply_to_msg_id = first_message_id_in_group

    try:
        gemini_reply_raw = await gemini_client.generate_multimodal_response(
            chat_id=chat_id,
            prompt_parts=prompt_parts,
            text_prompt_for_history=text_prompt_for_history)
        if gemini_reply_raw:
            gemini_reply_markdown = ensure_valid_markdown(gemini_reply_raw)
            # Menggunakan send_long_message agar konsisten dan menangani pesan panjang + fallback Markdown
            await send_long_message(
                context,
                chat_id,
                gemini_reply_markdown,
                reply_to_message_id=reply_to_msg_id,
                parse_mode=ParseMode.MARKDOWN,
                original_text_if_markdown_fails=gemini_reply_raw)
        else:
            err_msg = "Maaf, saya tidak bisa memproses gambar-gambar ini saat ini (tidak ada respons AI)."
            logger.warning(
                f"Respons Gemini kosong untuk media group {media_group_id_str}"
            )
            try:
                await context.bot.send_message(
                    chat_id, err_msg, reply_to_message_id=reply_to_msg_id)
            except BadRequest:
                await context.bot.send_message(chat_id, err_msg)
    except Exception as e:
        logger.error(
            f"Error saat memproses media group {media_group_id_str} dengan Gemini: {e}",
            exc_info=True)
        try:
            await context.bot.send_message(
                chat_id,
                "Terjadi kesalahan internal saat memproses album gambar Anda.",
                reply_to_message_id=reply_to_msg_id)
        except BadRequest:
            await context.bot.send_message(
                chat_id,
                "Terjadi kesalahan internal saat memproses album gambar Anda.")


async def think_deeper_command(update: Update,
                               context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    chat_id = message.chat_id
    user = update.effective_user
    prompt_text = ""
    target_message = message

    if context.args:
        prompt_text = " ".join(context.args)
        logger.info(
            f"Perintah /td dari user {user.id} di chat {chat_id} dengan argumen: {prompt_text[:50]}..."
        )
    elif message.reply_to_message and message.reply_to_message.text:
        prompt_text = message.reply_to_message.text
        target_message = message.reply_to_message
        logger.info(
            f"Perintah /td dari user {user.id} di chat {chat_id} sebagai balasan ke teks: {prompt_text[:50]}..."
        )
    else:
        await message.reply_text(
            "Gunakan `/td <pertanyaan Anda>` atau balas pesan teks yang ingin dipikirkan lebih dalam dengan `/td`.",
            parse_mode=ParseMode.MARKDOWN)
        return

    if not prompt_text:
        await message.reply_text(
            "Mohon berikan pertanyaan atau balas pesan teks yang valid.")
        return

    thinking_indicator_msg: Message | None = None
    try:
        thinking_indicator_msg = await target_message.reply_text(
            THINKING_INDICATOR_MESSAGE)  # Plain text indicator
        if thinking_indicator_msg:
            logger.info(
                f"Pesan indikator BERHASIL dikirim (msg_id: {thinking_indicator_msg.message_id})."
            )
    except Exception as e:
        logger.error(
            f"Gagal mengirim pesan indikator thinking ke chat {chat_id}: {e}",
            exc_info=True)

    await context.bot.send_chat_action(chat_id=chat_id,
                                       action=ChatAction.TYPING)
    prompt_parts = [prompt_text]
    text_prompt_for_history = prompt_text

    gemini_reply_raw = await gemini_client.generate_thinking_response(
        chat_id=chat_id,
        prompt_parts=prompt_parts,
        text_prompt_for_history=text_prompt_for_history)
    final_text_raw = gemini_reply_raw if gemini_reply_raw else "Maaf, saya tidak dapat memberikan respons setelah berpikir mendalam saat ini."

    # Validasi Markdown sebelum dikirim atau diedit
    final_text_markdown = ensure_valid_markdown(final_text_raw)

    message_too_long = len(
        final_text_markdown) > TELEGRAM_MAX_MESSAGE_LENGTH - 10

    if message_too_long:
        logger.warning(
            f"Respons /td terlalu panjang ({len(final_text_markdown)} chars). Akan dipecah."
        )
        if thinking_indicator_msg:
            try:
                await context.bot.delete_message(
                    chat_id=thinking_indicator_msg.chat_id,
                    message_id=thinking_indicator_msg.message_id)
                logger.info(
                    f"Pesan indikator thinking (msg_id: {thinking_indicator_msg.message_id}) dihapus karena respons panjang."
                )
            except Exception as del_err:
                logger.warning(
                    f"Gagal menghapus pesan indikator thinking (msg_id: {thinking_indicator_msg.message_id}): {del_err}"
                )
        await send_long_message(context,
                                chat_id,
                                final_text_markdown,
                                reply_to_message_id=target_message.message_id,
                                parse_mode=ParseMode.MARKDOWN,
                                original_text_if_markdown_fails=final_text_raw)
    elif thinking_indicator_msg:
        try:
            await context.bot.edit_message_text(
                text=final_text_markdown,
                chat_id=thinking_indicator_msg.chat_id,
                message_id=thinking_indicator_msg.message_id,
                parse_mode=ParseMode.MARKDOWN)
            logger.info(
                f"Pesan indikator thinking (msg_id: {thinking_indicator_msg.message_id}) diedit dengan respons /td."
            )
        except BadRequest as edit_err:
            if "message is not modified" in str(edit_err).lower():
                logger.info(
                    f"Pesan /td tidak dimodifikasi (kemungkinan sama atau error parse Markdown saat edit): {edit_err}"
                )
                # Jika edit gagal karena Markdown, coba kirim sbg pesan baru
                await send_long_message(
                    context,
                    chat_id,
                    final_text_markdown,
                    reply_to_message_id=target_message.message_id,
                    parse_mode=ParseMode.MARKDOWN,
                    original_text_if_markdown_fails=final_text_raw)
            elif "can't parse entities" in str(edit_err).lower():
                logger.warning(
                    f"Gagal mengedit pesan indikator (Markdown error): {edit_err}. Mengirim pesan baru dengan plain text."
                )
                await send_long_message(
                    context,
                    chat_id,
                    final_text_raw,
                    reply_to_message_id=target_message.message_id,
                    parse_mode=None)  # Fallback ke plain text (raw)
            else:
                logger.warning(
                    f"Gagal mengedit pesan indikator thinking (msg_id: {thinking_indicator_msg.message_id}): {edit_err}. Mengirim pesan baru."
                )
                await send_long_message(
                    context,
                    chat_id,
                    final_text_markdown,
                    reply_to_message_id=target_message.message_id,
                    parse_mode=ParseMode.MARKDOWN,
                    original_text_if_markdown_fails=final_text_raw)
        except Exception as edit_err_other:  # Tangkap error lain juga
            logger.error(
                f"Error lain saat mengedit pesan indikator: {edit_err_other}",
                exc_info=True)
            await send_long_message(
                context,
                chat_id,
                final_text_markdown,
                reply_to_message_id=target_message.message_id,
                parse_mode=ParseMode.MARKDOWN,
                original_text_if_markdown_fails=final_text_raw)

    else:  # Indikator thinking gagal dikirim
        logger.warning(
            "Indikator thinking gagal dikirim, mengirim respons /td sebagai pesan baru."
        )
        await send_long_message(context,
                                chat_id,
                                final_text_markdown,
                                reply_to_message_id=target_message.message_id,
                                parse_mode=ParseMode.MARKDOWN,
                                original_text_if_markdown_fails=final_text_raw)


async def send_long_message(
    context: CallbackContext,
    chat_id: int,
    text_to_send:
    str,  # Ini adalah teks yang sudah di-ensure_valid_markdown jika parse_mode=MARKDOWN
    reply_to_message_id: int | None = None,
    parse_mode: str | None = ParseMode.MARKDOWN,
    original_text_if_markdown_fails: str
    | None = None  # Teks asli sebelum validasi Markdown
):
    if not text_to_send:  # Bisa jadi string kosong setelah ensure_valid_markdown
        if original_text_if_markdown_fails and original_text_if_markdown_fails.strip(
        ):  # Jika teks asli ada
            logger.warning(
                f"send_long_message: text_to_send kosong setelah validasi Markdown, mencoba mengirim original_text_if_markdown_fails sebagai plain text untuk chat_id {chat_id}."
            )
            text_to_send = original_text_if_markdown_fails
            parse_mode = None  # Kirim sebagai plain text
        else:  # Jika teks asli juga kosong atau tidak ada
            logger.warning(
                f"send_long_message dipanggil dengan teks kosong untuk chat_id {chat_id}."
            )
            return
    chunks = []
    current_chunk = ""
    # Gunakan TELEGRAM_MAX_MESSAGE_LENGTH yang sudah didefinisikan di atas
    limit = TELEGRAM_MAX_MESSAGE_LENGTH - 20  # Beri sedikit ruang ekstra

    lines = text_to_send.split('\n')
    for i, line in enumerate(lines):
        if len(line) > limit:
            logger.warning(
                f"Satu baris terlalu panjang ({len(line)} chars) di chat {chat_id}. Akan dipecah paksa."
            )
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            for k in range(0, len(line), limit):
                chunks.append(line[k:k + limit])
        elif len(current_chunk) + len(line) + 1 <= limit:  # +1 untuk newline
            current_chunk += line + ('\n' if i < len(lines) - 1 else '')
        else:  # current_chunk penuh
            chunks.append(current_chunk.strip())
            current_chunk = line + ('\n' if i < len(lines) - 1 else '')

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    if not chunks:
        logger.error(
            f"Pemecahan pesan menghasilkan chunk kosong untuk chat_id {chat_id} dari teks: {text_to_send[:100]}"
        )
        return

    if len(chunks) > 1:
        logger.info(
            f"Memecah pesan menjadi {len(chunks)} bagian untuk chat_id {chat_id}."
        )

    for i, chunk_text in enumerate(chunks):
        if not chunk_text: continue
        text_for_current_chunk = chunk_text
        current_parse_mode = parse_mode

        if current_parse_mode == ParseMode.MARKDOWN:
            text_for_current_chunk = ensure_valid_markdown(chunk_text)
            # Jika hasil validasi jadi kosong, dan chunk_text asli ada isinya, mungkin fallback ke plain?
            if not text_for_current_chunk.strip() and chunk_text.strip():
                logger.warning(
                    f"Chunk {i+1} menjadi kosong setelah validasi Markdown ulang. Mencoba kirim chunk asli sebagai plain text."
                )
                text_for_current_chunk = chunk_text  # Gunakan chunk sebelum validasi ulang
                current_parse_mode = None

        current_reply_id = reply_to_message_id if i == 0 else None
        max_retries_markdown_fail = 1  # Hanya coba plain text sekali jika Markdown gagal

        for attempt in range(max_retries_markdown_fail + 1):
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text_for_current_chunk,
                    reply_to_message_id=current_reply_id,
                    parse_mode=current_parse_mode)
                logger.debug(
                    f"Mengirim chunk {i+1}/{len(chunks)} ke chat {chat_id} (mode: {current_parse_mode})"
                )
                break
            except RetryAfter as e_retry_after:
                logger.warning(
                    f"Terkena Rate Limit saat mengirim chunk {i+1}/{len(chunks)} ke chat {chat_id}. Menunggu {e_retry_after.retry_after} detik..."
                )
                await asyncio.sleep(e_retry_after.retry_after)

                if attempt == max_retries_markdown_fail:
                    logger.error(
                        f"Gagal mengirim chunk {i+1}/{len(chunks)} ke chat {chat_id} setelah retry rate limit: {e_retry_after}"
                    )

            except BadRequest as e_bad_request:
                if "can't parse entities" in str(e_bad_request).lower(
                ) and current_parse_mode == ParseMode.MARKDOWN and attempt < max_retries_markdown_fail:
                    logger.warning(
                        f"Gagal mengirim chunk {i+1} (Markdown) ke chat {chat_id}: {e_bad_request}. Mencoba lagi sebagai plain text."
                    )

                    text_for_current_chunk = chunk_text
                    current_parse_mode = None

                else:
                    logger.error(
                        f"Error BadRequest lain saat mengirim chunk {i+1}/{len(chunks)} ke chat {chat_id}: {e_bad_request}",
                        exc_info=True)
                    if i == 0:
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=
                                f"Maaf, terjadi kesalahan saat mengirim balasan (BadRequest)."
                            )
                        except:
                            pass
                    break
            except TelegramError as e_telegram_error:
                logger.error(
                    f"Error Telegram lain saat mengirim chunk {i+1}/{len(chunks)} ke chat {chat_id}: {e_telegram_error}",
                    exc_info=True)
                if i == 0:
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=
                            f"Maaf, terjadi kesalahan Telegram saat mengirim balasan."
                        )
                    except:
                        pass
                break
            except Exception as e_general:
                logger.error(
                    f"Error tak terduga saat mengirim chunk {i+1}/{len(chunks)} ke chat {chat_id}: {e_general}",
                    exc_info=True)
                if i == 0 and reply_to_message_id is None:  # Hindari double reply error jika ini adalah pesan error
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=
                            f"Maaf, terjadi kesalahan tak terduga saat mengirim balasan."
                        )
                    except:
                        pass
                break

        if len(chunks) > 1 and i < len(chunks) - 1:
            await asyncio.sleep(0.7)
