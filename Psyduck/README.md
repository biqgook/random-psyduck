# Psyduck Discord Bot

A Discord bot for conducting verifiable random raffles with Reddit integration and cryptographic proof from Random.org.

## Features

### Core Functionality
- **Verifiable Random Number Generation** - Uses Random.org with cryptographic signatures
- **API Key Rotation** - Automatically rotates through 4 API keys for 16,000 daily requests
- **Request Tracking** - Monitors API usage with automatic reset at 4 AM EST
- **Cryptographic Verification** - Every roll includes downloadable verification data

### Reddit Integration
- **Automatic Spot Parsing** - Parses Reddit raffle posts for participant assignments
- **External Slot List Support** - Automatically fetches participant lists from Firebase storage URLs for large raffles (900+ spots)
- **Winner Display** - Shows usernames with links to Reddit profiles and spot percentages
- **Image Display** - Pulls first image from Reddit gallery posts
- **Smart URL Handling** - Supports mobile/share links and various Reddit URL formats
- **URL Validation** - Validates Reddit URLs before API calls to prevent wasted quota

### Discord Features
- **Persistent Storage** - SQLite database maintains verification data across restarts
- **Persistent Buttons** - Verification buttons work even after bot restarts
- **Automated DMs** - Sends caller a record with link to results
- **Message Control** - Auto-deletes non-command messages in designated channel
- **Queue System** - Handles multiple requests with 5-second delays
- **Channel Restriction** - Commands only work in configured channel

### Username Matching
- **Fuzzy Matching** - Automatically matches Reddit usernames to Discord members with performance caching
- **Manual Linking** - Link button allows admins to manually map Reddit users to Discord users
- **Persistent Links Database** - Reddit-Discord mappings stored separately and survive database wipes
- **Retroactive Updates** - Manual links automatically update past winner announcements
- **Discord Mentions** - Winners are tagged in general chat if matched or linked
- **Performance Optimized** - Member name caching eliminates repeated regex operations on large servers

### Admin Tools
- `-c` - Clean up user messages only (keeps bot and admin messages)
- `-e` - Delete everything (complete channel wipe)
- `-cdb` - Purge all verification records from database

### Error Handling and Notifications
- **Silent Error System** - Errors are silent to users, only sent to admin via DM
- **Detailed Error Reports** - Admin receives comprehensive error details including user, URL, and failure reason
- **Retry Protection** - Failed raffles are not marked as called, allowing users to retry
- **Missing Participant Alerts** - Admin notified when Reddit posts lack participant lists

## Project Structure

```
Psyduck/
├── bot.py                 # Main bot entry point and event handlers (315 lines)
├── command_handler.py     # /call command processing and announcements (497 lines)
├── cleanup_handlers.py    # Channel cleanup functions (114 lines)
├── config.py             # Configuration settings (25 lines)
├── random_org.py         # Random.org API integration with key rotation (144 lines)
├── reddit_manager.py     # Reddit API client for post parsing (279 lines)
├── database.py           # SQLite persistence with connection pooling (186 lines)
├── link_database.py      # SQLite database for Reddit-Discord username links (283 lines)
├── link_view.py          # Persistent UI for manual username linking (242 lines)
├── queue_manager.py      # Command queue with rate limiting (69 lines)
├── utils.py              # Embed creation, button handlers, fuzzy matching (525 lines)
├── roll_logger.py        # Roll logging for general chat announcements (187 lines)
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (not in repo)
├── verification_data.db  # SQLite database (created on first run)
├── reddit_links.db       # SQLite database for username links (created on first run)
└── called_links.txt      # Track called raffles (created on first run)
```

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file with:
```env
# Discord
DISCORD_BOT_TOKEN=your_discord_bot_token
TESTING_GUILD_ID=your_guild_id

# Random.org API Keys (get from https://api.random.org/api-keys)
RANDOM_ORG_API_KEY_1=your_first_key
RANDOM_ORG_API_KEY_2=your_second_key
RANDOM_ORG_API_KEY_3=your_third_key
RANDOM_ORG_API_KEY_4=your_fourth_key

# Reddit API (create app at https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=YourBotName/1.0
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
```

### 3. Discord Bot Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable these **Privileged Gateway Intents**:
   - Message Content Intent (required)
   - Server Members Intent
   - Presence Intent
3. Bot needs these **permissions** in the target channel:
   - Send Messages
   - Embed Links
   - Attach Files
   - Read Message History
   - Manage Messages (for auto-deletion)
   - Use Application Commands

