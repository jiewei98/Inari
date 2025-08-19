# --- Standard library ---
import os
import re
import asyncio
import datetime

# --- Third-party packages ---
import discord
from discord.ext import commands
from dotenv import load_dotenv

# --- Load environment variables
load_dotenv()

# --- Discord setup
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.messages = True

client = commands.Bot(command_prefix="!", intents=intents)

# --- Variables declaration
TARGET_BOT_ID = 1312830013573169252  # Target bot ID
SERVER_ID = 938644623394492428 # Server ID
# SERVER_ID = 866730377258074152 # Test server ID
WARNING_CHANNEL_ID = 1373574689682751560  # Nairi-market-warn
NAIRI_AUTO_CLOSE_THREAD_CHANNEL_IDS = {
    # 1403052540223815700, # Test channel

    # Nairi auction channels
    1348289832388001803, # nairi-auction-1
    1348289882287640596, # nairi-auction-2
    1348289907910512831, # nairi-auction-3
    1355878579375833098, # nairi-auction-4
    1391049063129944195, # nairi-code-auction
}
SOFI_AUTO_CLOSE_THREAD_CHANNEL_IDS = {
    # Sofi auction channels
    973938253180850236, # glow-auction
    1089023076617949194, # frame-auction
    1081575442730979391, # sofi-code-auction
    1329789950215983106, # banner-auction
    973938304540098610, # morph-auction
    987751892132184127, # vip-auction
    1194976596239601764, # vip-auction-2
    938664690983272489, # sofi-auction-1
    938664738831863868, # sofi-auction-2
    938666930720608277, # sofi-auction-3
    938664487727292426, # sofi-auction-4
    952500783734210560, # sofi-auction-5
    1042089121830670346, # sofi-auction-6
}
# Map channel ID to allowed print range (inclusive)
PRINT_RANGES = {
    # T1 channels
    1348297134281326632: {"tier": "T1", "range": (1, 10)},
    1348297179281887422: {"tier": "T1", "range": (11, 99)},
    1348297282428076112: {"tier": "T1", "range": (100, 999)},
    1348298215497404459: {"tier": "T1", "range": (1000, 2500)},

    # T2 channels
    1381958187103817758: {"tier": "T2", "range": (1, 10)},
    1381958240790646874: {"tier": "T2", "range": (11, 99)},
    1381958270402691214: {"tier": "T2", "range": (100, 999)},

    # Smr25/Summer channel
    1404784532644954253: {"tier": "Smr25", "range": None},  # No print range enforcement
}
MESSAGE_TIMEOUT = 60  # seconds
MIN_THREAD_AGE_HOURS = 20 # 20 hours for actual
# MIN_THREAD_AGE_HOURS = 0.25 # 15 minutes for testing
# MIN_THREAD_AGE_HOURS = 0.001 # 3.6 seconds for testing

# Mappings
user_card_codes = {}           # user_id: list of card codes
message_user_map = {}          # message_id: user_id
user_response_message = {}     # user_id: response message
user_wants_to_copy = {}        # user_id: bool

# --- Methods declaration
# Cleanup function
def clear_user_data(user_id):
    user_card_codes.pop(user_id, None)
    user_response_message.pop(user_id, None)
    user_wants_to_copy.pop(user_id, None)
    for message_id in list(message_user_map):
        if message_user_map[message_id] == user_id:
            del message_user_map[message_id]

# Timeout-based cleanup
async def expire_user_mapping(user_id, delay):
    await asyncio.sleep(delay)
    clear_user_data(user_id)

# Extract card code
def extract_card_codes_from_field(field_value):
    codes = []
    lines = field_value.strip().splitlines()

    for line in lines:
        parts = line.split('•')
        if len(parts) >= 4:
            # The third • segment should contain the card code inside backticks
            raw_segment = parts[3].strip()
            match = re.search(r'`([^`]+)`', raw_segment)
            if match:
                code = match.group(1).strip()
                codes.append(code)
    return codes

# Extract card code and print number
def parse_card_line_for_code_and_print(raw_card_line):
    code_match = re.findall(r"`([^`]+)`", raw_card_line)
    card_code = code_match[0] if len(code_match) > 0 else "Unknown"
    card_print = code_match[1] if len(code_match) > 1 else "Unknown"
    card_print = card_print.replace("P-", "P")
    return card_code, card_print

