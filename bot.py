# ============================================================
#   Anonymous Chat Bot — bot.py
#   Entry point — all user-facing handlers live here
# ============================================================

import asyncio
import logging
import sys
from typing import Optional

from pyrogram import Client, filters, idle
from pyrogram.enums import ChatAction, ParseMode
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)

from config import (
    API_ID, API_HASH, BOT_TOKEN, ADMIN_IDS,
    FLOOD_LIMIT, FLOOD_WINDOW, MIN_KARMA_TO_CHAT,
    BADWORDS_FILE
)
from database import Database
from handlers.matching import (
    matchmaker, flood_guard, moderator,
    QueueEntry
)
from handlers.admin import register_admin_handlers

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Global singletons ────────────────────────────────────────
db  = Database()
app = Client(
    "anon_chat_bot",
    api_id   = API_ID,
    api_hash = API_HASH,
    bot_token= BOT_TOKEN,
    parse_mode=ParseMode.MARKDOWN,
)


# ════════════════════════════════════════════════════════════
#  Keyboards
# ════════════════════════════════════════════════════════════
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Find Stranger", callback_data="find"),
            InlineKeyboardButton("❓ Help",           callback_data="help"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings",        callback_data="settings"),
            InlineKeyboardButton("📊 My Profile",      callback_data="profile"),
        ],
    ])


def kb_in_chat() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭ Next",       callback_data="next"),
            InlineKeyboardButton("🛑 Stop",       callback_data="stop"),
        ],
        [
            InlineKeyboardButton("🚩 Report",     callback_data="report"),
            InlineKeyboardButton("🚫 Block",      callback_data="block"),
        ],
    ])


def kb_gender() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Male",    callback_data="gender_male"),
            InlineKeyboardButton("👩 Female",  callback_data="gender_female"),
            InlineKeyboardButton("🎲 Random",  callback_data="gender_random"),
        ],
    ])


def kb_gender_filter() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Match Males",    callback_data="gf_male"),
            InlineKeyboardButton("👩 Match Females",  callback_data="gf_female"),
            InlineKeyboardButton("🎲 Anyone",         callback_data="gf_random"),
        ],
    ])


def kb_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Set Gender",         callback_data="set_gender")],
        [InlineKeyboardButton("🎯 Set Interests",      callback_data="set_interests")],
        [InlineKeyboardButton("🌍 Set Country",        callback_data="set_country")],
        [InlineKeyboardButton("🔍 Gender Filter",      callback_data="set_gf")],
        [InlineKeyboardButton("« Back",                callback_data="back_main")],
    ])


# ════════════════════════════════════════════════════════════
#  Guards / middleware helpers
# ════════════════════════════════════════════════════════════
async def ensure_registered(message: Message):
    u = message.from_user
    await db.register_user(u.id, u.username or "", u.first_name or "", u.last_name or "")
    await db.touch_last_seen(u.id)


async def guard(message: Message) -> bool:
    """
    Returns True (block) if user should NOT proceed.
    Checks: ban, karma, flood.
    """
    uid = message.from_user.id

    if await db.is_banned(uid):
        await message.reply("🚫 You are **banned** from this bot.")
        return True

    user = await db.get_user(uid)
    if user and user["karma"] < MIN_KARMA_TO_CHAT:
        await message.reply(
            "⛔ Your karma is too low to use this bot.\n"
            "Behave nicely to earn karma back."
        )
        return True

    if flood_guard.check(uid):
        await message.reply("⚠️ Slow down! You are sending messages too fast.")
        return True

    return False


# ════════════════════════════════════════════════════════════
#  State tracker for multi-step flows (settings wizard)
# ════════════════════════════════════════════════════════════
_state: dict = {}   # user_id -> "awaiting_interests" | "awaiting_country" | …

AWAITING_INTERESTS = "awaiting_interests"
AWAITING_COUNTRY   = "awaiting_country"


# ════════════════════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, message: Message):
    await ensure_registered(message)
    if await guard(message):
        return

    name = message.from_user.first_name or "there"
    await message.reply(
        f"👋 **Welcome, {name}!**\n\n"
        "I'm an **Anonymous Chat Bot** — meet random strangers and chat privately.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 /find   — Search for a stranger\n"
        "⏭ /next   — Skip current partner\n"
        "🛑 /stop   — End the chat\n"
        "🚩 /report — Report your partner\n"
        "⚙️ /settings — Set gender, interests…\n"
        "❓ /help   — Show this menu\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Tap **Find Stranger** to begin! 🚀",
        reply_markup=kb_main(),
    )


