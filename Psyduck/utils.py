import discord
import io
import json
import base64
import logging
import config
import re
from functools import lru_cache

logger = logging.getLogger('Psyduck')


# Cache for normalized member names to improve fuzzy matching performance
# Key: (member_id, name_type), Value: normalized_name
_member_name_cache = {}


def _get_normalized_member_names(member: discord.Member) -> tuple:
    """
    Get cached normalized names for a member
    
    Returns:
        Tuple of (normalized_display_name, normalized_username)
    """
    cache_key = member.id
    if cache_key not in _member_name_cache:
        # Remove emojis, special characters, and normalize
        # Keep only alphanumeric characters
        display_clean = re.sub(r'[^a-z0-9]', '', member.display_name.lower())
        name_clean = re.sub(r'[^a-z0-9]', '', member.name.lower())
        _member_name_cache[cache_key] = (display_clean, name_clean)
    
    return _member_name_cache[cache_key]


def clear_member_cache():
    """Clear the member name cache (useful for testing or after guild updates)"""
    global _member_name_cache
    _member_name_cache = {}


def format_timestamp_est(timestamp: str, caller_name: str = None) -> str:
    """
    Format ISO timestamp to EST timezone with optional caller name
    
    Args:
        timestamp: ISO format timestamp string
        caller_name: Optional Discord username to include
        
    Returns:
        Formatted timestamp string for footer
    """
    from datetime import datetime
    import pytz
    
    try:
        # Parse ISO timestamp
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        # Convert to EST
        est = pytz.timezone('US/Eastern')
        dt_est = dt.astimezone(est)
        # Format as requested
        formatted_time = dt_est.strftime('%Y-%m-%d %I:%M %p')
        
        if caller_name:
            return f"Discord Bot Caller: {caller_name} | {formatted_time}"
        return formatted_time
    except Exception as e:
        logger.warning(f"Error formatting timestamp: {e}")
        if caller_name:
            return f"Discord Bot Caller: {caller_name} | {timestamp}"
        return timestamp


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
    logger.info(f"Building embed with Reddit info - Author: {reddit_info.get('author')}, Has image: {bool(reddit_info.get('image_url'))}")
    
    # Build description with all info in vertical order
    description_lines = []
    embed = discord.Embed(
        title=reddit_info['title'],
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
            # Try both int and string keys (int for fresh data, string for JSON-deserialized data)
            username = spot_assignments.get(number, spot_assignments.get(str(number), "Unknown"))
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
        footer_text = format_timestamp_est(timestamp, caller_name)
        embed.set_footer(text=footer_text)
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


def validate_parameters(winners: int, spots: int) -> tuple:
    """
    Validate the command parameters
    
    Args:
        winners: Number of winners to pick
        spots: Total number of spots in the raffle
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if winners is None or spots is None:
        return (False, "Invalid command parameters")
    
    if winners < 1:
        return (False, "Number of winners must be at least 1")
    
    if spots < 2:
        return (False, "Number of spots must be at least 2")
    
    if winners > spots:
        return (False, f"Cannot pick {winners} unique winners from {spots} spots")
    
    if spots > config.MAX_SPOTS:
        return (False, f"Maximum spots cannot exceed {config.MAX_SPOTS:,}")
    
    if winners > config.MAX_WINNERS:
        return (False, f"Cannot pick more than {config.MAX_WINNERS:,} winners at once")
    
    return (True, None)


def match_reddit_to_discord_user(reddit_username: str, guild_members: list) -> discord.Member:
    """
    Match a Reddit username to a Discord guild member using fuzzy matching.
    Handles Discord usernames with emojis and decorations.
    Uses caching to improve performance on large servers.
    
    Args:
        reddit_username: Reddit username to match (full username, not truncated)
        guild_members: List of Discord guild members
        
    Returns:
        Discord Member object if found, None otherwise
    """
    # Normalize Reddit username - remove u/ prefix if present and lowercase
    reddit_clean = reddit_username.lower().replace('u/', '').replace('_', '').replace('-', '')
    
    best_match = None
    best_score = 0
    
    for member in guild_members:
        # Skip bots
        if member.bot:
            continue
        
        # Get cached normalized names
        display_clean, name_clean = _get_normalized_member_names(member)
        
        # Check both display_name and name (username)
        for discord_clean in [display_clean, name_clean]:
            # Skip if either name is too short
            if len(discord_clean) < config.MIN_MATCH_LENGTH or len(reddit_clean) < config.MIN_MATCH_LENGTH:
                continue
            
            # Exact match after normalization
            if discord_clean == reddit_clean:
                return member
            
            # Check if reddit username is contained in discord name
            if reddit_clean in discord_clean and len(reddit_clean) >= config.MIN_MATCH_LENGTH:
                score = len(reddit_clean) / len(discord_clean)
                if score > best_score:
                    best_score = score
                    best_match = member
            
            # Check if discord name is contained in reddit username
            if discord_clean in reddit_clean and len(discord_clean) >= config.MIN_MATCH_LENGTH:
                score = len(discord_clean) / len(reddit_clean)
                if score > best_score:
                    best_score = score
                    best_match = member
    
    # Return best match if score is good enough
    if best_score >= config.MIN_MATCH_SCORE:
        return best_match
    
    return None


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
                                 caller_name: str = None, verification_random: str = None,
                                 signature: str = None) -> tuple:
    """
    Create embed(s) for DM with verification instructions and raffle info
    
    Args:
        reddit_info: Reddit post information
        numbers: List of winning numbers
        total_spots: Total number of spots
        timestamp: Timestamp of the call
        caller_name: Name of user who called the command
        verification_random: Random.org verification JSON data
        signature: Random.org signature
    
    Returns:
        Tuple of (main_embed, verification_embed or None)
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
            # Try both int and string keys (int for fresh data, string for JSON-deserialized data)
            username = spot_assignments.get(number, spot_assignments.get(str(number), "Unknown"))
            if username != "Unknown":
                description_lines.append(f"{number} - [{username}](https://reddit.com/u/{username})")
            else:
                description_lines.append(f"{number} - {username}")
    
    # Calculate if we need separate embed for verification
    # Estimate size: description + verification fields (Random Data ~800 chars, Signature ~350 chars)
    description_text = "\n".join(description_lines)
    verification_fields_size = len(verification_random or "") + len(signature or "") + 200  # +200 for field names and formatting
    
    # Discord limits: description 4096 chars, total embed ~6000 chars
    # If description + verification would be too large, split into separate embed
    needs_separate_verification = (len(description_text) + verification_fields_size) > 3500
    
    verification_embed = None
    
    if needs_separate_verification:
        # Don't add verification instructions to main embed
        embed.description = description_text
        
        # Create separate verification embed
        verification_embed = discord.Embed(
            title="🔐 Verification Instructions",
            color=config.EMBED_COLOR
        )
        
        verification_instructions = [
            "**How to Verify:**",
            "1. Visit [Random.org Verification](https://api.random.org/verify)",
            "2. Copy **Random Data** below → Paste in first field",
            "3. Copy **Signature** below → Paste in second field",
            "4. Click Verify ✅",
            "",
            "This proves the numbers were genuinely random and unmodified!"
        ]
        verification_embed.description = "\n".join(verification_instructions)
        
        # Add verification fields to separate embed
        if verification_random:
            verification_embed.add_field(
                name="Random Data",
                value=f"```json\n{verification_random}\n```",
                inline=False
            )
        
        if signature:
            verification_embed.add_field(
                name="Signature",
                value=f"```\n{signature}\n```",
                inline=False
            )
    else:
        # Add verification instructions to main embed
        description_lines.append("")
        description_lines.append("**Verification Instructions:**")
        description_lines.append("1. Visit [Random.org Verification](https://api.random.org/verify)")
        description_lines.append("2. Copy **Random Data** below → Paste in first field")
        description_lines.append("3. Copy **Signature** below → Paste in second field")
        description_lines.append("4. Click Verify ✅")
        description_lines.append("")
        description_lines.append("This proves the numbers were genuinely random and unmodified!")
        
        embed.description = "\n".join(description_lines)
        
        # Add verification fields to main embed
        if verification_random:
            embed.add_field(
                name="Random Data",
                value=f"```json\n{verification_random}\n```",
                inline=False
            )
        
        if signature:
            embed.add_field(
                name="Signature",
                value=f"```\n{signature}\n```",
                inline=False
            )
    
    # Set image if available (only on main embed)
    if reddit_info and reddit_info.get('image_url'):
        embed.set_image(url=reddit_info['image_url'])
    
    # Set footer with timestamp and caller
    if timestamp:
        footer_text = format_timestamp_est(timestamp, caller_name)
        embed.set_footer(text=footer_text)
    elif caller_name:
        embed.set_footer(text=caller_name)
    
    return (embed, verification_embed)


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
            
            # Create DM embed(s) with all raffle information and verification data
            dm_embed, verification_embed = create_verification_dm_embed(
                reddit_info=data.get('reddit_info'),
                numbers=data['numbers'],
                total_spots=data.get('total_spots'),
                timestamp=data.get('timestamp'),
                caller_name=data.get('caller_name'),
                verification_random=data['verification_random'],
                signature=data['signature']
            )
            
            # Send DM to user
            try:
                await interaction.user.send(embed=dm_embed)
                
                # If verification data is in separate embed, send it as well
                if verification_embed:
                    await interaction.user.send(embed=verification_embed)
                
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
            logging.getLogger('Psyduck').exception(f"Error in verification button: {e}")

