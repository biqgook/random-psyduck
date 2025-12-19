import asyncpraw
import logging
from typing import Optional, Dict
import re
import aiohttp

logger = logging.getLogger('GloveAndHisBoy')


class RedditManager:
    def __init__(self, client_id: str, client_secret: str, user_agent: str, 
                 username: str, password: str):
        """
        Initialize Reddit API client
        
        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string
            username: Reddit username
            password: Reddit password
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.username = username
        self.password = password
        self.reddit = None
        logger.info("Reddit API manager initialized")
    
    async def _ensure_reddit(self):
        """Ensure Reddit client is initialized"""
        if self.reddit is None:
            self.reddit = asyncpraw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
                username=self.username,
                password=self.password,
                requestor_kwargs={"session": None}  # Let asyncpraw manage sessions
            )
            logger.info("Reddit API client connected")
    
    def extract_post_id(self, url: str) -> Optional[str]:
        """
        Extract Reddit post ID from URL
        
        Args:
            url: Reddit post URL
            
        Returns:
            Post ID or None if invalid
        """
        # Match various Reddit URL formats
        patterns = [
            r'reddit\.com/r/\w+/comments/(\w+)',
            r'redd\.it/(\w+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    async def get_post_info(self, url: str) -> Optional[Dict]:
        """
        Get post information from Reddit URL
        
        Args:
            url: Reddit post URL (supports various formats including mobile/share links)
            
        Returns:
            Dictionary with post info or None if error
        """
        try:
            # Ensure Reddit client is initialized
            await self._ensure_reddit()
            
            # Clean and normalize the URL to handle mobile/share links
            # Convert share links (reddit.com/r/sub/s/xyz) to proper format
            # Convert mobile links (m.reddit.com, i.reddit.com) to www.reddit.com
            clean_url = url.replace('m.reddit.com', 'reddit.com')
            clean_url = clean_url.replace('i.reddit.com', 'reddit.com')
            clean_url = clean_url.replace('www.reddit.com', 'reddit.com')
            
            # Handle share links - they redirect, so we can pass them directly
            # asyncpraw will follow the redirect
            
            logger.info(f"Fetching Reddit post from: {clean_url}")
            
            # Get the submission and load all attributes
            submission = await self.reddit.submission(url=clean_url)
            await submission.load()
            
            # Get the first image URL
            image_url = None
            
            logger.info(f"Fetching Reddit post - checking for images...")
            
            # For gallery posts, get the FIRST image only from gallery_data order
            if hasattr(submission, 'is_gallery') and submission.is_gallery:
                logger.info("Post is a gallery, fetching first image...")
                
                # Use gallery_data for correct ordering
                if hasattr(submission, 'gallery_data') and submission.gallery_data:
                    gallery_items = submission.gallery_data.get('items', [])
                    if gallery_items and hasattr(submission, 'media_metadata'):
                        # Get the first item's media_id from gallery_data (this preserves order)
                        first_media_id = gallery_items[0]['media_id']
                        item = submission.media_metadata.get(first_media_id)
                        
                        if item and item.get('e') == 'Image' and 's' in item:
                            image_url = item['s'].get('u') or item['s'].get('gif')
                            if image_url:
                                # Decode HTML entities
                                image_url = image_url.replace('&amp;', '&')
                                logger.info(f"Found first gallery image (from gallery_data): {image_url[:100]}")
                
                # Fallback: if gallery_data didn't work, try media_metadata keys
                if not image_url and hasattr(submission, 'media_metadata') and submission.media_metadata:
                    first_item_id = list(submission.media_metadata.keys())[0]
                    item = submission.media_metadata[first_item_id]
                    if item.get('e') == 'Image' and 's' in item:
                        image_url = item['s'].get('u') or item['s'].get('gif')
                        if image_url:
                            image_url = image_url.replace('&amp;', '&')
                            logger.info(f"Found first gallery image (from media_metadata): {image_url[:100]}")
            
            # Only check non-gallery sources if it's NOT a gallery post
            if not image_url and not (hasattr(submission, 'is_gallery') and submission.is_gallery):
                # Check if it's a direct image post
                if hasattr(submission, 'url') and submission.url:
                    if any(submission.url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                        image_url = submission.url
                        logger.info(f"Found direct image: {image_url[:100]}")
                
                # Check preview images as fallback for non-gallery posts
                if not image_url and hasattr(submission, 'preview') and submission.preview:
                    if 'images' in submission.preview and len(submission.preview['images']) > 0:
                        image_url = submission.preview['images'][0]['source']['url']
                        image_url = image_url.replace('&amp;', '&')
                        logger.info(f"Found preview image: {image_url[:100]}")
            
            if not image_url:
                logger.warning("No image found for Reddit post")
            
            # Parse spot assignments from selftext
            # First check if there's an external slot list link
            external_slot_url = self._extract_external_slot_url(submission.selftext)
            if external_slot_url:
                logger.info(f"Found external slot list URL: {external_slot_url}")
                external_content = await self._fetch_external_slot_list(external_slot_url)
                if external_content:
                    spot_assignments, user_spot_counts = self._parse_spot_assignments(external_content)
                    logger.info(f"Parsed {len(spot_assignments)} spots from external slot list")
                else:
                    # Don't fallback to post body - if external URL exists, spots won't be in description
                    logger.error("Failed to fetch external slot list - returning empty assignments")
                    spot_assignments, user_spot_counts = {}, {}
            else:
                # No external URL found, parse from post body as normal
                spot_assignments, user_spot_counts = self._parse_spot_assignments(submission.selftext)
            
            result = {
                'title': submission.title,
                'author': str(submission.author),
                'author_url': f"https://reddit.com/u/{submission.author}",
                'url': f"https://reddit.com{submission.permalink}",
                'image_url': image_url,
                'subreddit': str(submission.subreddit),
                'spot_assignments': spot_assignments,
                'user_spot_counts': user_spot_counts
            }
            
            logger.info(f"Reddit info fetched - Author: {result['author']}, Image: {bool(image_url)}, Spots parsed: {len(spot_assignments)}")
            return result
            
        except Exception as e:
            # Check for specific errors and log appropriately
            error_msg = str(e)
            if '404' in error_msg or 'NotFound' in str(type(e)):
                logger.error(f"Reddit post not found (404): {url}")
            elif '403' in error_msg or 'Forbidden' in str(type(e)):
                logger.error(f"Reddit post access forbidden (403): {url}")
            else:
                logger.error(f"Error fetching Reddit post: {error_msg}")
            return None
    
    def _extract_external_slot_url(self, selftext: str) -> Optional[str]:
        """
        Extract external slot list URL from post body
        
        Args:
            selftext: The body text of the Reddit post
            
        Returns:
            URL to external slot list or None if not found
        """
        # Look for Firebase storage URLs (edc-raffle-tool)
        # Example: https://firebasestorage.googleapis.com/v0/b/edc-raffle-tool.appspot.com/o/slot_lists%2Ft3_1pp8019?alt=media&token=...
        firebase_pattern = r'(https://firebasestorage\.googleapis\.com/[^\s\)]+)'
        match = re.search(firebase_pattern, selftext)
        if match:
            return match.group(1)
        
        # Look for other common patterns like "slot list can be found here" with a link
        link_pattern = r'can be found \[here\]\((https?://[^\)]+)\)'
        match = re.search(link_pattern, selftext)
        if match:
            return match.group(1)
        
        return None
    
    async def _fetch_external_slot_list(self, url: str) -> Optional[str]:
        """
        Fetch content from external slot list URL
        
        Args:
            url: URL to fetch
            
        Returns:
            Text content of the slot list or None if error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        content = await response.text()
                        logger.info(f"Successfully fetched external slot list ({len(content)} chars)")
                        return content
                    else:
                        logger.error(f"Failed to fetch external slot list: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.exception(f"Error fetching external slot list from {url}: {e}")
            return None
    
    def _parse_spot_assignments(self, selftext: str) -> tuple:
        """
        Parse spot assignments from Reddit post text
        
        Args:
            selftext: The body text of the Reddit post
            
        Returns:
            Tuple of (spot_assignments dict, user_spot_counts dict)
            - spot_assignments: Dictionary mapping spot numbers to usernames
            - user_spot_counts: Dictionary mapping usernames to their total spot count
        """
        spot_assignments = {}
        user_spot_counts = {}
        
        # Pattern matches various formats:
        # "1 /u/username **PAID**"
        # "1 u/username PAID"
        # "1 /u/username"
        # "461 u/Main-Complaint-9574 PAID"
        # Usernames can contain letters, numbers, hyphens, and underscores
        pattern = r'^(\d+)\s+/?u/([\w\-]+)(?:\s+\*?\*?PAID\*?\*?)?'
        
        lines = selftext.split('\n')
        for line in lines:
            match = re.match(pattern, line.strip(), re.IGNORECASE)
            if match:
                spot_number = int(match.group(1))
                username = match.group(2)
                spot_assignments[spot_number] = username
                
                # Count spots per user
                if username in user_spot_counts:
                    user_spot_counts[username] += 1
                else:
                    user_spot_counts[username] = 1
        
        if len(spot_assignments) == 0:
            logger.warning(f"No spot assignments found in Reddit post. Post may not have participant list yet.")
            logger.debug(f"First 500 chars of post body: {selftext[:500] if selftext else 'EMPTY'}")
        else:
            logger.info(f"Parsed {len(spot_assignments)} spot assignments from post")
        
        return spot_assignments, user_spot_counts
    
    async def close(self):
        """Close the Reddit client"""
        if self.reddit:
            await self.reddit.close()
            logger.info("Reddit client closed")