# ════════════════════════════════════════════════════════════
#  /help
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("help") & filters.private)
async def cmd_help(client: Client, message: Message):
    await message.reply(
        "📖 **Help Menu**\n\n"
        "**Commands:**\n"
        "• /start — Welcome screen\n"
        "• /find — Find a random stranger\n"
        "• /next — Skip to next stranger\n"
        "• /stop — End current chat\n"
        "• /report — Report abusive user\n"
        "• /settings — Configure your profile\n"
        "• /profile — View your profile & karma\n\n"
        "**Tips:**\n"
        "• Be respectful to earn 🌟 Karma\n"
        "• Set interests to match with like-minded people\n"
        "• Use gender filter to choose who you meet\n"
        "• Reports are reviewed by admins"
    )


# ════════════════════════════════════════════════════════════
#  /settings
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("settings") & filters.private)
async def cmd_settings(client: Client, message: Message):
    await ensure_registered(message)
    user = await db.get_user(message.from_user.id)
    await message.reply(
        "⚙️ **Settings**\n\n"
        f"👤 Gender:   `{user['gender'] if user else 'random'}`\n"
        f"🎯 Interests: `{user['interests'] if user and user['interests'] else 'none set'}`\n"
        f"🌍 Country:  `{user['country'] if user and user['country'] else 'not set'}`",
        reply_markup=kb_settings(),
    )


# ════════════════════════════════════════════════════════════
#  /profile
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("profile") & filters.private)
async def cmd_profile(client: Client, message: Message):
    await ensure_registered(message)
    user = await db.get_user(message.from_user.id)
    if not user:
        return
    karma_stars = "⭐" * min(5, max(0, user["karma"] // 10))
    await message.reply(
        f"📊 **Your Profile**\n\n"
        f"🆔 ID:        `{user['user_id']}`\n"
        f"👤 Gender:   `{user['gender']}`\n"
        f"🎯 Interests: `{user['interests'] or 'none'}`\n"
        f"🌍 Country:  `{user['country'] or 'not set'}`\n"
        f"💬 Chats:    `{user['total_chats']}`\n"
        f"🌟 Karma:    `{user['karma']}` {karma_stars}\n"
        f"📅 Joined:   `{str(user['joined_at'])[:10]}`"
    )


# ════════════════════════════════════════════════════════════
#  /find — join queue
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("find") & filters.private)
async def cmd_find(client: Client, message: Message):
    await ensure_registered(message)
    if await guard(message):
        return

    uid  = message.from_user.id

    # Already in a chat?
    if await db.is_in_chat(uid):
        return await message.reply(
            "💬 You're already in a chat.\n"
            "Use /next to skip or /stop to end.",
            reply_markup=kb_in_chat()
        )

    # Already in queue?
    if await matchmaker.is_queued(uid):
        return await message.reply("🔍 Already searching… please wait.")

    user     = await db.get_user(uid)
    past     = await db.get_past_partners(uid)
    entry    = QueueEntry(
        user_id       = uid,
        gender        = user["gender"] if user else "random",
        interests     = set(user["interests"].split(",")) if user and user["interests"] else set(),
        country       = user["country"] if user else "",
        gender_filter = "random",
        past_partners = past,
    )

    partner_id = await matchmaker.enqueue(entry)
    if partner_id:
        await _start_chat(client, uid, partner_id)
    else:
        await message.reply(
            "🔍 **Searching for a stranger…**\n\n"
            "Please wait while we find someone for you.\n"
            "_Type /stop to cancel search._"
        )
        asyncio.create_task(_search_ticker(client, uid))


async def _search_ticker(client: Client, user_id: int):
    """Keep sending status dots while user is in queue."""
    dots   = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0
    elapsed = 0
    while await matchmaker.is_queued(user_id):
        await asyncio.sleep(SEARCH_MSG_INTERVAL)
        elapsed += SEARCH_MSG_INTERVAL
        if not await matchmaker.is_queued(user_id):
            break
        try:
            await client.send_message(
                user_id,
                f"{dots[i % len(dots)]} Still searching… ({elapsed}s)\n"
                "_/stop to cancel_"
            )
        except Exception:
            break
        i += 1


async def _start_chat(client: Client, uid1: int, uid2: int):
    await db.create_chat(uid1, uid2)
    user1 = await db.get_user(uid1)
    user2 = await db.get_user(uid2)

    common_interests = ""
    if user1 and user2 and user1["interests"] and user2["interests"]:
        a = set(user1["interests"].split(","))
        b = set(user2["interests"].split(","))
        common = a & b
        if common:
            common_interests = f"\n🎯 Common interests: `{', '.join(common)}`"

    msg = (
        "🎉 **Stranger found!**\n\n"
        f"You are now connected anonymously.{common_interests}\n\n"
        "_Say hi! Use /next to skip or /stop to end._"
    )
    for uid in (uid1, uid2):
        try:
            await client.send_message(uid, msg, reply_markup=kb_in_chat())
        except Exception as e:
            log.warning("Could not notify %s: %s", uid, e)


# ════════════════════════════════════════════════════════════
#  /next — skip current partner
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("next") & filters.private)
async def cmd_next(client: Client, message: Message):
    await ensure_registered(message)
    uid = message.from_user.id

    # If in queue, dequeue and find again
    if await matchmaker.is_queued(uid):
        await matchmaker.dequeue(uid)
        await message.reply("🔄 Restarting search…")
        return await cmd_find(client, message)

    partner_id = await db.get_partner(uid)
    if partner_id:
        await db.end_chat(uid)
        await matchmaker.remove_matched(uid)
        # notify old partner
        try:
            await client.send_message(
                partner_id,
                "😔 Your partner has moved on.\n"
                "🔍 Searching for a new stranger…",
            )
        except Exception:
            pass
        # put old partner back in queue
        await _auto_reconnect(client, partner_id)
        await message.reply("⏭ Skipping to next stranger…")
        await cmd_find(client, message)
    else:
        await cmd_find(client, message)


