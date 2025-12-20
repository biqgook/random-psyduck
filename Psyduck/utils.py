"""
Utility functions for formatting Discord messages and embeds
"""

import discord
import io
import json
import base64
import logging
import re
from typing import Optional
from datetime import datetime
import pytz
import config

logger = logging.getLogger('GloveAndHisBoy')


def parse_spots_from_title(title: str) -> Optional[int]:
    """
    Parse the number of spots from Reddit post title
    
    Examples:
    - "[MAIN] PSA 10 SHINY RAYQUAZA PONCHO PIKACHU #231 - 223 spots at $40/ea" -> 223
    - "[MINI] - Mini #3 (2 Winners) PSA 10 - 120 Spots at $5/ea" -> 120
    - "[NM] Phantasmal Flames Booster box | 306 Spots @ $1ea" -> 306
    
    Args:
        title: Reddit post title
        
    Returns:
        Number of spots parsed from title, or None if not found
    """
    # Pattern to match "XXX Spots" or "XXX spots" (case insensitive)
    pattern = r'(\d+)\s+[Ss]pots'
    match = re.search(pattern, title)
    
    if match:
        spots = int(match.group(1))
        logger.info(f"Parsed {spots} spots from title: {title[:50]}...")
        return spots
    
    logger.warning(f"Could not parse spots from title: {title[:50]}...")
    return None


def create_winner_embed(numbers: list, request_count: int, request_limit: int, 
                       reddit_info: dict = None, timestamp: str = None, total_spots: int = None, 
                       caller_name: str = None, need_detailed_winners: bool = False) -> discord.Embed:
    """
    Create a Discord embed with Reddit post info and timestamp
    
    Args:
        numbers: List of winning number(s)
        request_count: Current API request count
        request_limit: Maximum API requests allowed
        reddit_info: Dictionary with Reddit post information
        timestamp: ISO timestamp of when the call was made
        total_spots: Total number of spots in the raffle
        caller_name: Discord username of who called the command
        
    Returns:
        Discord Embed object
    """
    logger.info(f"Building embed with Reddit info - Author: {reddit_info.get('author') if reddit_info else 'None'}, Has image: {bool(reddit_info.get('image_url') if reddit_info else False)}")
    
    # Build description with all info in vertical order
    description_lines = []
    
    # Handle missing reddit_info gracefully
    if reddit_info and reddit_info.get('title'):
        embed = discord.Embed(
            title=reddit_info['title'],
            color=config.EMBED_COLOR
        )
    else:
        embed = discord.Embed(
            title="Raffle Results",
            color=config.EMBED_COLOR
        )

    # Spots indicator (e.g., "1-100")
    if total_spots:
        description_lines.append(f"**Total Spots:** 1-{total_spots}")
    
    # Winning numbers
    if len(numbers) == 1:
        description_lines.append(f"**Winning Number:** {numbers[0]}")
    else:
        numbers_str = ", ".join(map(str, numbers))
        description_lines.append(f"**Winning Numbers:** {numbers_str}")
    
    if reddit_info:
        description_lines.append("")  # Empty line for spacing

        # Author and Link on same line separated by |
        description_lines.append(f"**Reddit Host:** [{reddit_info['author']}]({reddit_info['author_url']}) | [Raffle Link]({reddit_info['url']})")
    else:
        logger.warning("No Reddit info provided to embed")

    # Add winners section if spot assignments are available
    if reddit_info and reddit_info.get('spot_assignments') and need_detailed_winners:
        spot_assignments = reddit_info['spot_assignments']
        description_lines.append("")  # Empty line for spacing
        description_lines.append("**Winners:**")
        
        for number in numbers:
            username = spot_assignments.get(number, "Unknown")
            # Create hyperlink to user's Reddit profile
            if username != "Unknown":
                description_lines.append(f"{number} - [{username}](https://reddit.com/u/{username})")
            else:
                description_lines.append(f"{number} - {username}")

    embed.description = "\n".join(description_lines)
    
    # Set image if available
    if reddit_info and reddit_info.get('image_url'):
        logger.info(f"Setting embed image: {reddit_info['image_url'][:100]}")
        embed.set_image(url=reddit_info['image_url'])
    else:
        logger.warning("No image URL available for embed")
    
    # Format timestamp to EST and set as footer with caller name
    if timestamp:
        from datetime import datetime
        import pytz
        try:
            # Parse ISO timestamp
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            # Convert to EST
            est = pytz.timezone('US/Eastern')
            dt_est = dt.astimezone(est)
            # Format as requested with caller name (no "Called by" prefix)
            formatted_time = dt_est.strftime('%Y-%m-%d %I:%M %p')
            if caller_name:
                footer_text = f"Discord Bot Caller: {caller_name} | {formatted_time}"
            else:
                footer_text = formatted_time
            embed.set_footer(text=footer_text)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not format timestamp {timestamp}: {e}")
            if caller_name:
                embed.set_footer(text=f"Discord Bot Caller: {caller_name} | {timestamp}")
            else:
                embed.set_footer(text=timestamp)
    elif caller_name:
        embed.set_footer(text=caller_name)
    
    return embed


