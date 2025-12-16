"""
Configuration settings for GloveAndHisBoy Discord Bot
"""

# Discord Configuration
ALLOWED_CHANNEL_ID = 1450311167452123207 # PR botcalls
ROLL_LOG_CHANNEL_ID = 1450342934573617353  # PR roll-log

LR_ALLOWED_CHANNEL_ID = 1450497852269924536 # LR botcalls
LR_ROLL_LOG_CHANNEL_ID = 1450497935484653689  # LR roll-log

ADMIN_USER_ID = 975054002431606844  # User who can run admin commands

# Random.org Configuration
RANDOM_ORG_API_URL = 'https://api.random.org/json-rpc/1/invoke'
API_REQUEST_LIMIT = 4000  # Daily limit per API key
API_RETRY_DELAY = 300  # Seconds to wait before retrying failed API calls (5 minutes)

# API Reset Time (4 AM EST = 9 AM UTC)
RESET_HOUR_UTC = 9

# Bot Configuration
VERSION = '1.0.0'
BOT_NAME = 'GloveAndHisBoy'
COMMAND_QUEUE_DELAY = 5  # Seconds between queued commands

# Embed Colors
EMBED_COLOR = 0x00FF00  # Green - you can change this to any hex color