async def _auto_reconnect(client: Client, uid: int):
    """Put user back into queue automatically after their partner left."""
    user = await db.get_user(uid)
    if not user or user["is_banned"]:
        return
    past  = await db.get_past_partners(uid)
    entry = QueueEntry(
        user_id       = uid,
        gender        = user["gender"],
        interests     = set(user["interests"].split(",")) if user["interests"] else set(),
        country       = user["country"] or "",
        past_partners = past,
    )
    partner_id = await matchmaker.enqueue(entry)
    if partner_id:
        await _start_chat(client, uid, partner_id)
    else:
        try:
            await client.send_message(
                uid,
                "🔍 Searching for a new stranger…\n_/stop to cancel_"
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
#  /stop — end chat
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("stop") & filters.private)
async def cmd_stop(client: Client, message: Message):
    uid = message.from_user.id

    # Cancel queue
    if await matchmaker.is_queued(uid):
        await matchmaker.dequeue(uid)
        return await message.reply(
            "🛑 Search cancelled.", reply_markup=kb_main()
        )

    partner_id = await db.get_partner(uid)
    if not partner_id:
        return await message.reply(
            "❌ You are not in any chat.", reply_markup=kb_main()
        )

    await db.end_chat(uid)
    await matchmaker.remove_matched(uid)

    await message.reply(
        "🛑 **Chat ended.**\n\n"
        "Thanks for chatting! Tap **Find Stranger** to meet someone new. 🚀",
        reply_markup=kb_main()
    )
    try:
        await client.send_message(
            partner_id,
            "😔 Your partner has ended the chat.\n"
            "Tap **Find Stranger** to meet someone new! 🚀",
            reply_markup=kb_main()
        )
    except Exception:
        pass


# ════════════════════════════════════════════════════════════
#  /report
# ════════════════════════════════════════════════════════════
@app.on_message(filters.command("report") & filters.private)
async def cmd_report(client: Client, message: Message):
    uid        = message.from_user.id
    partner_id = await db.get_partner(uid)

    if not partner_id:
        return await message.reply("❌ You are not in a chat right now.")

    parts  = message.text.split(maxsplit=1)
    reason = parts[1] if len(parts) > 1 else "No reason given"

    await db.add_report(uid, partner_id, reason)
    await db.update_karma(partner_id, -10)

    # notify admins
    for admin_id in ADMIN_IDS:
        try:
            await client.send_message(
                admin_id,
                f"🚩 **New Report**\n"
                f"Reporter: `{uid}`\n"
                f"Reported: `{partner_id}`\n"
                f"Reason: _{reason}_"
            )
        except Exception:
            pass

    await message.reply(
        "✅ **Report submitted.**\n"
        "Our admins will review it shortly.\n"
        "Thank you for keeping this community safe! 🛡"
    )


