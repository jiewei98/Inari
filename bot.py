# --- Standard library ---
import os
import re
import asyncio

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

# --- Your bot logic goes here...
# (keep all your event handlers like on_message, on_reaction_add, etc.)
target_bot_id = 1312830013573169252  # Target bot ID
server_id = 938644623394492428 # Server ID
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

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # --- Feature 1: %auc reply parser ---
    if message.content.lower().startswith('%auc'):
        if not message.reference or not isinstance(message.reference.resolved, discord.Message):
            await message.channel.send("read <#1348292826609221642> on how to use `%auc`")
            return

        original = message.reference.resolved

        if original.author.id != target_bot_id or not original.embeds:
            await message.channel.send("read <#1348292826609221642> on how to use `%auc`")
            return

        embed = original.embeds[0]
        fields = embed.fields
        command_parts = message.content.split(maxsplit=1)
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

        code_match = re.findall(r"`([^`]+)`", raw_card_line)
        card_code = code_match[0] if len(code_match) > 0 else "Unknown"
        card_number = code_match[2] if len(code_match) > 2 else "Unknown"
        card_number = card_number.replace("P-", "P")
        card_tier = "T1"

        formatted = (
            f"Card Code: {card_code}\n"
            f"{card_number} • {card_name} • {card_series} [ {card_tier} ]\n"
            f"{owned_by}\n"
            f"Preference: {preference}"
        )

        await message.channel.send(formatted)
        return

    # --- Feature 2: 'nc' code tracking ---
    if message.content.lower().startswith("nc ") or message.content.lower() == "nc":
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
        # Fix: Acknowledge first
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
    client.run(os.getenv("TOKEN"))            # Start Discord bot
