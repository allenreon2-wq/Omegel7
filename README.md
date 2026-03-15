# 🤖 Anonymous Chat Bot — Telegram

A **premium-grade Telegram anonymous chat bot** built with Python & Pyrogram.
Meet random strangers, chat privately, and stay anonymous — like Omegle, but on Telegram.

---

## ✨ Features

### Core
| Feature | Status |
|---|---|
| Anonymous random chat | ✅ |
| Text / Photo / Video / Voice / Sticker / Document relay | ✅ |
| Typing indicator relay | ✅ |
| Auto-reconnect on partner leave | ✅ |
| Prevent re-matching same users | ✅ |

### Matching
| Feature | Status |
|---|---|
| Smart queue with priority scoring | ✅ |
| Gender filter (male / female / random) | ✅ |
| Interest matching | ✅ |
| Country matching | ✅ |
| Instant match when someone is available | ✅ |
| Queue timeout (120s) | ✅ |

### Safety & Moderation
| Feature | Status |
|---|---|
| Flood control (10 msg / 10s) | ✅ |
| Bad-word auto-moderation | ✅ |
| Karma / reputation system | ✅ |
| User block system | ✅ |
| Report system | ✅ |
| Auto-ban after 5 reports | ✅ |

### Admin Panel
| Command | Description |
|---|---|
| `/ban <id> [reason]` | Ban a user |
| `/unban <id>` | Unban a user |
| `/stats` | Bot statistics |
| `/broadcast <msg>` | Message all users |
| `/users` | User list + ban history |
| `/reports [id]` | View reports |

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/yourname/anonymous-chat-bot
cd anonymous-chat-bot
pip install -r requirements.txt
```

### 2. Get credentials

| Credential | Where to get |
|---|---|
| `API_ID` & `API_HASH` | https://my.telegram.org |
| `BOT_TOKEN` | [@BotFather](https://t.me/BotFather) on Telegram |

### 3. Configure

Edit `config.py` **or** set environment variables:

```bash
export BOT_TOKEN="your_bot_token"
export API_ID="your_api_id"
export API_HASH="your_api_hash"
export ADMIN_IDS="123456789"   # comma-separated for multiple admins
```

### 4. Run

```bash
python bot.py
```

---

## 📁 Project Structure

```
anonymous-chat-bot/
├── bot.py              # Main entry point, all user handlers
├── config.py           # All configuration & secrets
├── database.py         # Full async SQLite layer
├── handlers/
│   ├── __init__.py
│   ├── matching.py     # MatchMaker engine, FloodGuard, Moderator
│   └── admin.py        # Admin panel commands
├── badwords.txt        # Moderation word list (one per line)
├── requirements.txt
└── README.md
```

---

## ☁️ 24/7 Cloud Deployment

### Railway (recommended — free tier)

1. Push code to GitHub
2. Connect repo at https://railway.app
3. Set environment variables in the Railway dashboard
4. Deploy — Railway auto-restarts on crashes

### Render

1. Create a new **Web Service** (or Background Worker)
2. Build command: `pip install -r requirements.txt`
3. Start command: `python bot.py`
4. Set env vars in the Render dashboard

### VPS (Ubuntu)

```bash
# Install dependencies
sudo apt update && sudo apt install python3-pip screen -y
pip3 install -r requirements.txt

# Run in background with screen
screen -S chatbot
python3 bot.py
# Ctrl+A then D to detach
```

### Systemd service (recommended for VPS)

```ini
# /etc/systemd/system/chatbot.service
[Unit]
Description=Anonymous Chat Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/anonymous-chat-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=5
Environment=BOT_TOKEN=your_token
Environment=API_ID=your_api_id
Environment=API_HASH=your_api_hash
Environment=ADMIN_IDS=your_admin_id

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable chatbot
sudo systemctl start chatbot
sudo systemctl status chatbot
```

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | BotFather token |
| `API_ID` | — | Telegram API ID |
| `API_HASH` | — | Telegram API Hash |
| `ADMIN_IDS` | — | Comma-separated admin user IDs |
| `DB_PATH` | `data/chatbot.db` | SQLite database path |
| `FLOOD_LIMIT` | `10` | Max messages per window |
| `FLOOD_WINDOW` | `10` | Flood window in seconds |
| `REPORT_BAN_THRESHOLD` | `5` | Reports before auto-ban |
| `QUEUE_TIMEOUT` | `120` | Seconds before queue expiry |
| `MIN_KARMA_TO_CHAT` | `-50` | Karma threshold (soft ban) |

---

## 🗄️ Database Schema

- **users** — profiles, gender, interests, karma, ban status
- **active_chats** — live connections between user pairs
- **chat_history** — archived completed chats
- **banned_users** — ban log with reason & admin
- **reports** — report log for moderation
- **blocked_pairs** — mutual block pairs
- **statistics** — global counters

---

## 📄 License

MIT — free to use, modify, and deploy.