# ════════════════════════════════════════════════════════════
#  Callback queries (inline buttons)
# ════════════════════════════════════════════════════════════
@app.on_callback_query()
async def handle_callbacks(client: Client, query: CallbackQuery):
    data = query.data
    uid  = query.from_user.id

    await query.answer()

    # -- Navigation callbacks --------------------------------
    if data == "find":
        await query.message.delete()
        await cmd_find(client, query.message)

    elif data == "help":
        await query.message.edit_text(
            "📖 **Help Menu**\n\n"
            "• /find — Find a stranger\n"
            "• /next — Skip partner\n"
            "• /stop — End chat\n"
            "• /report — Report abuse\n"
            "• /settings — Profile settings\n"
            "• /profile — View karma & stats",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("« Back", callback_data="back_main")
            ]])
        )

    elif data == "profile":
        user = await db.get_user(uid)
        if user:
            stars = "⭐" * min(5, max(0, user["karma"] // 10))
            await query.message.edit_text(
                f"📊 **Your Profile**\n\n"
                f"🆔 ID: `{user['user_id']}`\n"
                f"👤 Gender: `{user['gender']}`\n"
                f"🎯 Interests: `{user['interests'] or 'none'}`\n"
                f"🌍 Country: `{user['country'] or 'not set'}`\n"
                f"💬 Chats: `{user['total_chats']}`\n"
                f"🌟 Karma: `{user['karma']}` {stars}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("« Back", callback_data="back_main")
                ]])
            )

    elif data == "settings":
        user = await db.get_user(uid)
        await query.message.edit_text(
            "⚙️ **Settings**\n\n"
            f"👤 Gender:    `{user['gender'] if user else 'random'}`\n"
            f"🎯 Interests: `{user['interests'] if user and user['interests'] else 'none'}`\n"
            f"🌍 Country:   `{user['country'] if user and user['country'] else 'not set'}`",
            reply_markup=kb_settings(),
        )

    elif data == "back_main":
        await query.message.edit_text(
            "👋 **Main Menu**\n\nChoose an option below:",
            reply_markup=kb_main()
        )

    # -- In-chat buttons -------------------------------------
    elif data == "next":
        msg = query.message
        msg.from_user = query.from_user
        msg.text = "/next"
        await cmd_next(client, msg)

    elif data == "stop":
        msg = query.message
        msg.from_user = query.from_user
        msg.text = "/stop"
        await cmd_stop(client, msg)

    elif data == "report":
        msg = query.message
        msg.from_user = query.from_user
        msg.text = "/report"
        await cmd_report(client, msg)

    elif data == "block":
        partner_id = await db.get_partner(uid)
        if partner_id:
            await db.block_user(uid, partner_id)
            msg = query.message
            msg.from_user = query.from_user
            msg.text = "/next"
            await cmd_next(client, msg)
            await client.send_message(uid, "🚫 User blocked. Moving to next...")

    # -- Settings callbacks ----------------------------------
    elif data == "set_gender":
        await query.message.edit_text(
            "👤 **Select your gender:**",
            reply_markup=kb_gender()
        )

    elif data.startswith("gender_"):
        gender = data.split("_")[1]
        await db.update_user_profile(uid, gender=gender)
        await query.message.edit_text(
            f"✅ Gender set to **{gender}**",
            reply_markup=kb_settings()
        )

    elif data == "set_gf":
        await query.message.edit_text(
            "🔍 **Who do you want to chat with?**",
            reply_markup=kb_gender_filter()
        )

    elif data.startswith("gf_"):
        gf = data.split("_")[1]
        await db.update_user_profile(uid, gender=gf)   # store preference
        await query.message.edit_text(
            f"✅ Gender filter set to **{gf}**",
            reply_markup=kb_settings()
        )

    elif data == "set_interests":
        _state[uid] = AWAITING_INTERESTS
        await query.message.edit_text(
            "🎯 **Set your interests**\n\n"
            "Send a message with your interests separated by commas.\n"
            "Example: `music, gaming, movies, travel`",
        )

    elif data == "set_country":
        _state[uid] = AWAITING_COUNTRY
        await query.message.edit_text(
            "🌍 **Set your country**\n\n"
            "Send your country name. Example: `India`"
        )


