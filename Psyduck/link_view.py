"""
Persistent view and modal for linking Reddit usernames to Discord users
"""

import discord
import logging
import config
from utils import match_reddit_to_discord_user

logger = logging.getLogger('Psyduck')


class LinkButton(discord.ui.View):
    """Persistent view with link button for winner announcements"""
    
    def __init__(self, link_db):
        super().__init__(timeout=None)  # Persistent - survives bot restarts
        self.link_db = link_db
    
    @discord.ui.button(emoji="🔗", style=discord.ButtonStyle.secondary, custom_id="link_winner_button_persistent")
    async def link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the link button click"""
        try:
            # Check if user is admin
            if interaction.user.id != config.ADMIN_USER_ID:
                # Silently ignore non-admin users
                await interaction.response.defer()
                return
            
            # Get message mapping to find winners
            message_id = interaction.message.id
            mapping = self.link_db.get_message_mapping(message_id)
            
            if not mapping:
                await interaction.response.send_message(
                    "❌ Could not find winner information for this message.",
                    ephemeral=True
                )
                return
            
            reddit_usernames = mapping.get('reddit_usernames', [])
            
            if not reddit_usernames:
                await interaction.response.send_message(
                    "❌ No winners found in this announcement.",
                    ephemeral=True
                )
                return
            
            # If single winner, go straight to modal
            if len(reddit_usernames) == 1:
                modal = LinkModal(reddit_usernames[0], self.link_db, message_id, interaction.message)
                await interaction.response.send_modal(modal)
            else:
                # Multiple winners - show dropdown
                view = WinnerSelectView(reddit_usernames, self.link_db, message_id, interaction.message)
                await interaction.response.send_message(
                    "Select a Reddit user to link:",
                    view=view,
                    ephemeral=True
                )
        
        except Exception as e:
            logger.exception(f"Error in link button handler: {e}")
            try:
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
            except Exception as e:
                logger.warning(f"Could not send error response: {e}")


class WinnerSelectView(discord.ui.View):
    """Dropdown menu to select which winner to link"""
    
    def __init__(self, reddit_usernames: list, link_db, message_id: int, original_message: discord.Message):
        super().__init__(timeout=300)  # 5 minute timeout
        self.link_db = link_db
        self.message_id = message_id
        self.original_message = original_message
        
        # Deduplicate usernames (same user might have won multiple spots)
        unique_usernames = list(dict.fromkeys(reddit_usernames))
        
        # Create dropdown options
        options = []
        for username in unique_usernames:
            # Check if already linked
            discord_id = link_db.get_discord_id(username)
            label = f"u/{username}"
            description = f"Linked to <@{discord_id}>" if discord_id else "Not linked yet"
            
            options.append(discord.SelectOption(
                label=label[:100],  # Discord limit
                value=username,
                description=description[:100],
                emoji="🔗" if discord_id else "❓"
            ))
        
        # Add the select menu
        select = discord.ui.Select(
            placeholder="Choose a Reddit user to link...",
            options=options,
            custom_id="winner_select"
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        """Handle winner selection from dropdown"""
        try:
            selected_username = interaction.data['values'][0]
            
            # Show modal for linking
            modal = LinkModal(selected_username, self.link_db, self.message_id, self.original_message)
            await interaction.response.send_modal(modal)
        
        except Exception as e:
            logger.exception(f"Error in select callback: {e}")
            await interaction.response.send_message("❌ An error occurred.", ephemeral=True)


class LinkModal(discord.ui.Modal, title="Link Reddit User"):
    """Modal for entering Discord user ID to link"""
    
    def __init__(self, reddit_username: str, link_db, message_id: int, original_message: discord.Message):
        super().__init__()
        self.reddit_username = reddit_username
        self.link_db = link_db
        self.message_id = message_id
        self.original_message = original_message
        
        # Check if already linked
        existing_discord_id = link_db.get_discord_id(reddit_username)
        default_value = existing_discord_id if existing_discord_id else ""
        
        # Add text input for Discord user ID
        self.discord_id_input = discord.ui.TextInput(
            label=f"Discord User ID for u/{reddit_username}",
            placeholder="Enter Discord User ID (numbers only)",
            default=default_value,
            max_length=20,
            required=True
        )
        self.add_item(self.discord_id_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission"""
        try:
            discord_user_id = self.discord_id_input.value.strip()
            
            # Validate it's a number
            if not discord_user_id.isdigit():
                await interaction.response.send_message(
                    "❌ Invalid Discord User ID. Must be numbers only.",
                    ephemeral=True
                )
                return
            
            # Try to fetch the user to verify they exist
            try:
                user = await interaction.client.fetch_user(int(discord_user_id))
            except Exception as e:
                logger.warning(f"Could not verify Discord user {discord_user_id}: {e}")
                await interaction.response.send_message(
                    "⚠️ Warning: Could not find Discord user with that ID. Link created anyway.",
                    ephemeral=True
                )
                user = None
            
            # Save the link
            success = self.link_db.add_link(
                self.reddit_username,
                discord_user_id,
                str(interaction.user.id)
            )
            
            if success:
                user_mention = f"<@{discord_user_id}>"
                await interaction.response.send_message(
                    f"✅ Linked u/{self.reddit_username} → {user_mention}",
                    ephemeral=True
                )
                
                # Edit the original message to update mentions
                try:
                    await self.update_winner_message(interaction.client)
                except Exception as e:
                    logger.exception(f"Error updating winner message: {e}")
            else:
                await interaction.response.send_message(
                    "❌ Failed to create link.",
                    ephemeral=True
                )
        
        except Exception as e:
            logger.exception(f"Error in modal submit: {e}")
            await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
    
    async def update_winner_message(self, bot):
        """Update the original winner announcement with new mentions"""
        try:
            # Get the mapping to find all winners
            mapping = self.link_db.get_message_mapping(self.message_id)
            if not mapping:
                return
            
            reddit_usernames = mapping.get('reddit_usernames', [])
            
            # Get guild members for fuzzy matching
            guild = self.original_message.guild
            guild_members = guild.members if guild else []
            
            # Get all mentions (both from DB and fuzzy matching)
            mentions = []
            for username in reddit_usernames:
                # Check database first for manual links
                discord_id = self.link_db.get_discord_id(username)
                if discord_id:
                    mentions.append(f"<@{discord_id}>")
                else:
                    # Fall back to fuzzy matching
                    discord_member = match_reddit_to_discord_user(username, guild_members)
                    if discord_member:
                        mentions.append(discord_member.mention)
            
            # Build new content
            if mentions:
                if len(reddit_usernames) == 1:
                    new_content = f"# WINNER\n{mentions[0]}"
                else:
                    new_content = "# WINNERS\n" + "\n".join(mentions)
            else:
                if len(reddit_usernames) == 1:
                    new_content = "# WINNER"
                else:
                    new_content = "# WINNERS"
            
            # Edit the message
            await self.original_message.edit(content=new_content)
            logger.info(f"Updated winner message {self.message_id} with new mentions")
        
        except Exception as e:
            logger.exception(f"Error updating winner message: {e}")
