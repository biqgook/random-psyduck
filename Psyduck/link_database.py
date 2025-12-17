"""
Link database module for storing Reddit-Discord username mappings
Separate from verification database to preserve links across db wipes
"""

import sqlite3
import json
import logging
import time
from typing import Optional, Dict, List
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger('Psyduck')


def retry_on_db_error(max_retries=3, delay=0.1):
    """Decorator to retry database operations on transient failures"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"DB operation failed (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(delay * (attempt + 1))  # Exponential backoff
                    else:
                        logger.exception(f"DB operation failed after {max_retries} attempts: {e}")
                except Exception as e:
                    logger.exception(f"Unexpected database error: {e}")
                    raise
            raise last_exception
        return wrapper
    return decorator


class LinkDatabase:
    def __init__(self, db_path: str = "reddit_links.db"):
        """
        Initialize the link database
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections with proper cleanup"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def _init_database(self):
        """Create the database tables if they don't exist"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Reddit to Discord username mappings (one Discord ID can have multiple Reddit usernames)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reddit_discord_links (
                    reddit_username TEXT PRIMARY KEY,
                    discord_user_id TEXT NOT NULL,
                    linked_by TEXT,
                    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Message mappings for retroactive editing
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_winners (
                    message_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL,
                    reddit_usernames TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Index for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_discord_user_id 
                ON reddit_discord_links(discord_user_id)
            """)
            
            logger.info(f"Link database initialized at {self.db_path}")
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def add_link(self, reddit_username: str, discord_user_id: str, linked_by: str = None) -> bool:
        """
        Add or update a Reddit to Discord username link
        
        Args:
            reddit_username: Reddit username to link
            discord_user_id: Discord user ID to link to
            linked_by: Discord user ID of who created the link (optional)
            
        Returns:
            True if successful
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Normalize reddit username to lowercase
            reddit_username = reddit_username.lower()
            
            cursor.execute("""
                INSERT OR REPLACE INTO reddit_discord_links 
                (reddit_username, discord_user_id, linked_by, linked_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (reddit_username, discord_user_id, linked_by))
            
            logger.info(f"Linked Reddit u/{reddit_username} to Discord <@{discord_user_id}>")
            return True
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def get_discord_id(self, reddit_username: str) -> Optional[str]:
        """
        Get Discord user ID for a Reddit username
        
        Args:
            reddit_username: Reddit username to look up
            
        Returns:
            Discord user ID if found, None otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Normalize to lowercase
            reddit_username = reddit_username.lower()
            
            cursor.execute("""
                SELECT discord_user_id FROM reddit_discord_links 
                WHERE reddit_username = ?
            """, (reddit_username,))
            
            result = cursor.fetchone()
            
            return result[0] if result else None
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def get_reddit_usernames(self, discord_user_id: str) -> List[str]:
        """
        Get all Reddit usernames linked to a Discord user ID
        
        Args:
            discord_user_id: Discord user ID to look up
            
        Returns:
            List of Reddit usernames
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT reddit_username FROM reddit_discord_links 
                WHERE discord_user_id = ?
            """, (discord_user_id,))
            
            results = cursor.fetchall()
            
            return [row[0] for row in results]
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def remove_link(self, reddit_username: str) -> bool:
        """
        Remove a Reddit to Discord link
        
        Args:
            reddit_username: Reddit username to unlink
            
        Returns:
            True if successful
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            reddit_username = reddit_username.lower()
            
            cursor.execute("""
                DELETE FROM reddit_discord_links 
                WHERE reddit_username = ?
            """, (reddit_username,))
            
            logger.info(f"Removed link for Reddit u/{reddit_username}")
            return True
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def store_message_mapping(self, message_id: int, channel_id: int, reddit_usernames: List[str]):
        """
        Store mapping of message ID to winners for retroactive editing
        
        Args:
            message_id: Discord message ID
            channel_id: Discord channel ID
            reddit_usernames: List of Reddit usernames who won
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Store as JSON array
            usernames_json = json.dumps(reddit_usernames)
            
            cursor.execute("""
                INSERT OR REPLACE INTO message_winners 
                (message_id, channel_id, reddit_usernames)
                VALUES (?, ?, ?)
            """, (message_id, channel_id, usernames_json))
            
            logger.debug(f"Stored message mapping for message {message_id}")
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def get_message_mapping(self, message_id: int) -> Optional[Dict]:
        """
        Get message mapping data
        
        Args:
            message_id: Discord message ID to look up
            
        Returns:
            Dictionary with channel_id and reddit_usernames, or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT channel_id, reddit_usernames FROM message_winners 
                WHERE message_id = ?
            """, (message_id,))
            
            result = cursor.fetchone()
            
            if result:
                return {
                    'channel_id': result[0],
                    'reddit_usernames': json.loads(result[1])
                }
            return None
    
    @retry_on_db_error(max_retries=3, delay=0.1)
    def get_all_links(self) -> List[tuple]:
        """
        Get all Reddit to Discord links
        
        Returns:
            List of tuples (reddit_username, discord_user_id, linked_at)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT reddit_username, discord_user_id, linked_at 
                FROM reddit_discord_links 
                ORDER BY linked_at DESC
            """)
            
            results = cursor.fetchall()
            
            return results
