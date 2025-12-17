import argparse
import discord
from discord import app_commands
from discord.ext import commands
import logging
import os
import asyncio
from dotenv import load_dotenv
import config
from random_org import RandomOrgManager
from database import VerificationDatabase
from link_database import LinkDatabase
from reddit_manager import RedditManager
from queue_manager import CommandQueue
from roll_logger import RollLogger
from link_view import LinkButton
from cleanup_handlers import startup_cleanup, cleanup_user_messages, cleanup_everything
from command_handler import process_call_command
from utils import (
    create_winner_embed,
    validate_parameters,
    VerificationButton,
    match_reddit_to_discord_user,
    format_timestamp_est
)

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Psyduck')
logger.setLevel(logging.WARNING)  # Set our logger to WARNING too

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True  

bot = commands.Bot(command_prefix="-", intents=intents)

# File lock for thread-safe access to called_links.txt
called_links_lock = asyncio.Lock()

# Initialize Random.org manager with API keys
api_keys = [
    os.getenv('RANDOM_ORG_API_KEY_1'),
    os.getenv('RANDOM_ORG_API_KEY_2'),
    os.getenv('RANDOM_ORG_API_KEY_3'),
    os.getenv('RANDOM_ORG_API_KEY_4')
]

# Filter out any None values in case not all keys are set
api_keys = [key for key in api_keys if key]

if not api_keys:
    logger.error("No Random.org API keys found in environment variables!")
    exit(1)

random_org = RandomOrgManager(api_keys)

# Initialize verification database
verification_db = VerificationDatabase()

# Initialize link database (separate from verification db)
link_db = LinkDatabase()

# Initialize command queue with 5-second delay
command_queue = CommandQueue(delay_seconds=config.COMMAND_QUEUE_DELAY)

# Initialize roll logger
roll_logger = RollLogger()

# ---- Parse CLI arguments ----
parser = argparse.ArgumentParser()
parser.add_argument(
    "--env",
    choices=["pokemon", "lego"],
    default="pokemon",
    help="Run environment"
)
args = parser.parse_args()

guild_id_str = os.getenv('TESTING_GUILD_ID')
allow_id = config.ALLOWED_CHANNEL_ID
roll_id = config.ROLL_LOG_CHANNEL_ID
general_chat_id = config.PR_GENERAL_CHAT
if args.env != "pokemon":
    guild_id_str = os.getenv('LR_GUILD_ID')
    allow_id = config.LR_ALLOWED_CHANNEL_ID
    roll_id = config.LR_ROLL_LOG_CHANNEL_ID

# Initialize Reddit manager
try:
    reddit_manager = RedditManager(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        user_agent=os.getenv('REDDIT_USER_AGENT'),
        username=os.getenv('REDDIT_USERNAME'),
        password=os.getenv('REDDIT_PASSWORD')
    )
except Exception as e:
    logger.error(f"Failed to initialize Reddit manager: {e}")
    reddit_manager = None


@bot.event
async def on_ready():
    """Called when the bot is ready"""
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot ID: {bot.user.id}')
    logger.info(f'Loaded {len(api_keys)} API key(s)')
    logger.info(f'Listening in channel: {config.ALLOWED_CHANNEL_ID}')
    
    # Register persistent views for buttons
    bot.add_view(VerificationButton(verification_db))
    bot.add_view(LinkButton(link_db))
    logger.info("Registered persistent button views")

    # Sync commands to the guild (this clears and re-registers, preventing duplicates)
    try:
        guild = discord.Object(id=int(guild_id_str))
        # Clear existing commands first
        bot.tree.clear_commands(guild=guild)
        # Copy commands to guild
        bot.tree.copy_global_to(guild=guild)
        # Sync to guild (updates instantly for guild-specific commands)
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} command(s) to guild {guild_id_str}")
    except Exception as e:
        logger.exception(f"Error syncing commands: {e}")
    
    # Auto-cleanup user spam messages on startup
    try:
        channel = bot.get_channel(allow_id)
        if channel:
            logger.info("Starting startup cleanup of user messages...")
            await startup_cleanup(channel, bot.user.id)
        else:
            logger.warning(f"Could not find channel {allow_id} for startup cleanup")
    except Exception as e:
        logger.exception(f"Error during startup cleanup: {e}")
    
    # Initialize roll logger from existing data
    try:
        roll_log_channel = bot.get_channel(roll_id)
        if roll_log_channel:
            logger.info("Initializing roll logger from existing data...")
            await roll_logger.initialize_from_channel(roll_log_channel)
        else:
            logger.warning(f"Could not find roll log channel {roll_id}")
    except Exception as e:
        logger.exception(f"Error initializing roll logger: {e}")


