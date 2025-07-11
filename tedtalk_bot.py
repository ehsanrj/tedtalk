import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import tempfile
import shutil

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)



# Bot token - replace with your actual bot token
#BOT_TOKEN = "7576952610:AAERhmFipUAWDSd4qmV8g_r7hvoxyIc6hDo"

# Bot token - get from environment variable for security


BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN environment variable not set!")
    print("Please set your bot token as an environment variable")
    exit(1)



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

The bot will download the video in the best available quality.
        """
        await update.message.reply_text(help_text)

    def is_ted_url(self, url: str) -> bool:
        """Check if the URL is a valid TED Talk URL."""
        ted_domains = ['ted.com', 'www.ted.com']
        return any(domain in url.lower() for domain in ted_domains) and '/talks/' in url.lower()

    async def download_ted_talk(self, url: str) -> dict:
        """Download TED Talk video using yt-dlp."""
        try:
            # Create a unique filename
            output_path = os.path.join(self.temp_dir, '%(title)s.%(ext)s')
            
            ydl_opts = {
                'format': 'best[height<=720]',  # Limit quality to avoid large files
                'outtmpl': output_path,
                'noplaylist': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'TED Talk')
                duration = info.get('duration', 0)
                
                # Check file size estimation (rough)
                if duration > 1800:  # 30 minutes
                    return {
                        'success': False,
                        'error': 'Video too long (>30 minutes). Please try a shorter video.'
                    }
                
                # Download the video
                ydl.download([url])
                
                # Find the downloaded file
                downloaded_file = None
                for file in os.listdir(self.temp_dir):
                    if file.endswith(('.mp4', '.webm', '.mkv')):
                        downloaded_file = os.path.join(self.temp_dir, file)
                        break
                
                if downloaded_file and os.path.exists(downloaded_file):
                    # Check file size (Telegram limit is 50MB)
                    file_size = os.path.getsize(downloaded_file)
                    if file_size > 50 * 1024 * 1024:  # 50MB
                        return {
                            'success': False,
                            'error': 'File too large (>50MB). Telegram limit exceeded.'
                        }
                    
                    return {
                        'success': True,
                        'file_path': downloaded_file,
                        'title': title,
                        'file_size': file_size
                    }
                else:
                    return {
                        'success': False,
                        'error': 'Failed to locate downloaded file.'
                    }
                    
        except Exception as e:
            return {
                'success': False,
                'error': f'Download failed: {str(e)}'
            }

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages with URLs."""
        message_text = update.message.text.strip()
        
        # Check if message contains a URL
        if not message_text.startswith('http'):
            await update.message.reply_text(
                "Please send a valid TED Talk URL.\n"
                "Example: https://www.ted.com/talks/..."
            )
            return
        
        # Check if it's a TED URL
        if not self.is_ted_url(message_text):
            await update.message.reply_text(
                "Please send a valid TED Talk URL from ted.com\n"
                "Example: https://www.ted.com/talks/..."
            )
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            "🔄 Processing your request...\nThis might take a few moments."
        )
        
        try:
            # Download the video
            result = await self.download_ted_talk(message_text)
            
            if result['success']:
                # Send the video file
                await processing_msg.edit_text("📤 Uploading video...")
                
                with open(result['file_path'], 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=f"🎬 {result['title']}\n\n"
                               f"📊 Size: {result['file_size'] / (1024*1024):.1f} MB",
                        supports_streaming=True
                    )
                
                # Clean up the file
                os.remove(result['file_path'])
                
                # Delete processing message
                await processing_msg.delete()
                
            else:
                await processing_msg.edit_text(f"❌ Error: {result['error']}")
                
        except Exception as e:
            await processing_msg.edit_text(f"❌ An error occurred: {str(e)}")

    def cleanup(self):
        """Clean up temporary files."""
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass

def main():
    """Start the bot."""
    # Create bot instance
    bot = TEDTalkBot()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    # Run the bot
    print("🤖 TED Talk Bot is starting...")
    print("Press Ctrl+C to stop the bot")
    
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    finally:
        bot.cleanup()

if __name__ == '__main__':
    main()