# GloveAndHisBoy Discord Bot

A Discord bot for conducting verifiable random raffles with Reddit integration and cryptographic proof from Random.org.

## Features

### Core Functionality
- 🎲 **Verifiable Random Number Generation** - Uses Random.org with cryptographic signatures
- 🔄 **API Key Rotation** - Automatically rotates through 4 API keys for 16,000 daily requests
- 📊 **Request Tracking** - Monitors API usage with automatic reset at 4 AM EST
- 🔐 **Cryptographic Verification** - Every roll includes downloadable verification data

### Reddit Integration
- 📝 **Automatic Spot Parsing** - Parses Reddit raffle posts for participant assignments
- 👥 **Winner Display** - Shows usernames with links to Reddit profiles
- 🖼️ **Image Display** - Pulls first image from Reddit gallery posts
- 🔗 **Smart URL Handling** - Supports mobile/share links and various Reddit URL formats

### Discord Features
- 💾 **Persistent Storage** - SQLite database maintains verification data across restarts
- 🔘 **Persistent Buttons** - Verification buttons work even after bot restarts
- 📬 **Automated DMs** - Sends caller a record with link to results
- 🗑️ **Message Control** - Auto-deletes non-command messages in designated channel
- ⏱️ **Queue System** - Handles multiple requests with 5-second delays
- 🔒 **Channel Restriction** - Commands only work in configured channel

### Admin Tools
- `-c` - Clean up user messages only (keeps bot and admin messages)
- `-e` - Delete everything (complete channel wipe)
- `-cdb` - Purge all verification records from database

## Project Structure

```
GloveAndHisBoy/
├── bot.py                 # Main bot entry point and command handlers
├── config.py             # Configuration settings (channel IDs, colors, delays)
├── random_org.py         # Random.org API integration with key rotation
├── reddit_manager.py     # Reddit API client for post parsing
├── database.py           # SQLite persistence for verification data
├── queue_manager.py      # Command queue with rate limiting
├── utils.py              # Embed creation, button handlers, validation
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (not in repo)
└── verification_data.db  # SQLite database (created on first run)
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
   - ✅ Message Content Intent (required)
   - ✅ Server Members Intent
   - ✅ Presence Intent
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
- Winners list with Reddit profile links
- First image from Reddit gallery
- Timestamp and caller name in footer

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

### API Key Rotation
- Bot cycles through 4 Random.org API keys
- Each key has 4,000 daily requests
- Total capacity: 16,000 requests/day
- Resets daily at 4 AM EST (9 AM UTC)
- Automatic retry on failure with 5-minute delays

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
```

## Error Handling

- **API Failure**: Retries every 5 minutes until Random.org responds
- **Reddit Errors**: Continues with number generation, warns user
- **DM Blocked**: Logs warning, continues operation
- **Permission Errors**: Logs detailed error messages
- **Database Errors**: Catches and logs all DB exceptions

## Logging

All operations logged to console with:
- INFO: Normal operations, API calls, message deletions
- WARNING: Non-critical issues (DM failures, missing Reddit data)
- ERROR: Permission denials, missing environment variables
- EXCEPTION: Full stack traces for debugging

## Dependencies

```
discord.py>=2.3.0  # Discord API wrapper
asyncpraw>=7.7.0   # Async Reddit API wrapper
python-dotenv      # Environment variable management
aiohttp            # Async HTTP client
pytz               # Timezone conversions
```

## Security Notes

- Never commit `.env` file to version control
- Keep API keys confidential
- Admin commands restricted to single user ID
- Bot only operates in designated channel
- Verification data proves authenticity cryptographically

## License

This bot is for private use. Random.org API usage subject to their terms of service.

## Support

For issues or questions:
1. Check logs for detailed error messages
2. Verify all environment variables are set
3. Ensure Discord bot has correct permissions
4. Confirm Random.org API keys are valid

---

**Version:** 1.0.0  
**Last Updated:** December 2025
- `winners` - Number of winners to select (default: 1, max: 100)
/call reddit_url:https://reddit.com/r/WatchURaffle/comments/abc123 spots:100 winners:3
```

The `winners` parameter is optional and defaults to 1.

**Admin only - Cleanup database:**
```
Cleanup DB
```
Deletes all stored verification data (only works for admin user ID: 975054002431606844)

## Bot Response

The bot will reply with an embed containing:
- **Winning spot number(s)** displayed prominently
- **Author** of the Reddit post (clickable link to their profile)
- **Raffle Link** to the original Reddit post
- **First image from the Reddit post** (if available)
- **Button to receive verification data via DM**
- **API request counter** in the footer

## Project Structure

```
GloveAndHisBoy/
├── bot.py            # Main Discord bot file with slash commands
├── config.py         # Configuration settings
├── random_org.py     # Random.org API integration
├── reddit_manager.py # Reddit API integration
├── database.py       # SQLite database for verification data
├── utils.py          # Helper functions
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variables template
└── README.md         # This file
```

## How It Works

1. User runs `/call` slash command with Reddit URL, spot count, and optional winner count
2. Bot fetches Reddit post information (title, author, first image)
3. Parses command to extract number of winners and range
4. Rotates through API keys to make request to Random.org
5. Receives cryptographically signed random numbers
6. Stores verification data in SQLite database
7. Creates embed with winning numbers, Reddit info, and image
8. When button is clicked, retrieves data from database and DMs user
9. Tracks usage across all 4 API keys
10. Auto-resets counter at 4 AM EST daily
11. Verification data stored indefinitely until manual cleanup

## Verification

Users can verify results are authentic by:
1. Visiting https://api.random.org/verify
2. Copying the "Random" JSON from the embed
3. Copying the "Signature" from the embed
4. Pasting both into the verification page
5. Confirming the signature matches

This proves the numbers were genuinely random and not manipulated.
