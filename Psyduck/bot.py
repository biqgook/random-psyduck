"""
GloveAndHisBoy Discord Bot - Random Number Generator with Verification
Main bot file
"""

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
from reddit_manager import RedditManager
from queue_manager import CommandQueue
from roll_logger import RollLogger
from utils import (
    create_winner_embed,
    validate_parameters,
    VerificationButton
)

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('GloveAndHisBoy')
logger.setLevel(logging.WARNING)  # Set our logger to WARNING too

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

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

# Initialize command queue with 5-second delay
command_queue = CommandQueue(delay_seconds=config.COMMAND_QUEUE_DELAY)

# Initialize roll logger
roll_logger = RollLogger()

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
    
    # Sync commands to the guild (this clears and re-registers, preventing duplicates)
    try:
        guild = discord.Object(id=int(os.getenv('TESTING_GUILD_ID')))
        # Clear existing commands first
        bot.tree.clear_commands(guild=guild)
        # Copy commands to guild
        bot.tree.copy_global_to(guild=guild)
        # Sync to guild (updates instantly for guild-specific commands)
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} command(s) to guild {os.getenv('TESTING_GUILD_ID')}")
    except Exception as e:
        logger.exception(f"Error syncing commands: {e}")
    
    # Auto-cleanup user spam messages on startup
    try:
        channel = bot.get_channel(config.ALLOWED_CHANNEL_ID)
        if channel:
            logger.info("Starting startup cleanup of user messages...")
            await startup_cleanup(channel)
        else:
            logger.warning(f"Could not find channel {config.ALLOWED_CHANNEL_ID} for startup cleanup")
    except Exception as e:
        logger.exception(f"Error during startup cleanup: {e}")
    
    # Initialize roll logger from existing data
    try:
        roll_log_channel = bot.get_channel(config.ROLL_LOG_CHANNEL_ID)
        if roll_log_channel:
            logger.info("Initializing roll logger from existing data...")
            await roll_logger.initialize_from_channel(roll_log_channel)
        else:
            logger.warning(f"Could not find roll log channel {config.ROLL_LOG_CHANNEL_ID}")
    except Exception as e:
        logger.exception(f"Error initializing roll logger: {e}")
        logger.exception(f"Error during startup cleanup: {e}")


@bot.event
async def on_message(message):
    """Monitor messages and delete non-slash commands in the allowed channel"""
    # Ignore bot's own messages
    if message.author.bot:
        return
    
    # Check if message is in the allowed channel
    if message.channel.id == config.ALLOWED_CHANNEL_ID:
        logger.info(f"Message detected in monitored channel from {message.author} (ID: {message.author.id}): '{message.content[:50]}'")
        
        # Check for admin cleanup commands
        if message.author.id == config.ADMIN_USER_ID:
            logger.info("User is admin - checking for commands")
            msg_content = message.content.strip()
            
            # Admin cleanup commands
            if msg_content == "-c":
                logger.info("Admin '-c' (clean) command detected")
                await cleanup_user_messages(message.channel, message)
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


async def startup_cleanup(channel: discord.TextChannel):
    """Clean up user messages on bot startup"""
    try:
        deleted_count = 0
        async for msg in channel.history(limit=100):  # Check last 100 messages
            # Delete messages that are not from bot or admin
            if msg.author.id != bot.user.id and msg.author.id != config.ADMIN_USER_ID:
                try:
                    await msg.delete()
                    deleted_count += 1
                    # Rate limit protection
                    await asyncio.sleep(0.5)
                except discord.errors.NotFound:
                    pass
                except discord.errors.Forbidden:
                    logger.error(f"Missing permissions to delete message {msg.id}")
                except Exception as e:
                    logger.exception(f"Error deleting message {msg.id}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Startup cleanup complete - removed {deleted_count} user messages")
        else:
            logger.info("Startup cleanup complete - no user messages found")
            
    except Exception as e:
        logger.exception(f"Error during startup cleanup: {e}")