# ════════════════════════════════════════════════════════════
#  Message relay — core anonymous chat functionality
# ════════════════════════════════════════════════════════════
@app.on_message(filters.private & ~filters.command([
    "start", "help", "find", "next", "stop",
    "report", "settings", "profile",
    "ban", "unban", "stats", "broadcast", "users", "reports"
]))
async def relay_message(client: Client, message: Message):
    uid = message.from_user.id

    await ensure_registered(message)
    if await guard(message):
        return

    # ── handle state machine (settings wizard) ─────────────
    if uid in _state:
        state = _state.pop(uid)

        if state == AWAITING_INTERESTS:
            interests = ",".join(
                i.strip().lower() for i in message.text.split(",")[:10]
                if i.strip()
            )
            await db.update_user_profile(uid, interests=interests)
            return await message.reply(
                f"✅ Interests saved: `{interests}`\n\n"
                "Use /settings to view or change them.",
                reply_markup=kb_main()
            )

        elif state == AWAITING_COUNTRY:
            country = message.text.strip()[:50]
            await db.update_user_profile(uid, country=country)
            return await message.reply(
                f"✅ Country set to: `{country}`",
                reply_markup=kb_main()
            )

    # ── not in chat ─────────────────────────────────────────
    partner_id = await db.get_partner(uid)
    if not partner_id:
        if await matchmaker.is_queued(uid):
            return  # silently ignore messages while in queue
        return await message.reply(
            "❌ You are not in a chat.\nUse /find to meet a stranger.",
            reply_markup=kb_main()
        )

    # ── content moderation ──────────────────────────────────
    if message.text and not moderator.is_clean(message.text):
        await db.update_karma(uid, -5)
        return await message.reply(
            "⚠️ Your message was blocked by auto-moderation.\n"
            "Please keep the conversation respectful."
        )

    # ── relay typing indicator ──────────────────────────────
    asyncio.create_task(_relay_typing(client, partner_id))

    # ── relay the actual message ─────────────────────────────
    try:
        if message.text:
            await client.send_message(partner_id, message.text)

        elif message.photo:
            await client.send_photo(
                partner_id,
                message.photo.file_id,
                caption=message.caption or ""
            )

        elif message.video:
            await client.send_video(
                partner_id,
                message.video.file_id,
                caption=message.caption or ""
            )

        elif message.voice:
            await client.send_voice(partner_id, message.voice.file_id)

        elif message.audio:
            await client.send_audio(
                partner_id,
                message.audio.file_id,
                caption=message.caption or ""
            )

        elif message.sticker:
            await client.send_sticker(partner_id, message.sticker.file_id)

        elif message.document:
            await client.send_document(
                partner_id,
                message.document.file_id,
                caption=message.caption or ""
            )

        elif message.video_note:
            await client.send_video_note(partner_id, message.video_note.file_id)

        elif message.animation:
            await client.send_animation(
                partner_id,
                message.animation.file_id,
                caption=message.caption or ""
            )

        elif message.location:
            await client.send_location(
                partner_id,
                message.location.latitude,
                message.location.longitude
            )

        else:
            await message.reply("⚠️ Unsupported message type.")

    except Exception as e:
        log.error("Relay error uid=%s partner=%s: %s", uid, partner_id, e)
        # Partner probably blocked the bot
        await db.end_chat(uid)
        await matchmaker.remove_matched(uid)
        await message.reply(
            "😔 Could not send message. Your partner may have left.\n"
            "Use /find to connect with someone new.",
            reply_markup=kb_main()
        )


async def _relay_typing(client: Client, user_id: int):
    try:
        await client.send_chat_action(user_id, ChatAction.TYPING)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════
#  Background task — queue expiry checker
# ════════════════════════════════════════════════════════════
async def queue_expiry_task():
    while True:
        await asyncio.sleep(30)
        expired = await matchmaker.expire_old_entries()
        for uid in expired:
            try:
                await app.send_message(
                    uid,
                    "⌛ Search timed out — no stranger found.\n"
                    "Use /find to try again.",
                    reply_markup=kb_main()
                )
            except Exception:
                pass
        if expired:
            log.info("Expired %d queue entries", len(expired))


# ════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════
async def main():
    await db.connect()

    # Register admin commands
    register_admin_handlers(app, db)

    log.info("🚀 Starting Anonymous Chat Bot…")
    await app.start()

    me = await app.get_me()
    log.info("✅ Bot started as @%s (id=%s)", me.username, me.id)

    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await app.send_message(
                admin_id,
                f"✅ **Bot is online!**\n"
                f"Username: @{me.username}\n"
                f"ID: `{me.id}`"
            )
        except Exception:
            pass

    # start background tasks
    asyncio.create_task(queue_expiry_task())

    await idle()
    await app.stop()
    await db.close()
    log.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
