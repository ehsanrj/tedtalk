import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import tempfile
import shutil
import traceback # Import traceback for detailed error logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token is loaded from environment variables
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

class TEDTalkBot:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        welcome_message = """
🎬 Welcome to TED Talk Downloader Bot!

Send me a TED Talk URL and I'll download it for you.

Commands:
/start - Show this welcome message
/help - Show help information

Just paste any TED Talk URL and I'll handle the rest!
        """
        await update.message.reply_text(welcome_message)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        help_text = """
🆘 Help Information:

1. Copy a TED Talk URL from ted.com
2. Paste it here in the chat
3. Wait for the download to complete
4. Receive your video file!

Supported formats:
- https://www.ted.com/talks/...
- https://ted.com/talks/...

The bot will download the video in the best available quality up to 720p.
        """
        await update.message.reply_text(help_text)

    def is_ted_url(self, url: str) -> bool:
        """Check if the URL is a valid TED Talk URL."""
        ted_domains = ['ted.com', 'www.ted.com']
        return any(domain in url.lower() for domain in ted_domains) and '/talks/' in url.lower()

    async def download_ted_talk(self, url: str) -> dict:
        """Download TED Talk video using yt-dlp."""
        try:
            output_path = os.path.join(self.temp_dir, '%(title)s.%(ext)s')
            
            ydl_opts = {
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'merge_output_format': 'mp4',
                'outtmpl': output_path,
                'noplaylist': True,
                'extract_flat': False,
                # Add a logger to capture yt-dlp's own messages
                'logger': logger,
                'progress_hooks': [lambda d: logger.info(d['status']) if d['status'] in ['downloading', 'finished'] else None],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'TED Talk')
                duration = info.get('duration', 0)
                
                if duration > 1800:
                    return {'success': False, 'error': 'Video too long (>30 minutes). Please try a shorter video.'}
                
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
                    if file_size > 50 * 1024 * 1024:
                        os.remove(downloaded_file)
                        return {'success': False, 'error': 'File too large (>50MB). Telegram limit exceeded.'}
                    
                    return {'success': True, 'file_path': downloaded_file, 'title': title, 'file_size': file_size}
                else:
                    logger.warning("Could not find the final .mp4 file after download.")
                    return {'success': False, 'error': 'Failed to locate the final downloaded video file.'}
                    
        # --- THIS IS THE NEW DEBUGGING PART ---
        except Exception as e:
            # Log the full, detailed error to the console for debugging
            logger.error("--- DETAILED YT-DLP ERROR ---")
            logger.error(traceback.format_exc())
            logger.error("-----------------------------")
            
            # Return a user-friendly error
            if "Requested format is not available" in str(e) or "No video formats found" in str(e):
                 return {'success': False, 'error': 'Could not find a suitable download format for this video.'}
            return {'success': False, 'error': 'An unexpected error occurred during download.'}
        # --- END OF DEBUGGING PART ---


    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages with URLs."""
        message_text = update.message.text.strip()
        
        if not message_text.startswith('http') or not self.is_ted_url(message_text):
            await update.message.reply_text(
                "Please send a valid TED Talk URL from ted.com\n"
                "Example: https://www.ted.com/talks/..."
            )
            return
        
        processing_msg = await update.message.reply_text(
            "🔄 Processing your request...\nThis might take a few moments."
        )
        
        try:
            result = await self.download_ted_talk(message_text)
            
            if result['success']:
                await processing_msg.edit_text("📤 Uploading video...")
                
                with open(result['file_path'], 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=f"🎬 {result['title']}\n\n"
                               f"📊 Size: {result['file_size'] / (1024*1024):.1f} MB",
                        supports_streaming=True
                    )
                
                os.remove(result['file_path'])
                await processing_msg.delete()
                
            else:
                await processing_msg.edit_text(f"❌ Error: {result['error']}")
                
        except Exception as e:
            logger.error(f"General handling error: {traceback.format_exc()}")
            await processing_msg.edit_text(f"❌ An unexpected error occurred.")

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