# Extract card tier
def get_card_tier_from_embed(embed):
    TIER_PLACEHOLDER_MAP = {
        "sReCBQAkp3iWWpmo+/1/SwL8CGeIaImHZw==": "T1",
        "sheCBQAkqGiVa5nJ/f5vSwL8CFeHeImHaA==": "T2",
        "dAiCBQAkmWa5SI2m+HVgYwXYCGeIZ4h4lw==": "Smr25",
    }

    placeholder = ""
    if embed.thumbnail and hasattr(embed.thumbnail, "placeholder"):
        placeholder = embed.thumbnail.placeholder

    return TIER_PLACEHOLDER_MAP.get(placeholder, "T1")  # Default to T1 if unknown

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.strip().lower()
    # --- Feature 1: %auc reply parser ---
    if content.lower().startswith('%auc'):
        if not message.reference or not isinstance(message.reference.resolved, discord.Message):
            await message.channel.send("read <#1348292826609221642> on how to use `%auc`")
            return

        original = message.reference.resolved

        if original.author.id != TARGET_BOT_ID or not original.embeds:
            await message.channel.send("read <#1348292826609221642> on how to use `%auc`")
            return

        embed = original.embeds[0]
        fields = embed.fields
        command_parts = content.split(maxsplit=1)
        preference = "<:jades:1351944414104129599>"

        emoji_map = {
            ":jades:": "<:jades:1351944414104129599>",
        }

        if len(command_parts) > 1:
            raw_pref = command_parts[1]
            for alias, full in emoji_map.items():
                raw_pref = raw_pref.replace(alias, full)
            preference = raw_pref.strip()

        card_name = embed.title or "Unknown"
        if not (card_name.startswith("**") and card_name.endswith("**")):
            await message.channel.send("read <#1348292826609221642> on how to use `%auc`")
            return

        card_series = fields[0].value.strip() if len(fields) > 0 else "Unknown"
        raw_card_line = fields[1].value.strip() if len(fields) > 1 else ""
        owned_by = fields[2].value.strip() if len(fields) > 2 else "Unknown"

        # Extract card code, print number and card tier
        card_code, card_print = parse_card_line_for_code_and_print(raw_card_line)
        card_tier = get_card_tier_from_embed(embed)

        formatted = (
            f"Card Code: {card_code}\n"
            f"{card_print} • {card_name} • {card_series} [ {card_tier} ]\n"
            f"{owned_by}\n"
            f"Preference: {preference}"
        )

        await message.channel.send(formatted)
        return

    # --- Feature 2: 'nc' code tracking ---
    if content == "nc" or content.startswith("nc ") or content == "ncollection" or content.startswith("ncollection "):
        # Clear old mappings for this user
        clear_user_data(message.author.id)

        # Start timeout to expire mapping
        asyncio.create_task(expire_user_mapping(message.author.id, MESSAGE_TIMEOUT))

        def check(m):
            return m.author.id == TARGET_BOT_ID and m.channel == message.channel

        try:
            bot_message = await client.wait_for("message", timeout=10.0, check=check)

            for _ in range(10):
                if bot_message.embeds:
                    break
                await asyncio.sleep(0.5)
                bot_message = await message.channel.fetch_message(bot_message.id)

            if not bot_message.embeds:
                return

            message_user_map[bot_message.id] = message.author.id
            user_wants_to_copy[message.author.id] = False  # Reset until 📝
            await bot_message.add_reaction("📝")

        except asyncio.TimeoutError:
            return
        
    # --- Feature 4: nv/nview command enforcement in XXX channel ---
    if message.channel.id in PRINT_RANGES:
        if message.author.bot or message.author.id == TARGET_BOT_ID:
            return

        channel_config = PRINT_RANGES[message.channel.id]
        expected_tier = channel_config["tier"]
        allowed_range = channel_config["range"]
        parts = content.lower().strip().split()

        if not parts or parts[0] not in ("nv", "nview"):
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        def check_bot_reply(m):
            return (
                m.author.id == TARGET_BOT_ID and
                m.channel.id == message.channel.id and
                m.reference and
                m.reference.message_id == message.id
            )

        try:
            bot_reply = await client.wait_for("message", timeout=10.0, check=check_bot_reply)

            for _ in range(10):
                if bot_reply.embeds:
                    break
                await asyncio.sleep(0.5)
                bot_reply = await message.channel.fetch_message(bot_reply.id)

            if not bot_reply.embeds:
                return

            embed = bot_reply.embeds[0]
            fields = embed.fields

            if len(fields) < 2:
                return

            # Get card data
            raw_card_line = fields[1].value.strip()
            card_code, card_print = parse_card_line_for_code_and_print(raw_card_line)
            actual_tier = get_card_tier_from_embed(embed)

            if actual_tier != expected_tier:
                # Wrong tier → delete messages + warn
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass

                try:
                    await bot_reply.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

                warning_channel = client.get_channel(WARNING_CHANNEL_ID)
                if warning_channel:
                    await warning_channel.send(
                        f"{message.author.mention}, your recently posted card `{card_code}` is **{actual_tier}**, "
                        f"which is not allowed in {message.channel.mention}. Please check the card tier and post in the correct channel."
                    )
                return  # Don't continue to print check

            # Tier is valid → now do print check
            match = re.search(r"P?(\d+)", card_print)
            if not match:
                return

            print_number = int(match.group(1))

            if allowed_range is not None:
                allowed_min, allowed_max = allowed_range
                match = re.search(r"P?(\d+)", card_print)
                if not match:
                    return

                print_number = int(match.group(1))
                if print_number < allowed_min or print_number > allowed_max:
                    try:
                        await message.delete()
                    except discord.Forbidden:
                        pass

                    try:
                        await bot_reply.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass

                    warning_channel = client.get_channel(WARNING_CHANNEL_ID)
                    if warning_channel:
                        await warning_channel.send(
                            f"{message.author.mention}, your recently posted card `{card_code}` has print number **{print_number}**, "
                            f"which is not allowed in {message.channel.mention}. Please check the print number and post in the correct channel."
                        )

        except asyncio.TimeoutError:
            return