@bot.event
async def on_message(message):
    """Monitor messages and delete non-slash commands in the allowed channel"""
    # Ignore bot's own messages
    if message.author.bot:
        return

    # Check if message is in the allowed channel
    if message.channel.id == allow_id:
        logger.info(f"Message detected in monitored channel from {message.author} (ID: {message.author.id}): '{message.content[:50]}'")
        
        # Check for admin cleanup commands
        if message.author.id == config.ADMIN_USER_ID:
            logger.info("User is admin - checking for commands")
            msg_content = message.content.strip()
            
            # Admin cleanup commands
            if msg_content == "-c":
                logger.info("Admin '-c' (clean) command detected")
                await cleanup_user_messages(message.channel, message, bot.user.id)
                return
            elif msg_content == "-e":
                logger.info("Admin '-e' (everything) command detected")
                await cleanup_everything(message.channel, message)
                return
            elif msg_content == "-cdb":
                logger.info("Admin '-cdb' (cleanup database) command detected")
                try:
                    deleted = verification_db.cleanup_all_records()
                    await message.reply(f"✅ Database cleaned up successfully! Deleted {deleted} verification records.")
                    logger.info(f"Admin {message.author} cleaned up database: {deleted} records deleted")
                except Exception as e:
                    await message.reply(f"❌ Error cleaning up database: {str(e)}")
                    logger.exception(f"Error during manual cleanup: {e}")
                return
        
        # Delete any message that's not a slash command (slash commands don't trigger on_message)
        try:
            logger.info(f"Attempting to delete message from {message.author.name}")
            await message.delete()
            logger.info(f"Successfully deleted message from {message.author} in monitored channel")
        except discord.errors.Forbidden:
            logger.error(f"PERMISSION DENIED: Cannot delete messages in channel {message.channel.id}. Bot needs 'Manage Messages' permission!")
        except Exception as e:
            logger.exception(f"Error deleting message: {e}")
    
    # Process commands (for prefix commands if any)
    await bot.process_commands(message)


@bot.tree.command(name="call", description="Generate random winner(s) for a raffle")
@app_commands.describe(
    reddit_url="Reddit post URL for the raffle",
    spots="Total number of spots (optional - will parse from Reddit title if not provided)",
    winners="Number of winners to select (default: 1)"
)
async def call_command(
    interaction: discord.Interaction,
    reddit_url: str,
    spots: int = None,
    winners: int = 1
):
    """Slash command to generate random winners"""

    # Check if command is used in the correct channel
    if interaction.channel_id != allow_id:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{allow_id}>",
            ephemeral=True
        )
        return
    
    # If spots not provided, we'll parse it from Reddit title later
    # For now, just validate winners if spots is provided
    if spots is not None:
        is_valid, error_message = validate_parameters(winners, spots)
        if not is_valid:
            # Silent error - notify admin only
            from command_handler import send_error_to_admin
            await send_error_to_admin(bot, interaction.user, f"Invalid command parameters: {error_message} (spots={spots}, winners={winners})")
            await interaction.response.send_message("🎲 Processing...", ephemeral=True)
            return
    
    # Check queue position
    queue_position = command_queue.get_queue_position()
    
    if queue_position > 0:
        # Send initial response with queue position (ephemeral so it doesn't clutter)
        await interaction.response.send_message(
            f"⏳ Your request is queued. Position: **{queue_position + 1}**\n"
            f"*Please wait, processing will begin shortly...*",
            ephemeral=True
        )
    else:
        # Respond immediately with ephemeral message so interaction doesn't fail
        await interaction.response.send_message("🎲 Processing...", ephemeral=True)
    
    # Add to queue with all necessary parameters
    await command_queue.add_to_queue(
        process_call_command,
        interaction.channel,
        reddit_url,
        spots,
        winners,
        interaction.user,
        bot,
        random_org,
        reddit_manager,
        verification_db,
        link_db,
        roll_logger,
        roll_id,
        general_chat_id,
        interaction
    )


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors (suppress CommandNotFound for prefix commands)"""
    if isinstance(error, commands.CommandNotFound):
        # Silently ignore - we only use slash commands
        return
    
    # Log other command errors
    logger.exception(f"Command error: {error}")


@bot.event
async def on_error(event, *args, **kwargs):
    """Handle errors"""
    logger.exception(f"Error in {event}")


def load_links(path):
    """Load called links from file with proper error handling"""
    try:
        with open(path, encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        logger.warning(f"Links file {path} not found, creating new one")
        # Create empty file
        with open(path, "w", encoding="utf-8") as f:
            pass
        return set()
    except Exception as e:
        logger.exception(f"Error loading links from {path}: {e}")
        return set()


def main():
    """Main entry point"""
    # Get Discord token
    discord_token = os.getenv('DISCORD_BOT_TOKEN')
    
    if not discord_token:
        logger.error("DISCORD_BOT_TOKEN not found in environment variables!")
        return
    
    # Start the bot
    try:
        bot.run(discord_token)
    except Exception as e:
        logger.exception(f"Failed to start bot: {e}")
    finally:
        # Cleanup Reddit client
        if reddit_manager:
            import asyncio
            asyncio.run(reddit_manager.close())


if __name__ == "__main__":
    main()
