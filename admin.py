# ============================================================
#   Anonymous Chat Bot — handlers/admin.py
#   Admin commands with broadcast, stats, ban, unban
# ============================================================

import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message

from config import ADMIN_IDS
from database import Database

log = logging.getLogger(__name__)


def admin_only(_, __, m: Message) -> bool:
    return m.from_user and m.from_user.id in ADMIN_IDS


admin_filter = filters.create(admin_only)


# ════════════════════════════════════════════════════════════
#  Register all admin handlers
# ════════════════════════════════════════════════════════════
def register_admin_handlers(app: Client, db: Database):

    # ── /stats ──────────────────────────────────────────────
    @app.on_message(filters.command("stats") & admin_filter)
    async def cmd_stats(client: Client, message: Message):
        stats = await db.get_stats()
        text = (
            "📊 **Bot Statistics**\n\n"
            f"👥 Total Users:    `{stats['total_users']:,}`\n"
            f"💬 Total Chats:    `{stats['total_chats']:,}`\n"
            f"🔗 Active Chats:   `{stats['active_chats']:,}`\n"
            f"🚫 Banned Users:   `{stats['banned_users']:,}`\n"
            f"⚠️  Total Reports:  `{stats['total_reports']:,}`\n"
        )
        await message.reply(text)

    # ── /ban user_id [reason] ────────────────────────────────
    @app.on_message(filters.command("ban") & admin_filter)
    async def cmd_ban(client: Client, message: Message):
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2 or not parts[1].isdigit():
            return await message.reply("Usage: `/ban <user_id> [reason]`")

        target_id = int(parts[1])
        reason    = parts[2] if len(parts) > 2 else "Banned by admin"

        user = await db.get_user(target_id)
        if not user:
            return await message.reply("❌ User not found in database.")

        await db.ban_user(target_id, reason, message.from_user.id)
        # notify target if possible
        try:
            await client.send_message(
                target_id,
                "🚫 You have been **banned** from this bot.\n"
                f"Reason: `{reason}`\n\n"
                "Contact support if you think this is a mistake."
            )
        except Exception:
            pass
        await message.reply(f"✅ User `{target_id}` banned.\nReason: `{reason}`")

    # ── /unban user_id ───────────────────────────────────────
    @app.on_message(filters.command("unban") & admin_filter)
    async def cmd_unban(client: Client, message: Message):
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return await message.reply("Usage: `/unban <user_id>`")

        target_id = int(parts[1])
        await db.unban_user(target_id)
        try:
            await client.send_message(
                target_id,
                "✅ Your ban has been lifted. You can use the bot again."
            )
        except Exception:
            pass
        await message.reply(f"✅ User `{target_id}` unbanned.")

    # ── /users ───────────────────────────────────────────────
    @app.on_message(filters.command("users") & admin_filter)
    async def cmd_users(client: Client, message: Message):
        count = await db.get_user_count()
        bans  = await db.get_banned_list()

        lines = [f"👥 **Total registered users: {count:,}**\n", "**Last 20 bans:**"]
        for b in bans:
            name = b["username"] or b["first_name"] or "Unknown"
            lines.append(f"• `{b['user_id']}` — @{name} — _{b['reason']}_")

        await message.reply("\n".join(lines))

    # ── /reports ─────────────────────────────────────────────
    @app.on_message(filters.command("reports") & admin_filter)
    async def cmd_reports(client: Client, message: Message):
        parts = message.text.split()
        uid   = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        rpts  = await db.get_reports(uid)

        if not rpts:
            return await message.reply("No reports found.")

        lines = [f"⚠️ **Reports {'for user ' + str(uid) if uid else '(latest 50)'}:**\n"]
        for r in rpts:
            lines.append(
                f"• Reporter `{r['reporter_id']}` → Reported `{r['reported_id']}`\n"
                f"  Reason: _{r['reason']}_  |  {r['created_at']}"
            )
        await message.reply("\n".join(lines[:40]))  # keep it under limit

    # ── /broadcast message ───────────────────────────────────
    @app.on_message(filters.command("broadcast") & admin_filter)
    async def cmd_broadcast(client: Client, message: Message):
        text = message.text.partition(" ")[2].strip()
        if not text:
            return await message.reply(
                "Usage: `/broadcast <your message>`\n"
                "Supports **markdown**."
            )

        user_ids = await db.get_all_user_ids()
        status   = await message.reply(
            f"📡 Broadcasting to **{len(user_ids):,}** users…"
        )

        ok = fail = 0
        for uid in user_ids:
            try:
                await client.send_message(uid, text)
                ok += 1
            except Exception:
                fail += 1
            if (ok + fail) % 50 == 0:
                await asyncio.sleep(1)   # Telegram rate limit

        await status.edit(
            f"✅ Broadcast complete.\n"
            f"Sent: `{ok}` | Failed: `{fail}`"
        )
