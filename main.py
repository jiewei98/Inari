# --- Standard library ---
import os
import re
import asyncio

# --- Third-party packages ---
import discord
import threading  # Run Flask and bot together
from flask import Flask
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

# --- Flask web server setup
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

# --- Your bot logic goes here...
# (keep all your event handlers like on_message, on_reaction_add, etc.)
target_bot_id = 1312830013573169252  # Target bot ID
server_id = 938644623394492428 # Server ID
warning_channel_id = 1373574689682751560  # Nairi-market-warn
# Map channel ID to allowed print range (inclusive)
print_ranges = {
    # T1 channels
    1348297134281326632: (1, 10),      # t1-exclusive-print
    1348297179281887422: (11, 99),     # t1-low-print
    1348297282428076112: (100, 999),   # t1-mid-print
    1348298215497404459: (1000, 2500), # t1-high-print

    # T2 channels
    1381958187103817758: (1, 10),      # t2-exclusive-print
    1381958240790646874: (11, 99),     # t2-low-print
    1381958270402691214: (100, 999),   # t2-mid-print

    # 1353381835547344987: (1, 10),      # observation-room for testing
}
message_timeout = 60  # seconds

# Mappings
user_card_codes = {}           # user_id: list of card codes
message_user_map = {}          # message_id: user_id
user_response_message = {}     # user_id: response message
user_wants_to_copy = {}        # user_id: bool

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

        if original.author.id != target_bot_id or not original.embeds:
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

        # Extract card code and print number
        card_code, card_print = parse_card_line_for_code_and_print(raw_card_line)

        # Determine tier from placeholder
        TIER_PLACEHOLDER_MAP = {
            "sReCBQAkp3iWWpmo+/1/SwL8CGeIaImHZw==": "T1",
            "sheCBQAkqGiVa5nJ/f5vSwL8CFeHeImHaA==": "T2"
        }

        placeholder = embed.thumbnail.placeholder if embed.thumbnail and hasattr(embed.thumbnail, "placeholder") else ""
        card_tier = TIER_PLACEHOLDER_MAP.get(placeholder, "T1")  # default to T1

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
        asyncio.create_task(expire_user_mapping(message.author.id, message_timeout))

        def check(m):
            return m.author.id == target_bot_id and m.channel == message.channel

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
    if message.channel.id in print_ranges:
        if message.author.bot or message.author.id == target_bot_id:
            return
        
        allowed_min, allowed_max = print_ranges[message.channel.id]
        parts = content.lower().strip().split()
        
        if not parts or parts[0] not in ("nv", "nview"):
            # Invalid command, delete
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return
        # else valid command

        def check_bot_reply(m):
            return (
                m.author.id == target_bot_id and
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

            raw_card_line = fields[1].value.strip()
            card_code, card_print = parse_card_line_for_code_and_print(raw_card_line)

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
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    pass

                # Still send the warning regardless
                warning_channel = client.get_channel(warning_channel_id)
                if warning_channel:
                    try:
                        await warning_channel.send(
                            f"{message.author.mention}, your recently posted card {card_code} has a print number {print_number}, "
                            f"which is not allowed in {message.channel.mention}. Please check the print number and post in the correct channel."
                        )
                    except discord.Forbidden:
                        pass

        except asyncio.TimeoutError:
            return


@client.event
async def on_reaction_add(reaction, user):
    if user == client.user:
        return
    if reaction.message.author.id != target_bot_id or reaction.emoji != "📝":
        return

    user_id = message_user_map.get(reaction.message.id)
    if user_id is None or user_id != user.id:
        return

    user_wants_to_copy[user.id] = True
    await extract_and_send_card_codes(reaction.message, user)

@client.event
async def on_message_edit(before, after):
    if after.author.id != target_bot_id or not after.embeds:
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
    if message.author.id != target_bot_id:
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

@client.event
async def on_ready():
    await client.tree.sync()  # sync globally

# --- Main entry point
if __name__ == "__main__":
    threading.Thread(target=run_web).start()  # Run Flask on a separate thread
    client.run(os.getenv("TOKEN"))            # Start Discord bot