@client.event
async def on_reaction_add(reaction, user):
    if user == client.user:
        return
    if reaction.message.author.id != TARGET_BOT_ID or reaction.emoji != "📝":
        return

    user_id = message_user_map.get(reaction.message.id)
    if user_id is None or user_id != user.id:
        return

    user_wants_to_copy[user.id] = True
    await extract_and_send_card_codes(reaction.message, user)

@client.event
async def on_message_edit(before, after):
    if after.author.id != TARGET_BOT_ID or not after.embeds:
        return

    user_id = message_user_map.get(after.id)
    if user_id is None or not user_wants_to_copy.get(user_id, False):
        return

    user = await client.fetch_user(user_id)
    await extract_and_send_card_codes(after, user)

async def extract_and_send_card_codes(message, user):
    if not user_wants_to_copy.get(user.id, False):
        return

    if user.id not in user_card_codes:
        user_card_codes[user.id] = []

    stored = user_card_codes[user.id]
    before_count = len(stored)

    for embed in message.embeds:
        for field in embed.fields:
            new_codes = extract_card_codes_from_field(field.value)
            for code in new_codes:
                if code not in stored:
                    stored.append(code)


    if len(stored) > before_count:
        combined = ', '.join(stored)
        response_text = f"{combined}"

        previous_msg = user_response_message.get(user.id)
        if previous_msg:
            try:
                await previous_msg.edit(content=response_text)
            except discord.NotFound:
                new_msg = await message.reply(response_text, mention_author=False)
                user_response_message[user.id] = new_msg
        else:
            new_msg = await message.reply(response_text, mention_author=False)
            user_response_message[user.id] = new_msg

@client.tree.context_menu(name="Delete Nairi Message")
async def delete_message(interaction: discord.Interaction, message: discord.Message):
    # --- Feature 3: deleting your nairi messages ---
    if message.author.id != TARGET_BOT_ID:
        await interaction.response.send_message(
            "You can only delete messages from Nairi.", ephemeral=True
        )
        return

    if not message.reference or not message.reference.message_id:
        await interaction.response.send_message(
            "You can only delete your own Nairi messages.", ephemeral=True
        )
        return

    original_msg = await message.channel.fetch_message(message.reference.message_id)
    if original_msg.author.id != interaction.user.id:
        await interaction.response.send_message(
            "You can only delete your own Nairi messages.", ephemeral=True
        )
        return

    try:
        # Acknowledge first
        await interaction.response.defer(ephemeral=True)

        await message.delete()

        # Then send a follow-up
        await interaction.followup.send("Successfully deleted the message.", ephemeral=True)

    except discord.Forbidden:
        await interaction.followup.send(
            "I don't have permission to delete that message.", ephemeral=True
        )

# --- Feature 5: auto closing auction channels ---
async def close_threads(channels_to_close, guild, now_utc):
    all_threads = await guild.active_threads()
    for thread in all_threads:
        if thread.parent_id in channels_to_close and not thread.locked:
            thread_age = now_utc - thread.created_at
            if thread_age.total_seconds() >= MIN_THREAD_AGE_HOURS * 3600:
                try:
                    await thread.edit(archived=True, locked=True)
                except Exception:
                    pass

async def auto_close_task_runner(channels, target_hour, target_minute):
    last_run_date = None
    await client.wait_until_ready()

    while not client.is_closed():
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_sgt = now_utc + datetime.timedelta(hours=8)
        today_date = now_sgt.date()

        if ((now_sgt.hour > target_hour) or
            (now_sgt.hour == target_hour and now_sgt.minute >= target_minute)) \
            and last_run_date != today_date:

            guild = client.get_guild(SERVER_ID)
            if guild:
                await close_threads(channels, guild, now_utc)

            last_run_date = today_date
            await asyncio.sleep(60 * 60 * 23)  # wait ~23 hours
        else:
            await asyncio.sleep(60)

@client.event
async def on_ready():
    client.loop.create_task(auto_close_task_runner(SOFI_AUTO_CLOSE_THREAD_CHANNEL_IDS, 20, 0))  # 8PM SGT
    client.loop.create_task(auto_close_task_runner(NAIRI_AUTO_CLOSE_THREAD_CHANNEL_IDS, 22, 0))  # 10PM SGT
    await client.tree.sync()  # sync globally

# --- Main entry point
if __name__ == "__main__":
    client.run(os.getenv("TOKEN"))            # Start Discord bot