def format_winning_message(numbers: list) -> str:
    """
    Format the winning number(s) as large header
    
    Args:
        numbers: List of winning number(s)
        
    Returns:
        Formatted message string with # for large text
    """
    if len(numbers) == 1:
        return f"# {numbers[0]}"
    else:
        numbers_str = ", ".join(map(str, numbers))
        return f"# {numbers_str}"


def parse_command(message_content: str, bot_user_id: int) -> tuple:
    """
    Parse the bot mention command to extract parameters
    
    Args:
        message_content: The message content
        bot_user_id: The bot's user ID
        
    Returns:
        Tuple of (count, max_value) or (None, None) if invalid
    """
    # Remove the bot mention
    mention = f"<@{bot_user_id}>"
    if mention not in message_content:
        # Try with ! for nickname mentions
        mention = f"<@!{bot_user_id}>"
        if mention not in message_content:
            return (None, None)
    
    # Get the text after the mention
    parts = message_content.replace(mention, "").strip().split()
    
    # Filter to only numeric parts
    numbers = []
    for part in parts:
        if part.isdigit():
            numbers.append(int(part))
    
    if len(numbers) == 1:
        # Single number: pick 1 winner from 1-N
        return (1, numbers[0])
    elif len(numbers) == 2:
        # Two numbers: pick N winners from 1-M
        count, max_value = numbers[0], numbers[1]
        
        # Validation: count can't exceed max_value
        if count > max_value:
            return (None, None)
        
        return (count, max_value)
    else:
        return (None, None)


def validate_parameters(count: int, max_value: int) -> tuple:
    """
    Validate the command parameters
    
    Args:
        count: Number of winners to pick
        max_value: Maximum value in range
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if count is None or max_value is None:
        return (False, "Invalid command format. Use `@GloveAndHisBoy <number>` or `@GloveAndHisBoy <count> <max>`")
    
    if count < 1:
        return (False, "Count must be at least 1")
    
    if max_value < 1:
        return (False, "Maximum value must be at least 1")
    
    if count > max_value:
        return (False, f"Cannot pick {count} unique numbers from a range of 1-{max_value}")
    
    if max_value > 1000000:
        return (False, "Maximum value cannot exceed 1,000,000")
    
    if count > 1000:
        return (False, "Cannot pick more than 1,000 numbers at once")
    
    return (True, None)


def create_verification_file(numbers: list, verification_random: str, signature: str) -> io.BytesIO:
    """
    Create a text file with verification data
    
    Args:
        numbers: List of winning number(s)
        verification_random: Formatted JSON verification data
        signature: Signature from Random.org
        
    Returns:
        BytesIO object containing the text file
    """
    content = f"""╔══════════════════════════════════════════════════════════════╗
║          RANDOM.ORG VERIFICATION DATA                        ║
╚══════════════════════════════════════════════════════════════╝

WINNING NUMBER(S): {', '.join(map(str, numbers))}

═══════════════════════════════════════════════════════════════
HOW TO VERIFY:
═══════════════════════════════════════════════════════════════

1. Go to: https://api.random.org/verify

2. Copy the "RANDOM DATA" section below (everything between the 
   ═══ markers) and paste it into the first field on the page

3. Copy the "SIGNATURE" section below and paste it into the 
   second field on the page

4. Click the "Verify" button

5. If verification succeeds, you'll see a green checkmark 
   confirming these numbers were genuinely generated by 
   Random.org and have not been tampered with

═══════════════════════════════════════════════════════════════
RANDOM DATA:
═══════════════════════════════════════════════════════════════

{verification_random}

═══════════════════════════════════════════════════════════════
SIGNATURE:
═══════════════════════════════════════════════════════════════

{signature}

═══════════════════════════════════════════════════════════════
TECHNICAL DETAILS:
═══════════════════════════════════════════════════════════════

This verification uses cryptographic signatures to prove that:
• These numbers were generated by Random.org's servers
• The numbers have not been modified after generation
• The generation parameters (range, count) are authentic
• The timestamp shows when generation occurred

Random.org uses a digital signature that can only be created by
their servers. If the signature verifies successfully, it's
mathematically impossible for these numbers to have been faked
or altered.

