import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import tempfile
import shutil
import traceback
import requests # Used for uploading

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token is loaded from environment variables
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_FILE_LIMIT = 49 * 1024 * 1024  # 49MB to be safe

class TEDTalkBot:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        welcome_message = """
🎬 Welcome to TED Talk Downloader Bot!

Send me a TED Talk URL and I'll download it for you.

For videos under 50MB, I'll send the file directly. For larger videos, I'll provide a temporary download link.
        """
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        help_text = """
🆘 Help Information:

1. Copy a TED Talk URL from ted.com
2. Paste it here in the chat.
3. Wait for the download to complete.
4. You'll receive either the video file directly (if <50MB) or a download link (if >50MB).

Download links are active for at least 30 days.
        """
        await update.message.reply_text(help_text)

    def is_ted_url(self, url: str) -> bool:
        """Check if the URL is a valid TED Talk URL."""
        ted_domains = ['ted.com', 'www.ted.com']
        return any(domain in url.lower() for domain in ted_domains) and '/talks/' in url.lower()

    # --- THIS FUNCTION HAS BEEN REPLACED ---
    async def upload_to_0x0st(self, file_path: str) -> dict:
        """Uploads a file to 0x0.st and returns the link."""
        try:
            url = "http://0x0.st"
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = requests.post(url, files=files)
            
            response.raise_for_status()
            
            download_link = response.text.strip()
            if download_link.startswith("http"):
                 return {'success': True, 'link': download_link}
            else:
                logger.error(f"0x0.st upload returned invalid link: {download_link}")
                return {'success': False, 'error': 'File host returned an invalid link.'}

        except requests.exceptions.RequestException as e:
            logger.error(f"0x0.st upload failed (RequestException): {e}")
            return {'success': False, 'error': 'Failed to communicate with the file hosting service.'}
        except Exception as e:
            logger.error(f"Exception during upload: {traceback.format_exc()}")
            return {'success': False, 'error': 'An exception occurred during file upload.'}
    # --- END OF REPLACEMENT ---

    async def download_ted_talk(self, url: str) -> dict:
        """Download TED Talk video using yt-dlp."""
        try:
            output_path = os.path.join(self.temp_dir, '%(title)s.%(ext)s')
            
            ydl_opts = {
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'merge_output_format': 'mp4',
                'outtmpl': output_path,
                'noplaylist': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'TED Talk')
                
                logger.info(f"Starting download for: {title}")
                ydl.download([url])
                logger.info(f"Finished download for: {title}")

                downloaded_file = None
                for file in os.listdir(self.temp_dir):
                    if file.endswith('.mp4'):
                        downloaded_file = os.path.join(self.temp_dir, file)
                        break
                
                if downloaded_file and os.path.exists(downloaded_file):
                    file_size = os.path.getsize(downloaded_file)
                    return {'success': True, 'file_path': downloaded_file, 'title': title, 'file_size': file_size}
                else:
                    return {'success': False, 'error': 'Failed to locate the final downloaded video file.'}
                    
        except Exception as e:
            logger.error(f"Download error: {traceback.format_exc()}")
            return {'success': False, 'error': 'An unexpected error occurred during download.'}

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages with URLs."""
        message_text = update.message.text.strip()
        
        if not message_text.startswith('http') or not self.is_ted_url(message_text):
            await update.message.reply_text("Please send a valid TED Talk URL from ted.com")
            return
        
        processing_msg = await update.message.reply_text("🔄 Processing your request...")
        
        try:
            download_result = await self.download_ted_talk(message_text)
            
            if not download_result['success']:
                await processing_msg.edit_text(f"❌ Error: {download_result['error']}")
                return

            file_path = download_result['file_path']
            file_size = download_result['file_size']
            title = download_result['title']

            if file_size < TELEGRAM_FILE_LIMIT:
                await processing_msg.edit_text("✅ Download complete! Uploading video to Telegram...")
                with open(file_path, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=f"🎬 {title}\n📊 Size: {file_size / (1024*1024):.1f} MB",
                        supports_streaming=True
                    )
                await processing_msg.delete()
            else:
                await processing_msg.edit_text("✅ Download complete! File is too large for Telegram, generating a download link...")
                # --- THIS LINE HAS BEEN UPDATED ---
                upload_result = await self.upload_to_0x0st(file_path)
                # --- END OF UPDATE ---
                if upload_result['success']:
                    link = upload_result['link']
                    await processing_msg.edit_text(
                        f"🎬 {title}\n\n"
                        f"🔗 This video is too large for Telegram ({file_size / (1024*1024):.1f} MB).\n\n"
                        f"Here is your temporary download link:\n{link}"
                    )
                else:
                    await processing_msg.edit_text(f"❌ Error: {upload_result['error']}")

            os.remove(file_path)

        except Exception as e:
            logger.error(f"General handling error: {traceback.format_exc()}")
            await processing_msg.edit_text("❌ An unexpected error occurred.")

    def cleanup(self):
        """Clean up temporary files."""
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass

def main():
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("FATAL: TELEGRAM_TOKEN environment variable not set.")
        return

    bot = TEDTalkBot()
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    logger.info("🤖 TED Talk Bot is starting...")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except (Exception, KeyboardInterrupt) as e:
        logger.info(f"🛑 Bot shutting down: {e}")
    finally:
        bot.cleanup()

if __name__ == '__main__':
    main()