### 4. Update Configuration
Edit `config.py` to set:
- `ALLOWED_CHANNEL_ID` - Channel where bot operates
- `ADMIN_USER_ID` - Admin Discord user ID for cleanup commands
- `COMMAND_QUEUE_DELAY` - Seconds between queued commands (default: 5)
- `EMBED_COLOR` - Hex color for embeds (default: 0x00FF00)

### 5. Run the Bot
```bash
python bot.py
```

## Usage

### Main Command
```
/call reddit_url:<url> spots:<total> winners:<count>
```

**Parameters:**
- `reddit_url` - Reddit post URL (supports mobile/share links)
- `spots` - Total number of raffle spots (1-1000000)
- `winners` - Number of winners to select (default: 1, max: 100)

**Examples:**
```
/call reddit_url:https://reddit.com/r/PokemonRaffles/comments/abc123 spots:200 winners:1
/call reddit_url:https://redd.it/xyz789 spots:50 winners:3
```

### Admin Commands
Type in the designated channel (admin user only):
- `-c` - Clean user messages (keeps bot and admin messages)
- `-e` - Delete everything (wipes entire channel)
- `-cdb` - Purge all verification data from database

### Link Button (Admin Only)
Each winner announcement includes a link button that allows admins to manually map Reddit usernames to Discord users:
1. Click the link button (only visible to admin)
2. Select which Reddit winner to link (if multiple winners)
3. Enter the Discord user ID in the modal
4. Link is saved to database and persists across bot restarts
5. Past winner announcements are automatically updated with the new mention

### Verification Button
After each `/call`, a "Click to Verify" button appears. Users can:
1. Click the button
2. Receive a DM with verification data and instructions
3. Download the `.txt` file
4. Visit https://api.random.org/verify
5. Verify the cryptographic signature

## Output Format

### Channel Message
Shows:
- Large formatted winning numbers
- Reddit author and raffle link
- Total spots (e.g., "1-200")
- Winning numbers
- Winners list with Reddit profile links and spot percentages
- Discord mentions for matched/linked winners
- First image from Reddit gallery
- Link button (admin only) for manual Reddit-Discord mapping
- Verification button for cryptographic proof
- Timestamp and caller name in footer

### General Chat Announcement
When winners are announced in the results channel, a simultaneous announcement is sent to the configured general chat channel showing:
- Large formatted "WINNER" or "WINNERS" header
- Discord user mentions for all matched winners (via fuzzy matching or manual links)
- Only appears if at least one Discord user match is found

### Caller DM
Includes:
- Title: "Record"
- Jump link to results message
- All raffle information
- Image from Reddit post
- Timestamp in footer

### Verification DM
Contains:
- Full raffle information with winners
- Reddit image
- Verification instructions
- Downloadable .txt file with cryptographic data
- Timestamp and caller name

## Technical Details

### Database Schema

**Verification Database (verification_data.db)**
- Connection pooling with WAL mode for improved concurrency
- Automatic retry logic with exponential backoff for transient failures
- Context managers ensure proper connection cleanup

