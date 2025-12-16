"""
Random.org API integration with key rotation and request tracking
"""

import json
import requests
import uuid
import logging
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional, Dict
import config

logger = logging.getLogger('GloveAndHisBoy')


class RandomOrgManager:
    def __init__(self, api_keys: list):
        """
        Initialize the Random.org manager with rotating API keys
        
        Args:
            api_keys: List of Random.org API keys to rotate through
        """
        self.api_keys = api_keys
        self.current_key_index = 0
        self.request_counts = {key: 0 for key in api_keys}
        self.last_reset = datetime.now(timezone.utc)
        
    def _check_reset_needed(self):
        """Check if we need to reset the daily counters (at 4 AM EST / 9 AM UTC)"""
        now = datetime.now(timezone.utc)
        
        # Calculate today's reset time
        reset_time_today = now.replace(hour=config.RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
        
        # If we've passed today's reset time and last reset was before it
        if now >= reset_time_today and self.last_reset < reset_time_today:
            # Reset all counters
            self.request_counts = {key: 0 for key in self.api_keys}
            self.last_reset = now
            logger.info(f"Reset API request counters at {now}")
    
    def _get_next_api_key(self) -> str:
        """Get the next API key in rotation"""
        self._check_reset_needed()
        
        # Rotate to next key
        api_key = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        
        return api_key
    
    def get_total_requests(self) -> Tuple[int, int]:
        """
        Get total requests made and the limit (per key)
        
        Returns:
            Tuple of (current_requests, limit_per_key)
        """
        self._check_reset_needed()
        total = sum(self.request_counts.values())
        return (total, config.API_REQUEST_LIMIT)
    
    async def generate_random_numbers(self, count: int, max_value: int) -> Optional[Dict]:
        """
        Generate random numbers using Random.org API with retry mechanism
        Will retry every 5 minutes if the API is down or fails
        
        Args:
            count: Number of random integers to generate
            max_value: Maximum value (1 to max_value range)
            
        Returns:
            Dictionary containing random data and verification info
        """
        retry_delay = config.API_RETRY_DELAY
        attempt = 0
        
        while True:
            attempt += 1
            api_key = self._get_next_api_key()
            
            request_data = {
                'jsonrpc': '2.0',
                'method': 'generateSignedIntegers',
                'params': {
                    'apiKey': api_key,
                    'n': count,
                    'min': 1,
                    'max': max_value,
                    'replacement': False  # Don't repeat numbers
                },
                'id': uuid.uuid4().hex
            }
            
            try:
                response = requests.post(
                    config.RANDOM_ORG_API_URL,
                    data=json.dumps(request_data),
                    headers={'content-type': 'application/json'},
                    timeout=30.0
                )
                
                response_data = response.json()
                
                if response_data and 'result' in response_data:
                    # Increment counter for this key
                    self.request_counts[api_key] = self.request_counts.get(api_key, 0) + 1
                    
                    if attempt > 1:
                        logger.info(f"Successfully generated numbers after {attempt} attempts")
                    logger.info(f"Generated {count} random number(s) from 1-{max_value}")
                    return response_data['result']
                else:
                    logger.warning(f"Invalid response from Random.org (attempt {attempt}): {response_data}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout calling Random.org API (attempt {attempt})")
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error to Random.org (attempt {attempt})")
            except Exception as e:
                logger.warning(f"Error calling Random.org API (attempt {attempt}): {e}")
            
            # Wait 5 minutes before retrying
            logger.info(f"Random.org API unavailable. Waiting {retry_delay} seconds before retry...")
            await asyncio.sleep(retry_delay)
    
    def format_verification_data(self, random_dict: dict) -> str:
        """
        Format the random data for verification
        
        Args:
            random_dict: The 'random' portion of the API response
            
        Returns:
            Formatted JSON string for verification
        """
        return json.dumps({
            "method": "generateSignedIntegers",
            "hashedApiKey": random_dict['hashedApiKey'],
            "n": random_dict['n'],
            "min": random_dict['min'],
            "max": random_dict['max'],
            "replacement": random_dict['replacement'],
            "base": random_dict['base'],
            "data": random_dict['data'],
            "completionTime": random_dict['completionTime'],
            "serialNumber": random_dict['serialNumber']
        }, indent=2)
