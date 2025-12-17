# Discord Configuration
ALLOWED_CHANNEL_ID = 1450684659145904280 # PR botcalls
ROLL_LOG_CHANNEL_ID = 1450342934573617353  # PR roll-log
PR_GENERAL_CHAT = 1313637204018462855  # PR general chat for winner announcements

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
BOT_NAME = 'Psyduck'
COMMAND_QUEUE_DELAY = 5  # Seconds between queued commands

# Username Matching Configuration
MIN_MATCH_LENGTH = 5  # Minimum characters required for fuzzy username matching
MIN_MATCH_SCORE = 0.5  # Minimum similarity score (50%) for fuzzy matches

# Parameter Validation
MAX_SPOTS = 1000000  # Maximum number of spots allowed
MAX_WINNERS = 10000  # Maximum number of winners allowed

# Embed Colors
EMBED_COLOR = 0x00FF00  # Green - you can change this to any hex color