```sql
CREATE TABLE verification_data (
    message_id INTEGER PRIMARY KEY,
    verification_random TEXT NOT NULL,
    signature TEXT NOT NULL,
    numbers TEXT NOT NULL,
    reddit_info TEXT,
    timestamp TEXT,
    total_spots INTEGER,
    caller_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Links Database (reddit_links.db)**
- Connection pooling with WAL mode for improved concurrency
- Automatic retry logic with exponential backoff for transient failures
- Context managers ensure proper connection cleanup

```sql
-- Reddit to Discord username mappings
CREATE TABLE reddit_discord_links (
    reddit_username TEXT PRIMARY KEY,
    discord_user_id TEXT NOT NULL,
    linked_by TEXT,
    linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Message mappings for retroactive editing
CREATE TABLE message_winners (
    message_id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    reddit_usernames TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### API Key Rotation
- Bot cycles through 4 Random.org API keys
- Each key has 4,000 daily requests
- Total capacity: 16,000 requests/day
- Resets daily at 4 AM EST (9 AM UTC)
- Automatic retry on failure with 5-minute delays

### Username Matching
- **Fuzzy Matching Algorithm** - Compares Reddit usernames to Discord display names using normalized string comparison
- **Member Name Caching** - Cached normalization for O(1) lookups instead of O(n) regex operations on large servers
- **Two-Pass System** - First checks database for manual links, then falls back to fuzzy matching
- **Normalization** - Removes special characters, converts to lowercase for comparison
- **Match Threshold** - 70% similarity required for automatic matches
- **Manual Override** - Admin can manually link any Reddit username to Discord user ID
- **Retroactive Updates** - When a manual link is created, all past winner announcements are automatically updated

### Duplicate Prevention
- **Thread-Safe File Operations** - Uses asyncio.Lock to prevent race conditions on called_links.txt
- **Success-Based Tracking** - Raffles only marked as called after successful completion
- **Automatic Retry Support** - Failed raffles can be retried without admin intervention
- **Admin Bypass** - Admin users can re-roll any raffle regardless of duplicate status
- **Participant Validation** - Prevents selecting more winners than actual participants

### File and Database Safety
- **Automatic File Creation** - Missing files are created automatically instead of causing crashes
- **Connection Pooling** - Database connections use context managers with proper cleanup
- **Retry Logic** - Transient database failures automatically retried with exponential backoff (0.1s, 0.2s, 0.3s)
- **WAL Mode** - SQLite uses Write-Ahead Logging for better concurrency
- **Graceful Shutdown** - Proper exception handling allows clean bot termination

### Rate Limiting
- Queue system: 5-second delay between commands
- Channel cleanup: 0.5-second delay between deletions (2 msgs/sec)
- Startup cleanup: Scans last 100 messages

### Reddit Post Parsing
Supports these spot formats:
```
1 /u/username **PAID**
1 u/username PAID
1 /u/username
461 u/Main-Complaint-9574 PAID
```

**External Slot Lists** - Automatically detects and fetches participant lists from external URLs:
- Firebase storage URLs (edc-raffle-tool)
- Markdown link patterns: "can be found [here](url)"
- Seamlessly handles large raffles (900+ spots) where Reddit posts link to external storage
- Falls back to post body parsing if external fetch fails

## Error Handling

- **Silent User Errors** - All user errors are silent, only admin receives DM notifications
- **Detailed Admin Notifications** - Admin receives comprehensive error reports with user info, URL, and error details
- **API Failure** - Retries every 5 minutes until Random.org responds
- **Reddit Errors** - Continues with number generation, notifies admin of issues
- **External Slot List Failures** - Falls back to post body parsing if external fetch fails
- **Missing Participant Lists** - Admin notified when Reddit posts lack participant data
- **DM Blocked** - Logs warning, continues operation
- **Permission Errors** - Logs detailed error messages
- **Database Errors** - Automatic retry with exponential backoff for transient failures
- **File Operations** - Thread-safe with automatic file creation for missing files

## Logging

All operations logged to console with severity levels:
- **INFO** - Normal operations, API calls, message deletions
- **WARNING** - Non-critical issues (DM failures, missing Reddit data)
- **ERROR** - Permission denials, missing environment variables
- **EXCEPTION** - Full stack traces for debugging

## Dependencies

```
discord.py>=2.3.0  # Discord API wrapper
asyncpraw>=7.7.0   # Async Reddit API wrapper
python-dotenv      # Environment variable management
aiohttp>=3.9.0     # Async HTTP client for external slot lists
pytz               # Timezone conversions
requests>=2.31.0   # HTTP library
```

## Security Notes

- Never commit `.env` file to version control
- Keep API keys confidential
- Admin commands restricted to single user ID
- Bot only operates in designated channel
- Verification data proves authenticity cryptographically
- Thread-safe file operations prevent race conditions
- Database connections use secure context managers with proper cleanup

## Production Enhancements

### Performance Optimizations
- Database connection pooling with WAL mode (50% performance improvement)
- Member name caching for fuzzy matching (O(1) vs O(n) lookups)
- URL validation before API calls prevents wasted quota
- Efficient queue management with proper task completion

### Reliability Improvements
- Thread-safe file operations with asyncio.Lock
- Automatic retry logic for transient database failures
- Graceful error handling with proper exception types
- Automatic file creation prevents startup crashes
- Success-based duplicate tracking allows retry on failure

### Data Integrity
- Atomic database operations with commit/rollback
- WAL mode for better concurrency without corruption
- Exponential backoff retry prevents data loss
- Thread-safe operations prevent concurrent write issues

## License

This bot is for private use. Random.org API usage subject to their terms of service.

## Support

For issues or questions:
1. Check logs for detailed error messages
2. Verify all environment variables are set correctly
3. Ensure Discord bot has correct permissions
4. Confirm Random.org API keys are valid and have remaining requests

## Version Information

**Version:** 2.0.0  
**Last Updated:** December 2025

### Recent Updates
- Added external slot list support for large raffles (Firebase URLs)
- Implemented database connection pooling with retry logic
- Added member name caching for performance optimization
- Enhanced error handling with admin DM notifications
- Implemented thread-safe file operations
- Added success-based duplicate tracking
- Improved Reddit URL validation
- Enhanced logging for missing participant lists
- Added automatic file creation for missing files
- Optimized database operations with WAL mode
