"""
Database module for storing verification data
"""

import sqlite3
import json
import logging
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger('GloveAndHisBoy')


class VerificationDatabase:
    def __init__(self, db_path: str = "verification_data.db"):
        """
        Initialize the verification database
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Create the database table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create table with all columns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_data (
                message_id INTEGER PRIMARY KEY,
                verification_random TEXT NOT NULL,
                signature TEXT NOT NULL,
                numbers TEXT NOT NULL,
                reddit_info TEXT,
                timestamp TEXT,
                total_spots INTEGER,
                caller_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migration: Add new columns if they don't exist (for existing databases)
        try:
            # Check if reddit_info column exists
            cursor.execute("PRAGMA table_info(verification_data)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Add missing columns
            if 'reddit_info' not in columns:
                cursor.execute("ALTER TABLE verification_data ADD COLUMN reddit_info TEXT")
                logger.info("Added reddit_info column to database")
            
            if 'timestamp' not in columns:
                cursor.execute("ALTER TABLE verification_data ADD COLUMN timestamp TEXT")
                logger.info("Added timestamp column to database")
            
            if 'total_spots' not in columns:
                cursor.execute("ALTER TABLE verification_data ADD COLUMN total_spots INTEGER")
                logger.info("Added total_spots column to database")
            
            if 'caller_name' not in columns:
                cursor.execute("ALTER TABLE verification_data ADD COLUMN caller_name TEXT")
                logger.info("Added caller_name column to database")
                
        except Exception as e:
            logger.warning(f"Could not migrate database schema: {e}")
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def store_verification(self, message_id: int, verification_random: str, 
                          signature: str, numbers: list, reddit_info: dict = None,
                          timestamp: str = None, total_spots: int = None, caller_name: str = None):
        """
        Store verification data for a message
        
        Args:
            message_id: Discord message ID
            verification_random: JSON verification data
            signature: Cryptographic signature
            numbers: List of winning numbers
            reddit_info: Reddit post information
            timestamp: Timestamp of the call
            total_spots: Total number of spots
            caller_name: Name of user who called the command
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO verification_data 
                (message_id, verification_random, signature, numbers, reddit_info, timestamp, total_spots, caller_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (message_id, verification_random, signature, json.dumps(numbers), 
                   json.dumps(reddit_info) if reddit_info else None, timestamp, total_spots, caller_name))
            
            conn.commit()
            conn.close()
            logger.info(f"Stored verification data for message {message_id}")
            
        except Exception as e:
            logger.exception(f"Error storing verification data: {e}")
    
    def get_verification(self, message_id: int) -> Optional[Dict]:
        """
        Retrieve verification data for a message
        
        Args:
            message_id: Discord message ID
            
        Returns:
            Dictionary with verification data or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT verification_random, signature, numbers, reddit_info, timestamp, total_spots, caller_name
                FROM verification_data
                WHERE message_id = ?
            """, (message_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'verification_random': row[0],
                    'signature': row[1],
                    'numbers': json.loads(row[2]),
                    'reddit_info': json.loads(row[3]) if row[3] else None,
                    'timestamp': row[4],
                    'total_spots': row[5],
                    'caller_name': row[6]
                }
            return None
            
        except Exception as e:
            logger.exception(f"Error retrieving verification data: {e}")
            return None
    
    def cleanup_all_records(self) -> int:
        """
        Delete all verification data from database (admin command only)
        
        Returns:
            Number of records deleted
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM verification_data")
            count = cursor.fetchone()[0]
            
            cursor.execute("DELETE FROM verification_data")
            
            conn.commit()
            conn.close()
            
            logger.info(f"Manual cleanup: Deleted all {count} verification records")
            return count
            
        except Exception as e:
            logger.exception(f"Error during manual cleanup: {e}")
            raise
