import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
import os
import asyncio

TOKEN = os.getenv("DISCORD_TOKEN")

ARCHIVE_AFTER_DAYS = 120
ARCHIVE_CATEGORY_NAME = "Archived"

CHANNEL_EDIT_DELAY_SECONDS = 2
MAX_RETRIES = 3

EXCLUDED_CATEGORY_NAMES = {
    "Information Center",
    "Tournament",
    "Partners/Server Links",
}

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    if not archive_inactive_channels.is_running():
        archive_inactive_channels.start()

    await archive_inactive_channels()


async def safe_channel_edit(channel: discord.TextChannel, **kwargs):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await channel.edit(**kwargs)
            await asyncio.sleep(CHANNEL_EDIT_DELAY_SECONDS)
            return True

        except discord.HTTPException as e:
            retry_after = getattr(e, "retry_after", None)
            wait_time = retry_after + 1 if retry_after else 5 * attempt

            print(
                f"HTTP error editing #{channel.name}. "
                f"Attempt {attempt}/{MAX_RETRIES}. "
                f"Waiting {wait_time}s. Error: {e}"
            )

            await asyncio.sleep(wait_time)

        except discord.Forbidden:
            print(f"Missing permissions for #{channel.name}")
            return False

    print(f"Failed to edit #{channel.name} after {MAX_RETRIES} attempts")
    return False


async def sort_archive_category(archive_category: discord.CategoryChannel):
    archived_channels = sorted(
        archive_category.text_channels,
        key=lambda c: c.name.lower()
    )

    for index, channel in enumerate(archived_channels):
        await safe_channel_edit(channel, position=index)


@tasks.loop(time=time(hour=0, minute=0, tzinfo=ZoneInfo("America/New_York")))
async def archive_inactive_channels():
    print(f"Running archive check at {datetime.now(timezone.utc)}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)

    for guild in bot.guilds:
        archive_category = discord.utils.get(
            guild.categories,
            name=ARCHIVE_CATEGORY_NAME
        )

        if archive_category is None:
            archive_category = await guild.create_category(
                ARCHIVE_CATEGORY_NAME,
                reason="Created archive category for inactive channels"
            )

        moved_any_channels = False

        for channel in guild.text_channels:
            if channel.category and channel.category.name in EXCLUDED_CATEGORY_NAMES:
                continue

            try:
                last_message = None

                async for message in channel.history(limit=1):
                    last_message = message

                if last_message is None:
                    continue

                if last_message.created_at < cutoff:
                    success = await safe_channel_edit(
                        channel,
                        category=archive_category,
                        sync_permissions=True,
                        reason=f"Archived after {ARCHIVE_AFTER_DAYS} days of inactivity"
                    )

                    if not success:
                        continue

                    moved_any_channels = True
                    print(f"Archived and synced #{channel.name}")

            except Exception as e:
                print(f"Error checking #{channel.name}: {e}")

        if moved_any_channels:
            await sort_archive_category(archive_category)
            print("Sorted archived channels alphabetically")


if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable is not set.")

bot.run(TOKEN)
