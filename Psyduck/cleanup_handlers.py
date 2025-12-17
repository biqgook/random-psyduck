"""
Channel cleanup handlers for removing messages
"""

import discord
import asyncio
import logging
import config

logger = logging.getLogger('Psyduck')


async def startup_cleanup(channel: discord.TextChannel, bot_user_id: int):
    """
    Clean up user messages on bot startup
    
    Args:
        channel: Discord channel to clean
        bot_user_id: Bot's user ID to preserve bot messages
    """
    try:
        deleted_count = 0
        async for msg in channel.history(limit=100):  # Check last 100 messages
            # Delete messages that are not from bot or admin
            if msg.author.id != bot_user_id and msg.author.id != config.ADMIN_USER_ID:
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


async def cleanup_user_messages(channel: discord.TextChannel, trigger_message: discord.Message, bot_user_id: int):
    """
    Delete all messages except bot and admin messages
    
    Args:
        channel: Discord channel to clean
        trigger_message: The message that triggered the cleanup (will be deleted)
        bot_user_id: Bot's user ID to preserve bot messages
    """
    try:
        await trigger_message.delete()  # Delete the "Clean up" command
        logger.info("Starting cleanup - removing user messages only")
        
        deleted_count = 0
        async for msg in channel.history(limit=500):  # Limit to last 500 messages
            # Keep bot messages and admin messages
            if msg.author.id != bot_user_id and msg.author.id != config.ADMIN_USER_ID:
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
    """
    Delete all messages including bot messages and admin messages
    
    Args:
        channel: Discord channel to clean
        trigger_message: The message that triggered the cleanup (will be deleted too)
    """
    try:
        logger.info("Starting full cleanup - removing ALL messages (including bot and admin)")
        
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