For more information about Random.org's verification system:
https://www.random.org/faq/#Q4.3
"""
    
    file_bytes = io.BytesIO(content.encode('utf-8'))
    file_bytes.seek(0)
    return file_bytes


def create_verification_dm_embed(reddit_info: dict = None, numbers: list = None, 
                                 total_spots: int = None, timestamp: str = None, 
                                 caller_name: str = None) -> discord.Embed:
    """
    Create embed for DM with verification instructions and raffle info
    
    Args:
        reddit_info: Reddit post information
        numbers: List of winning numbers
        total_spots: Total number of spots
        timestamp: Timestamp of the call
        caller_name: Name of user who called the command
    
    Returns:
        Discord Embed object
    """
    embed = discord.Embed(
        title="🔐 Verification Data",
        color=config.EMBED_COLOR
    )
    
    # Build description with raffle info
    description_lines = []
    
    if reddit_info:
        description_lines.append(f"[{reddit_info['author']}]({reddit_info['author_url']}) | [Raffle Link]({reddit_info['url']})")
    
    if total_spots:
        description_lines.append(f"**Spots:** 1-{total_spots}")
    
    if numbers:
        if len(numbers) == 1:
            description_lines.append(f"**Winning Numbers:** {numbers[0]}")
        else:
            numbers_str = ", ".join(map(str, numbers))
            description_lines.append(f"**Winning Numbers:** {numbers_str}")
    
    # Add winners section if spot assignments are available
    if reddit_info and reddit_info.get('spot_assignments') and numbers:
        spot_assignments = reddit_info['spot_assignments']
        description_lines.append("")
        description_lines.append("**Winners:**")
        
        for number in numbers:
            username = spot_assignments.get(number, "Unknown")
            if username != "Unknown":
                description_lines.append(f"{number} - [{username}](https://reddit.com/u/{username})")
            else:
                description_lines.append(f"{number} - {username}")
    
    description_lines.append("")
    description_lines.append("**Verification Instructions:**")
    description_lines.append("1. Download the attached `.txt` file")
    description_lines.append("2. Open it and follow the instructions inside")
    description_lines.append("3. Visit [Random.org Verification](https://api.random.org/verify)")
    description_lines.append("4. Copy/paste the data as instructed")
    description_lines.append("")
    description_lines.append("This proves the numbers were genuinely random and unmodified!")
    
    embed.description = "\n".join(description_lines)
    
    # Set image if available
    if reddit_info and reddit_info.get('image_url'):
        embed.set_image(url=reddit_info['image_url'])
    
    # Set footer with timestamp and caller
    if timestamp:
        from datetime import datetime
        import pytz
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            est = pytz.timezone('US/Eastern')
            dt_est = dt.astimezone(est)
            formatted_time = dt_est.strftime('%Y-%m-%d %I:%M %p')
            if caller_name:
                footer_text = f"{formatted_time} | {caller_name}"
            else:
                footer_text = formatted_time
            embed.set_footer(text=footer_text)
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not format timestamp {timestamp}: {e}")
            if caller_name:
                embed.set_footer(text=f"{timestamp} | {caller_name}")
            else:
                embed.set_footer(text=timestamp)
    elif caller_name:
        embed.set_footer(text=caller_name)
    
    return embed


class VerificationButton(discord.ui.View):
    """Persistent button view that retrieves verification data from database"""
    
    def __init__(self, database):
        super().__init__(timeout=None)  # Never timeout - persistent across restarts
        self.database = database
    
    @discord.ui.button(label="Click to Verify", style=discord.ButtonStyle.primary, custom_id="persistent:verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle verification button click"""
        try:
            # Get verification data from database using the message ID
            message_id = interaction.message.id
            data = self.database.get_verification(message_id)
            
            if not data:
                await interaction.response.send_message(
                    "❌ Verification data not found. This may be an old message from before the database was implemented.",
                    ephemeral=True
                )
                return
            
            # Create the verification file
            file_content = create_verification_file(
                data['numbers'],
                data['verification_random'],
                data['signature']
            )
            
            # Create Discord file
            discord_file = discord.File(
                fp=file_content,
                filename=f"verification_data_{interaction.id}.txt"
            )
            
            # Create DM embed with all raffle information
            dm_embed = create_verification_dm_embed(
                reddit_info=data.get('reddit_info'),
                numbers=data['numbers'],
                total_spots=data.get('total_spots'),
                timestamp=data.get('timestamp'),
                caller_name=data.get('caller_name')
            )
            
            # Send DM to user
            try:
                await interaction.user.send(
                    embed=dm_embed,
                    file=discord_file
                )
                
                # Respond to interaction
                await interaction.response.send_message(
                    "✅ Check your DMs! I've sent you the verification data.",
                    ephemeral=True
                )
                
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ I couldn't send you a DM. Please enable DMs from server members and try again.",
                    ephemeral=True
                )
                
        except Exception as e:
            await interaction.response.send_message(
                "❌ An error occurred while sending verification data. Please try again.",
                ephemeral=True
            )
            import logging
            logging.getLogger('GloveAndHisBoy').exception(f"Error in verification button: {e}")

