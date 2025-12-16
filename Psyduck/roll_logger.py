"""
Roll Logger module for tracking daily roll history
"""

import discord
import logging
from datetime import datetime
from typing import Dict, Optional
import json
import pytz

logger = logging.getLogger('GloveAndHisBoy')


class RollLogger:
    """Manages daily roll history tracking and embed updates"""
    
    def __init__(self):
        """Initialize roll logger"""
        self.current_date = None
        self.current_message_id = None
        self.roll_counts = {}  # {number: count}
        self.est = pytz.timezone('US/Eastern')
        logger.info("Roll logger initialized")
    
    def _get_current_date_est(self) -> str:
        """Get current date in EST formatted as M/D/YY"""
        now = datetime.now(self.est)
        # Use %m/%d/%y and strip leading zeros manually (Windows compatible)
        month = now.month
        day = now.day
        year = now.strftime('%y')
        return f"{month}/{day}/{year}"  # 12/15/25 format
    
    async def log_roll(self, channel: discord.TextChannel, numbers: list):
        """
        Log rolled numbers to the daily history
        
        Args:
            channel: Discord channel for roll log
            numbers: List of numbers that were rolled
        """
        try:
            current_date = self._get_current_date_est()
            
            # Check if we need to create a new day's embed
            if current_date != self.current_date:
                await self._create_new_day_embed(channel, current_date)
            
            # Update roll counts
            for number in numbers:
                self.roll_counts[number] = self.roll_counts.get(number, 0) + 1
            
            # Update the embed
            await self._update_embed(channel)
            
            logger.info(f"Logged {len(numbers)} number(s) to roll history")
            
        except Exception as e:
            logger.exception(f"Error logging roll: {e}")
    
    async def _create_new_day_embed(self, channel: discord.TextChannel, date: str):
        """
        Create a new embed for a new day
        
        Args:
            channel: Discord channel for roll log
            date: Date string (M/D/YY format)
        """
        try:
            # Reset for new day
            self.current_date = date
            self.roll_counts = {}
            
            # Send date message
            date_message = await channel.send(date)
            
            # Create initial empty embed
            embed = discord.Embed(
                title="Roll History",
                description="No rolls yet today.",
                color=0x00FF00
            )
            
            # Send embed
            embed_message = await channel.send(embed=embed)
            self.current_message_id = embed_message.id
            
            logger.info(f"Created new roll history embed for {date}")
            
        except Exception as e:
            logger.exception(f"Error creating new day embed: {e}")
    
    async def _update_embed(self, channel: discord.TextChannel):
        """
        Update the current day's embed with latest roll counts
        
        Args:
            channel: Discord channel for roll log
        """
        try:
            if not self.current_message_id:
                logger.warning("No current message ID to update")
                return
            
            # Sort by count (descending)
            sorted_rolls = sorted(
                self.roll_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            # Build description
            if sorted_rolls:
                lines = []
                for i, (number, count) in enumerate(sorted_rolls, 1):
                    lines.append(f"{i}. {number}|{count}")
                description = "\n".join(lines)
            else:
                description = "No rolls yet today."
            
            # Create updated embed
            embed = discord.Embed(
                title="Roll History",
                description=description,
                color=0x00FF00
            )
            
            # Fetch and edit the message
            message = await channel.fetch_message(self.current_message_id)
            await message.edit(embed=embed)
            
            logger.debug(f"Updated roll history embed with {len(sorted_rolls)} entries")
            
        except discord.errors.NotFound:
            logger.error(f"Roll history message {self.current_message_id} not found")
            self.current_message_id = None
        except Exception as e:
            logger.exception(f"Error updating embed: {e}")
    
    async def initialize_from_channel(self, channel: discord.TextChannel):
        """
        Initialize logger by finding today's embed in the channel
        
        Args:
            channel: Discord channel for roll log
        """
        try:
            current_date = self._get_current_date_est()
            
            # Look through recent messages to find today's embed
            async for message in channel.history(limit=50):
                # Check if this is an embed message
                if message.embeds and message.embeds[0].title == "Roll History":
                    # Check if the previous message is today's date
                    # Get message before this embed
                    messages_before = []
                    async for msg in channel.history(limit=2, before=message):
                        messages_before.append(msg)
                    
                    if messages_before and messages_before[0].content == current_date:
                        # Found today's embed
                        self.current_message_id = message.id
                        self.current_date = current_date
                        
                        # Parse existing roll counts from embed
                        description = message.embeds[0].description
                        if description and description != "No rolls yet today.":
                            for line in description.split('\n'):
                                # Parse "1. 42|5" format
                                if '|' in line:
                                    parts = line.split('.')
                                    if len(parts) >= 2:
                                        number_count = parts[1].strip().split('|')
                                        if len(number_count) == 2:
                                            try:
                                                number = int(number_count[0])
                                                count = int(number_count[1])
                                                self.roll_counts[number] = count
                                            except ValueError:
                                                pass
                        
                        logger.info(f"Initialized roll logger from existing embed (ID: {self.current_message_id})")
                        return
            
            # No today's embed found, create new one
            logger.info("No existing roll history found for today, will create on first roll")
            
        except Exception as e:
            logger.exception(f"Error initializing from channel: {e}")