async def cleanup_user_messages(channel: discord.TextChannel, trigger_message: discord.Message):
    """Delete all messages except bot and admin messages"""
    try:
        await trigger_message.delete()  # Delete the "Clean up" command
        logger.info(f"Starting cleanup - removing user messages only")
        
        deleted_count = 0
        async for msg in channel.history(limit=500):  # Limit to last 500 messages
            # Keep bot messages and admin messages
            if msg.author.id != bot.user.id and msg.author.id != config.ADMIN_USER_ID:
                try:
                    await msg.delete()
                    deleted_count += 1
                    # Rate limit protection: wait between deletions
                    await asyncio.sleep(0.5)  # 2 deletions per second
                except discord.errors.NotFound:
                    pass  # Message already deleted
                except discord.errors.Forbidden:
                    logger.error(f"Missing permissions to delete message {msg.id}")
                except Exception as e:
                    logger.exception(f"Error deleting message {msg.id}: {e}")
        
        logger.info(f"Cleanup complete - deleted {deleted_count} user messages")
        
        # Send confirmation (will auto-delete after 5 seconds)
        confirm_msg = await channel.send(f"✅ Cleaned up {deleted_count} user messages")
        await asyncio.sleep(5)
        await confirm_msg.delete()
        
    except Exception as e:
        logger.exception(f"Error during cleanup: {e}")


async def cleanup_everything(channel: discord.TextChannel, trigger_message: discord.Message):
    """Delete all messages including bot messages and admin messages"""
    try:
        logger.info(f"Starting full cleanup - removing ALL messages (including bot and admin)")
        
        # Don't delete the trigger message first - let it be deleted in the loop
        deleted_count = 0
        failed_count = 0
        
        async for msg in channel.history(limit=500):  # Limit to last 500 messages
            try:
                logger.debug(f"Deleting message {msg.id} from {msg.author.name}")
                await msg.delete()
                deleted_count += 1
                # Rate limit protection: wait between deletions
                await asyncio.sleep(0.5)  # 2 deletions per second
            except discord.errors.NotFound:
                logger.debug(f"Message {msg.id} already deleted")
                pass  # Message already deleted
            except discord.errors.Forbidden:
                logger.error(f"Missing permissions to delete message {msg.id}")
                failed_count += 1
            except Exception as e:
                logger.exception(f"Error deleting message {msg.id}: {e}")
                failed_count += 1
        
        logger.info(f"Full cleanup complete - deleted {deleted_count} messages, {failed_count} failed")
        
    except Exception as e:
        logger.exception(f"Error during full cleanup: {e}")


@bot.tree.command(name="call", description="Generate random winner(s) for a raffle")
@app_commands.describe(
    reddit_url="Reddit post URL for the raffle",
    spots="Total number of spots in the raffle",
    winners="Number of winners to select (default: 1)"
)
async def call_command(
    interaction: discord.Interaction,
    reddit_url: str,
    spots: int,
    winners: int = 1
):
    """Slash command to generate random winners"""
    
    # Check if command is used in the correct channel
    if interaction.channel_id != config.ALLOWED_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{config.ALLOWED_CHANNEL_ID}>",
            ephemeral=True
        )
        return
    
    # Validate parameters
    is_valid, error_message = validate_parameters(winners, spots)
    if not is_valid:
        await interaction.response.send_message(f"❌ {error_message}", ephemeral=True)
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
    
    # Add to queue with channel reference and caller user object
    await command_queue.add_to_queue(process_call_command, interaction.channel, reddit_url, spots, winners, interaction.user)


