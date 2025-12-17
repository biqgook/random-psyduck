"""
Command processing for the /call slash command
"""

import discord
import logging
import re
import config
from utils import (
    create_winner_embed,
    validate_parameters,
    VerificationButton,
    match_reddit_to_discord_user
)

logger = logging.getLogger('Psyduck')


async def send_error_to_admin(bot, user: discord.User, error_reason: str):
    """
    Send error notification to admin via DM
    
    Args:
        bot: Discord bot instance
        user: User who triggered the error
        error_reason: Description of the error
    """
    try:
        admin = await bot.fetch_user(config.ADMIN_USER_ID)
        embed = discord.Embed(
            title=f"{user.name}#{user.discriminator}" if user.discriminator != "0" else user.name,
            description=f"**Error:** {error_reason}",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"User ID: {user.id}")
        await admin.send(embed=embed)
        logger.info(f"Sent error notification to admin for user {user.name}: {error_reason}")
    except Exception as e:
        logger.exception(f"Failed to send error notification to admin: {e}")


def parse_spots_from_title(title: str) -> int:
    """
    Parse the number of spots from Reddit post title
    
    Examples:
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


async def process_call_command(
    channel: discord.TextChannel,
    reddit_url: str,
    spots: int,
    winners: int,
    caller_user: discord.User,
    bot,
    random_org,
    reddit_manager,
    verification_db,
    link_db,
    roll_logger,
    roll_id: int,
    general_chat_id: int,
    interaction: discord.Interaction = None
):
    """
    Process the actual command execution for /call
    
    Args:
        channel: Discord channel where command was called
        reddit_url: URL to Reddit raffle post
        spots: Total number of spots in raffle
        winners: Number of winners to select
        caller_user: Discord user who called the command
        bot: Discord bot instance
        random_org: RandomOrgManager instance
        reddit_manager: RedditManager instance
        verification_db: VerificationDatabase instance
        link_db: LinkDatabase instance
        roll_logger: RollLogger instance
        roll_id: Channel ID for roll logging
        general_chat_id: Channel ID for general chat announcements
        interaction: Discord interaction for ephemeral responses (optional)
    """
    caller_name = caller_user.display_name
    from bot import load_links, called_links_lock
    
    # Validate Reddit URL format before API call
    reddit_url_pattern = r'^https?://(www\.)?(reddit\.com|redd\.it)/'
    if not re.match(reddit_url_pattern, reddit_url, re.IGNORECASE):
        await send_error_to_admin(bot, caller_user, f"Invalid Reddit URL format: {reddit_url}")
        if interaction:
            await interaction.followup.send("❌ **Invalid Reddit URL**\n\nPlease provide a valid Reddit link.", ephemeral=True)
        return
    
    # Thread-safe loading of called links
    async with called_links_lock:
        links = load_links("called_links.txt")
    
    is_admin = (caller_user.id == config.ADMIN_USER_ID)

    logger.info(f'Processing call command. caller_name: {caller_name} | reddit_url: {reddit_url} | spots: {spots} | winners: {winners} | is_admin: {is_admin}')
    
    # Fetch Reddit post information
    reddit_info = None
    if reddit_manager:
        try:
            reddit_info = await reddit_manager.get_post_info(reddit_url)
            if not reddit_info:
                await send_error_to_admin(bot, caller_user, "Could not fetch Reddit post information")
                if interaction:
                    await interaction.followup.send("❌ **Unable to fetch Reddit post**\n\nPlease verify the link and try again.", ephemeral=True)
                return
            else:
                link = reddit_info['url']
                logger.info(f'Checking if raffle already called. Current links: {len(links)} total')
                
                # Check for duplicate but DON'T write to file yet
                if link in links:
                    # Allow admin to bypass duplicate check (for re-rolls in case of errors)
                    if not is_admin:
                        await send_error_to_admin(bot, caller_user, f"Duplicate raffle call attempted: {link}\n\n**This raffle has already been called.**")
                        if interaction:
                            await interaction.followup.send("❌ **This raffle has already been called**\n\nContact an admin if you believe this is an error.", ephemeral=True)
                        return
                    else:
                        logger.info(f"Admin {caller_name} bypassing duplicate check for: {link}")
                    
                # If spots not provided, try to parse from Reddit title
                if spots is None and reddit_info.get('title'):
                    parsed_spots = parse_spots_from_title(reddit_info['title'])
                    if parsed_spots:
                        spots = parsed_spots
                        logger.info(f"Using parsed spots value: {spots}")
                    else:
                        await send_error_to_admin(bot, caller_user, f"Could not parse spots from Reddit title: {reddit_info['title']}")
                        if interaction:
                            await interaction.followup.send("❌ **Could not determine number of spots**\n\nPlease include the spots parameter.", ephemeral=True)
                        return
        except Exception as e:
            logger.exception(f"Error fetching Reddit info: {e}")
            await send_error_to_admin(bot, caller_user, f"Error fetching Reddit post: {str(e)}")
            if interaction:
                await interaction.followup.send("❌ **Error fetching Reddit post**\n\nPlease try again later.", ephemeral=True)
            return
    
    # If spots still not determined, send error
    if spots is None:
        await send_error_to_admin(bot, caller_user, "Number of spots not provided and could not be parsed from Reddit post")
        if interaction:
            await interaction.followup.send("❌ **Number of spots required**\n\nCould not determine spots from Reddit post. Please include the spots parameter.", ephemeral=True)
        return
    
    # Now validate parameters with the determined spots value
    is_valid, error_message = validate_parameters(winners, spots)
    if not is_valid:
        await send_error_to_admin(bot, caller_user, f"Invalid parameters: {error_message}")
        if interaction:
            await interaction.followup.send(f"❌ **Invalid spot to winner ratio**\n\n{error_message}", ephemeral=True)
        return
    
    # Validate winners against actual participants from Reddit post
    if reddit_info and reddit_info.get('spot_assignments'):
        total_assigned_spots = len(reddit_info['spot_assignments'])
        if winners > total_assigned_spots:
            await send_error_to_admin(
                bot, 
                caller_user, 
                f"Cannot select {winners} winners from only {total_assigned_spots} participants in the Reddit post"
            )
            if interaction:
                await interaction.followup.send(f"❌ **Invalid spot to winner ratio**\n\nCannot pick {winners} unique winners from {total_assigned_spots} spots.", ephemeral=True)
            return
        logger.info(f"Validated: {winners} winners requested from {total_assigned_spots} participants")
    
    try:
        # Generate random numbers (will retry every 5 minutes if API is down)
        result = await random_org.generate_random_numbers(winners, spots)
        
        # Extract data from result
        random_data = result['random']
        signature = result['signature']
        numbers = random_data['data']
        
        # Get request count
        request_count, request_limit = random_org.get_total_requests()
        
        # Format verification data
        verification_json = random_org.format_verification_data(random_data)
        
        # Get timestamp from Random.org response
        timestamp = random_data.get('completionTime', 'N/A')
        
        # Add winners section if spot assignments are available
        if reddit_info and reddit_info.get('spot_assignments') and len(reddit_info['spot_assignments']) > 0:
            spot_assignments = reddit_info['spot_assignments']
            user_spot_counts = reddit_info.get('user_spot_counts', {})
            winner_arr = []
            for number in numbers:
                username = spot_assignments.get(number, spot_assignments.get(str(number), "Unknown"))
                # Create hyperlink to user's Reddit profile with percentage
                if username != "Unknown":
                    # Calculate percentage
                    user_spots = user_spot_counts.get(username, 0)
                    percentage = (user_spots / spots * 100) if spots > 0 else 0
                    # Format percentage to remove trailing zeros (17.5% instead of 17.50%)
                    percentage_str = f"{percentage:.1f}".rstrip('0').rstrip('.')
                    winner_arr.append(f"{number} - [{username}](https://reddit.com/u/{username}) {percentage_str}%")
                else:
                    winner_arr.append(f"{number} - {username}")
        
            header = "# Winner:\n\n" if len(numbers) == 1 else "# Winners:\n\n"
            winning_content = header + "\n".join(winner_arr)
        else:
            # Log why spot assignments weren't available
            if not reddit_info:
                logger.warning("No Reddit info available")
            elif not reddit_info.get('spot_assignments'):
                logger.warning("Reddit info missing spot_assignments key")
            elif len(reddit_info['spot_assignments']) == 0:
                logger.warning(f"Reddit post has no spot assignments - Post may not have participant list yet. Check: {reddit_info.get('url', 'unknown URL')}")
                # Send notification to admin about missing spot assignments
                await send_error_to_admin(
                    bot, 
                    caller_user, 
                    f"⚠️ **Raffle completed but no participants found in Reddit post**\n\n"
                    f"**Reddit URL:** {reddit_info.get('url', 'unknown')}\n"
                    f"**Winning Number:** {numbers[0] if len(numbers) == 1 else ', '.join(map(str, numbers))}\n\n"
                    f"_The Reddit post may not have the participant list filled in yet. "
                    f"You may need to manually verify the winner._"
                )
            
            header = "# Winning number:\n\n" if len(numbers) == 1 else "# Winning numbers:\n\n"
            winning_content = header + "\n".join(map(str, numbers))

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
            roll_log_channel = bot.get_channel(roll_id)
            if roll_log_channel:
                await roll_logger.log_roll(roll_log_channel, numbers)
            else:
                logger.warning(f"Roll log channel {roll_id} not found")
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
        
        # Send winner announcement to general chat
        await send_general_chat_announcement(
            channel, numbers, reddit_info, spots, response_message,
            bot, link_db, general_chat_id
        )
        
        # Send DM to caller with results
        await send_caller_dm(
            caller_user, response_message, numbers, reddit_info, spots, timestamp
        )
        
        # SUCCESS - Now mark raffle as called (only after everything completes)
        link = reddit_info['url']
        
        # Write to called_links.txt unless this is an admin re-rolling a duplicate
        # Admin re-rolls: is_admin=True AND link already in links
        is_admin_reroll = is_admin and link in links
        
        if not is_admin_reroll:
            # Thread-safe file writing
            async with called_links_lock:
                # Reload links to ensure we have the latest state
                current_links = load_links("called_links.txt")
                if link not in current_links:
                    with open("called_links.txt", "a", encoding="utf-8") as f:
                        f.write(link + "\n")
                    logger.info(f"Raffle successfully completed and marked as called: {link}")
                else:
                    logger.info(f"Raffle completed but already in called_links.txt: {link}")
        else:
            logger.info(f"Admin re-roll completed, not updating called_links.txt: {link}")
        
    except Exception as e:
        # Send error notification to admin with details
        error_details = f"**Raffle Failed for User:** {caller_user.name}#{caller_user.discriminator if caller_user.discriminator != '0' else ''}\n"
        error_details += f"**Reddit URL:** {reddit_url}\n"
        error_details += f"**Spots:** {spots}, **Winners:** {winners}\n"
        error_details += f"**Error:** {str(e)}\n\n"
        error_details += "_The raffle was NOT marked as called, so the user can retry._"
        
        await send_error_to_admin(bot, caller_user, error_details)
        logger.exception(f"Error processing command: {e}")


async def send_general_chat_announcement(
    channel: discord.TextChannel,
    numbers: list,
    reddit_info: dict,
    spots: int,
    response_message: discord.Message,
    bot,
    link_db,
    general_chat_id: int
):
    """Send winner announcement to general chat channel"""
    try:
        general_channel = bot.get_channel(general_chat_id)
        if not general_channel:
            logger.warning(f"General chat channel {general_chat_id} not found")
            return
        
        if not reddit_info or not reddit_info.get('spot_assignments') or len(reddit_info.get('spot_assignments', {})) == 0:
            logger.warning(f"Skipping general chat announcement - no spot assignments found in Reddit post")
            return
        
        if general_channel and reddit_info and reddit_info.get('spot_assignments'):
            # Get guild members for username matching
            guild = channel.guild
            
            # Ensure guild members are fetched
            if not guild.chunked:
                await guild.chunk()
                logger.info(f"Fetched {len(guild.members)} members from guild")
            
            guild_members = guild.members
            
            # Match Reddit usernames to Discord users and create mentions
            spot_assignments = reddit_info['spot_assignments']
            user_spot_counts = reddit_info.get('user_spot_counts', {})
            mentions = []
            winner_lines = []
            reddit_usernames_list = []  # For storing in message mapping
            
            # Use actual number of assigned spots from Reddit post for percentage calculation
            total_assigned_spots = len(spot_assignments)
            
            logger.debug(f"Processing {len(numbers)} winners for general chat announcement")
            logger.debug(f"user_spot_counts keys: {list(user_spot_counts.keys())}")
            logger.debug(f"Total spots from Reddit post: {total_assigned_spots}")
            
            for number in numbers:
                # Try both int and string keys (int for fresh data, string for JSON-deserialized data)
                reddit_username = spot_assignments.get(number, spot_assignments.get(str(number), "Unknown"))
                if reddit_username != "Unknown":
                    reddit_usernames_list.append(reddit_username)
                    logger.debug(f"Spot {number}: Attempting to match Reddit user '{reddit_username}'")
                    
                    # Check database first for manual links
                    discord_id = link_db.get_discord_id(reddit_username)
                    if discord_id:
                        mentions.append(f"<@{discord_id}>")
                        logger.debug(f"  ✓ Found DB link: u/{reddit_username} → <@{discord_id}>")
                    else:
                        # Fall back to fuzzy matching
                        discord_member = match_reddit_to_discord_user(reddit_username, guild_members)
                        if discord_member:
                            mentions.append(discord_member.mention)
                            logger.debug(f"  ✓ Found fuzzy match: {discord_member.name} ({discord_member.mention})")
                        else:
                            logger.debug(f"  ✗ No Discord match found for '{reddit_username}'")
                    # Calculate percentage - use actual assigned spots from Reddit, not user input
                    user_spots = user_spot_counts.get(reddit_username, 0)
                    logger.debug(f"  User '{reddit_username}' has {user_spots} spots out of {total_assigned_spots} total")
                    percentage = (user_spots / total_assigned_spots * 100) if total_assigned_spots > 0 else 0
                    # Truncate username display to 10 characters for clean embed, but keep full link
                    display_username = reddit_username[:10] if len(reddit_username) > 10 else reddit_username
                    # Add to winner lines with Reddit profile link and percentage (1 decimal place)
                    winner_lines.append(f"{number} - [{display_username}](https://reddit.com/u/{reddit_username}) {percentage:.1f}%")
                else:
                    winner_lines.append(f"{number} - Unknown")
            
            logger.debug(f"Total Discord mentions found: {len(mentions)}")
            
            # Create announcement content - header on its own line, mentions below
            if mentions:
                if len(numbers) == 1:
                    announcement_content = "# WINNER\n" + mentions[0]
                else:
                    announcement_content = "# WINNERS\n" + "\n".join(mentions)
            else:
                if len(numbers) == 1:
                    announcement_content = "# WINNER"
                else:
                    announcement_content = "# WINNERS"
            
            # Create announcement embed
            announcement_embed = discord.Embed(color=config.EMBED_COLOR)
            
            # Extract raffle type tag from title (e.g., [MAIN], [NM], [GIVY], [MINI])
            raffle_title = reddit_info.get('title', '')
            import re
            tag_match = re.match(r'\[([^\]]+)\]', raffle_title)
            if tag_match:
                raffle_tag = tag_match.group(0)  # Includes brackets
                announcement_embed.add_field(
                    name="",
                    value=f"[{raffle_tag}]({reddit_info['url']})",
                    inline=False
                )
            
            # Add winning numbers with Reddit usernames
            winning_numbers_title = "Winning Number:" if len(numbers) == 1 else "Winning Numbers:"
            announcement_embed.add_field(
                name=winning_numbers_title,
                value="\n".join(winner_lines),
                inline=False
            )
            
            # Add Call-Log link below winning numbers
            announcement_embed.add_field(
                name="",
                value=f"[Call-Log]({response_message.jump_url})",
                inline=False
            )
            
            # Set image if available
            if reddit_info.get('image_url'):
                announcement_embed.set_image(url=reddit_info['image_url'])
            
            # Add link button for manual username mapping
            from link_view import LinkButton
            link_view = LinkButton(link_db)
            
            # Send announcement with button
            announcement_message = await general_channel.send(
                content=announcement_content,
                embed=announcement_embed,
                view=link_view
            )
            
            # Store message mapping for retroactive updates
            link_db.store_message_mapping(
                announcement_message.id,
                general_channel.id,
                reddit_usernames_list
            )
            
            logger.info(f"Sent winner announcement to general chat #{general_channel.name}")
    except Exception as e:
        logger.exception(f"Error sending general chat announcement: {e}")


async def send_caller_dm(
    caller_user: discord.User,
    response_message: discord.Message,
    numbers: list,
    reddit_info: dict,
    spots: int,
    timestamp: str
):
    """Send DM to command caller with results"""
    try:
        # Create DM embed
        dm_embed = discord.Embed(
            title="Record",
            description=f"[Jump to Results]({response_message.jump_url})",
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
            from utils import format_timestamp_est
            dm_embed.set_footer(text=format_timestamp_est(timestamp))
        
        await caller_user.send(embed=dm_embed)
        logger.info(f"Sent results DM to {caller_user.name}")
        
    except discord.Forbidden:
        logger.warning(f"Could not send DM to {caller_user.name} - DMs disabled")
    except Exception as e:
        logger.exception(f"Error sending DM to caller: {e}")