async def process_call_command(
    channel: discord.TextChannel,
    reddit_url: str,
    spots: int,
    winners: int,
    caller_user: discord.User
):
    """Process the actual command execution"""
    caller_name = caller_user.display_name
    
    # Fetch Reddit post information
    reddit_info = None
    if reddit_manager:
        try:
            reddit_info = await reddit_manager.get_post_info(reddit_url)
            if not reddit_info:
                await channel.send("⚠️ Could not fetch Reddit post information, but continuing with number generation...")
        except Exception as e:
            logger.exception(f"Error fetching Reddit info: {e}")
            await channel.send("⚠️ Error fetching Reddit post, but continuing with number generation...")
    
    try:
        # Generate random numbers (will retry every 5 minutes if API is down)
        result = await random_org.generate_random_numbers(winners, spots)
        
        # Extract data from result
        random_data = result['random']
        signature = result['signature']
        numbers = random_data['data']
        numbers.sort()
        
        # Get request count
        request_count, request_limit = random_org.get_total_requests()
        
        # Format verification data
        verification_json = random_org.format_verification_data(random_data)
        
        # Get timestamp from Random.org response
        timestamp = random_data.get('completionTime', 'N/A')
        
        # Add winners section if spot assignments are available
        if reddit_info and reddit_info.get('spot_assignments'):
            spot_assignments = reddit_info['spot_assignments']
            winner_arr = []
            for number in numbers:
                username = spot_assignments.get(number, "Unknown")
                # Create hyperlink to user's Reddit profile
                if username != "Unknown":
                    winner_arr.append(f"{number} - [{username}](https://reddit.com/u/{username})")
                else:
                    winner_arr.append(f"{number} - {username}")
        
            winning_content = "# **Winners:** " + " | ".join(winner_arr)
        else:
            winning_content = "# **Winning numbers:** " + " | ".join(numbers)

        need_detailed_winners = len(winning_content) >= 256
        if need_detailed_winners:
            winning_content = "List of winners is too long. See desc. for details."

        # Create the embed
        embed = create_winner_embed(
            numbers,
            request_count,
            request_limit,
            reddit_info,
            timestamp,
            spots,
            caller_name,
            need_detailed_winners
        )
        
        # Create button view with verification data (uses database for persistence)
        view = VerificationButton(verification_db)
        
        # Send the response with button (winning numbers as content, info as embed)
        response_message = await channel.send(content=winning_content, embed=embed, view=view)
        
        # Log numbers to roll history
        try:
            roll_log_channel = bot.get_channel(config.ROLL_LOG_CHANNEL_ID)
            if roll_log_channel:
                await roll_logger.log_roll(roll_log_channel, numbers)
            else:
                logger.warning(f"Roll log channel {config.ROLL_LOG_CHANNEL_ID} not found")
        except Exception as e:
            logger.exception(f"Error logging roll to history: {e}")
        
        # Store verification data in database using the response message ID
        verification_db.store_verification(
            response_message.id,
            verification_json,
            signature,
            numbers,
            reddit_info,
            timestamp,
            spots,
            caller_name
        )
        
        logger.info(f"Successfully sent {len(numbers)} number(s) to channel {channel.id}")
        
        # Send DM to caller with results and message link
        try:
            dm_embed = discord.Embed(
                title="Record",
                description=f"[Discord Link]({response_message.jump_url})",
                color=config.EMBED_COLOR
            )
            
            # Add the same information as the main embed
            if reddit_info:
                dm_embed.add_field(
                    name="Raffle",
                    value=f"[{reddit_info['author']}]({reddit_info['author_url']}) | [Link]({reddit_info['url']})",
                    inline=False
                )
            
            dm_embed.add_field(name="Spots", value=f"1-{spots}", inline=True)
            
            if len(numbers) == 1:
                dm_embed.add_field(name="Winning Number", value=str(numbers[0]), inline=True)
            else:
                dm_embed.add_field(name="Winning Numbers", value=", ".join(map(str, numbers)), inline=True)
            
            # Add winners if available
            if reddit_info and reddit_info.get('spot_assignments'):
                spot_assignments = reddit_info['spot_assignments']
                winners_list = []
                for number in numbers:
                    username = spot_assignments.get(number, "Unknown")
                    if username != "Unknown":
                        winners_list.append(f"{number} - [{username}](https://reddit.com/u/{username})")
                    else:
                        winners_list.append(f"{number} - {username}")
                
                if winners_list:
                    dm_embed.add_field(name="Winners", value="\n".join(winners_list), inline=False)
            
            # Set image if available
            if reddit_info and reddit_info.get('image_url'):
                dm_embed.set_image(url=reddit_info['image_url'])
            
            # Set footer with timestamp
            if timestamp:
                from datetime import datetime
                import pytz
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    est = pytz.timezone('US/Eastern')
                    dt_est = dt.astimezone(est)
                    formatted_time = dt_est.strftime('%Y-%m-%d %I:%M %p')
                    dm_embed.set_footer(text=formatted_time)
                except:
                    pass
            
            await caller_user.send(embed=dm_embed)
            logger.info(f"Sent results DM to {caller_user.name}")
            
        except discord.Forbidden:
            logger.warning(f"Could not send DM to {caller_user.name} - DMs disabled")
        except Exception as e:
            logger.exception(f"Error sending DM to caller: {e}")
        
    except Exception as e:
        # Send error message
        await channel.send("❌ An unexpected error occurred. Please try again later.")
        logger.exception(f"Error processing command: {e}")


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
