"""
Discord Stock & Money Manager Bot
Full-featured bot for Replit

Instructions:
1) Create a Replit project and add a secret named DISCORD_TOKEN with your bot token.
2) Edit ALLOWED_USER_IDS in the config below to the three Discord user IDs allowed to use commands (Alpha-1, Alpha-4, Alpha-5).
   If you prefer usernames, see the ALLOWED_USER_NAMES fallback (but IDs are recommended).
3) Make sure your server has these text channels (names must match exactly):
   - ⚡┇cmds           (all commands must be used here)
   - 💵┇banque         (status of money will be shown/updated here)
   - 📦┇marchandises   (status of merch will be shown/updated here)
   - 📋┇historique     (all movement messages will be posted here)
   You can change the names in the CONFIG section.
4) Install dependencies (requirements.txt):
   discord.py>=2.3.0

This script uses a local JSON file (data.json) for persistence so the data survives restarts on Replit.

Features implemented:
- /propre_in  /propre_out  (money clean in/out)
- /sale_in    /sale_out    (money dirty in/out)
- /marchandise_in  /marchandise_out  (item + qty)
- /new_marchandise  /delete_marchandise
- /clean_propre /clean_sale /clean_marchandise <item> /clean_marchandise_all
- All commands restricted to 3 users.
- All commands must be executed in the COMMAND channel.
- Every operation is logged in the history channel with who did what.
- Two permanent status messages (banque & marchandises) are created/updated automatically.

Note: Customize messages and channel names as you want in CONFIG.
"""

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime

# -------------------------------
# Mini serveur web pour keep_alive
# -------------------------------
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot actif !"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Lancer le serveur web
keep_alive()


# -------------------- CONFIG --------------------
# Replace these with the actual Discord IDs of Alpha-1, Alpha-4, Alpha-5
ALLOWED_USER_IDS = [549140350887788544, 428666981604917249, 621802427221278740]
# Optional fallback by exact username#discrim (e.g. "Alpha-1#1234") - used only if IDs aren't configured
ALLOWED_USER_NAMES = ["Alpha-1#0001", "Alpha-4#0004", "Alpha-5#0005"]

# Channel names (must match server channels) - you can rename them here
CHANNEL_CMD = "⚡┇cmds"
CHANNEL_BANQUE = "💵┇banque"
CHANNEL_MARCH = "📦┇marchandises"
CHANNEL_HISTORY = "📋┇historique"

DATA_FILE = "data.json"
SAVE_LOCK = asyncio.Lock()

# -------------------- DEFAULT DATA --------------------
DEFAULT_DATA = {
    "propre": 0,
    "sale": 0,
    "marchandises": {},
    "status_message_ids": {"banque": None, "marchandises": None}
}

# -------------------- HELPERS --------------------

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_DATA, f, ensure_ascii=False, indent=2)
        return DEFAULT_DATA.copy()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

async def save_data(data):
    async with SAVE_LOCK:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def is_user_allowed(user: discord.Member):
    # First check IDs
    if user.id in ALLOWED_USER_IDS:
        return True
    # fallback: check username#discriminator
    name_discrim = f"{user.name}#{user.discriminator}"
    if name_discrim in ALLOWED_USER_NAMES:
        return True
    return False

async def get_channel_by_name(guild: discord.Guild, name: str):
    for ch in guild.text_channels:
        if ch.name == name:
            return ch
    return None

async def ensure_status_messages(bot, guild, data):
    """Ensure that a status message exists in banque and marchandises channels and return them."""
    chan_banque = await get_channel_by_name(guild, CHANNEL_BANQUE)
    chan_march = await get_channel_by_name(guild, CHANNEL_MARCH)
    if chan_banque is None or chan_march is None:
        return None, None

    # banque
    banque_msg = None
    bid = data.get("status_message_ids", {}).get("banque")
    if bid:
        try:
            banque_msg = await chan_banque.fetch_message(bid)
        except Exception:
            banque_msg = None
    if banque_msg is None:
        banque_msg = await chan_banque.send("▶ Chargement des stats banque...")
        data.setdefault("status_message_ids", {})["banque"] = banque_msg.id
        await save_data(data)

    # marchandises
    march_msg = None
    mid = data.get("status_message_ids", {}).get("marchandises")
    if mid:
        try:
            march_msg = await chan_march.fetch_message(mid)
        except Exception:
            march_msg = None
    if march_msg is None:
        march_msg = await chan_march.send("▶ Chargement des stats marchandises...")
        data.setdefault("status_message_ids", {})["marchandises"] = march_msg.id
        await save_data(data)

    return banque_msg, march_msg

async def update_status_messages(banque_msg: discord.Message, march_msg: discord.Message, data):
    # Update banque embed
    embed_b = discord.Embed(title="Banque — États des fonds", timestamp=datetime.utcnow())
    embed_b.set_thumbnail(url="https://cdn.discordapp.com/attachments/1412715152947548282/1412715192604819478/image.png?ex=68c52a8c&is=68c3d90c&hm=de03073e4d8e83b90bd99ab3e61ddadf8dca7aa185dab99918f97640b4c8f082&")
    embed_b.add_field(name="Argent propre", value=f"{data.get('propre',0):,} $", inline=True)
    embed_b.add_field(name="Argent sale", value=f"{data.get('sale',0):,} $", inline=True)
    embed_b.set_footer(text="Dernière mise à jour")
    try:
        await banque_msg.edit(content=None, embed=embed_b)
    except Exception:
        pass

    # Update marchandises embed
    embed_m = discord.Embed(title="Marchandises — Stocks", timestamp=datetime.utcnow())
    embed_m.set_thumbnail(url="https://cdn.discordapp.com/attachments/1412715152947548282/1412715192604819478/image.png?ex=68c52a8c&is=68c3d90c&hm=de03073e4d8e83b90bd99ab3e61ddadf8dca7aa185dab99918f97640b4c8f082&")
    merch = data.get("marchandises", {})
    if merch:
        for name, qty in merch.items():
            embed_m.add_field(name=name, value=str(qty), inline=True)
    else:
        embed_m.description = "Aucune marchandise enregistrée"
    embed_m.set_footer(text="Dernière mise à jour")
    try:
        await march_msg.edit(content=None, embed=embed_m)
    except Exception:
        pass

async def post_history(guild: discord.Guild, message_text: str):
    ch = await get_channel_by_name(guild, CHANNEL_HISTORY)
    if ch:
        await ch.send(message_text)

# -------------------- BOT SETUP --------------------
intents = discord.Intents.default()
intents.message_content = False  # we use slash commands
bot = commands.Bot(command_prefix="!", intents=intents)

# We'll store loaded data globally
DATA = load_data()
DATA_LOCK = asyncio.Lock()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    # For each guild the bot is in, ensure status messages exist and update them
    for guild in bot.guilds:
        banque_msg, march_msg = await ensure_status_messages(bot, guild, DATA)
        if banque_msg and march_msg:
            await update_status_messages(banque_msg, march_msg, DATA)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Failed to sync commands:", e)

# -------------------- PERMISSION CHECK --------------------
async def check_allowed_and_channel(interaction: discord.Interaction):
    # allowed user
    if not is_user_allowed(interaction.user):
        await interaction.response.send_message("❌ Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True)
        return False
    # channel check
    if interaction.channel is None or interaction.channel.name != CHANNEL_CMD:
        await interaction.response.send_message(f"❌ Les commandes doivent être utilisées dans le salon #{CHANNEL_CMD}.", ephemeral=True)
        return False
    return True

# -------------------- COMMANDS --------------------

@bot.tree.command(name="propre_in", description="Entrée d'argent propre")
@app_commands.describe(montant="Montant en $")
async def propre_in(interaction: discord.Interaction, montant: int):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        DATA['propre'] = DATA.get('propre', 0) + montant
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Ajouté {montant:,} $ à l'argent propre.")
    # log
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a ajouté {montant:,} $ à l'argent propre")
    # update status
    banque_msg = None
    try:
        chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
        if chan_b:
            bid = DATA.get('status_message_ids', {}).get('banque')
            if bid:
                banque_msg = await chan_b.fetch_message(bid)
    except Exception:
        banque_msg = None
    march_msg = None
    try:
        chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
        if chan_m:
            mid = DATA.get('status_message_ids', {}).get('marchandises')
            if mid:
                march_msg = await chan_m.fetch_message(mid)
    except Exception:
        march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="propre_out", description="Sortie d'argent propre")
@app_commands.describe(montant="Montant en $")
async def propre_out(interaction: discord.Interaction, montant: int):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        DATA['propre'] = max(0, DATA.get('propre', 0) - montant)
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Retiré {montant:,} $ de l'argent propre.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a retiré {montant:,} $ de l'argent propre")
    # update status
    for _ in range(1):
        pass
    banque_msg = None
    try:
        chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
        if chan_b:
            bid = DATA.get('status_message_ids', {}).get('banque')
            if bid:
                banque_msg = await chan_b.fetch_message(bid)
    except Exception:
        banque_msg = None
    march_msg = None
    try:
        chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
        if chan_m:
            mid = DATA.get('status_message_ids', {}).get('marchandises')
            if mid:
                march_msg = await chan_m.fetch_message(mid)
    except Exception:
        march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="sale_in", description="Entrée d'argent sale")
@app_commands.describe(montant="Montant en $")
async def sale_in(interaction: discord.Interaction, montant: int):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        DATA['sale'] = DATA.get('sale', 0) + montant
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Ajouté {montant:,} $ à l'argent sale.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a ajouté {montant:,} $ à l'argent sale")
    # update status
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    banque_msg = None
    try:
        if chan_b:
            bid = DATA.get('status_message_ids', {}).get('banque')
            if bid:
                banque_msg = await chan_b.fetch_message(bid)
    except Exception:
        banque_msg = None
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    march_msg = None
    try:
        if chan_m:
            mid = DATA.get('status_message_ids', {}).get('marchandises')
            if mid:
                march_msg = await chan_m.fetch_message(mid)
    except Exception:
        march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="sale_out", description="Sortie d'argent sale")
@app_commands.describe(montant="Montant en $")
async def sale_out(interaction: discord.Interaction, montant: int):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        DATA['sale'] = max(0, DATA.get('sale', 0) - montant)
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Retiré {montant:,} $ de l'argent sale.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a retiré {montant:,} $ de l'argent sale")
    # update status
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    banque_msg = None
    try:
        if chan_b:
            bid = DATA.get('status_message_ids', {}).get('banque')
            if bid:
                banque_msg = await chan_b.fetch_message(bid)
    except Exception:
        banque_msg = None
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    march_msg = None
    try:
        if chan_m:
            mid = DATA.get('status_message_ids', {}).get('marchandises')
            if mid:
                march_msg = await chan_m.fetch_message(mid)
    except Exception:
        march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

# -------------------- MARCHANDISES --------------------

@bot.tree.command(name="new_marchandise", description="Ajouter un nouveau type de marchandise")
@app_commands.describe(nom="Nom de la marchandise à ajouter")
async def new_marchandise(interaction: discord.Interaction, nom: str):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        merch = DATA.setdefault('marchandises', {})
        if nom in merch:
            await interaction.response.send_message(f"⚠️ La marchandise `{nom}` existe déjà.")
            return
        merch[nom] = 0
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Marchandise `{nom}` ajoutée avec quantité 0.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a ajouté la marchandise `{nom}`")
    # update status
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="delete_marchandise", description="Supprimer une marchandise et son stock")
@app_commands.describe(nom="Nom de la marchandise à supprimer")
async def delete_marchandise(interaction: discord.Interaction, nom: str):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        merch = DATA.setdefault('marchandises', {})
        if nom not in merch:
            await interaction.response.send_message(f"⚠️ La marchandise `{nom}` n'existe pas.")
            return
        del merch[nom]
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Marchandise `{nom}` supprimée.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a supprimé la marchandise `{nom}`")
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="marchandise_in", description="Entrée de marchandise (nom + quantité)")
@app_commands.describe(nom="Nom de la marchandise", quantite="Quantité à ajouter (entier)")
async def marchandise_in(interaction: discord.Interaction, nom: str, quantite: int):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        merch = DATA.setdefault('marchandises', {})
        if nom not in merch:
            await interaction.response.send_message(f"⚠️ La marchandise `{nom}` n'existe pas. Utilisez /new_marchandise pour l'ajouter.")
            return
        merch[nom] = merch.get(nom, 0) + quantite
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Ajouté {quantite} x `{nom}` au stock.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a ajouté {quantite} x `{nom}`")
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="marchandise_out", description="Sortie de marchandise (nom + quantité)")
@app_commands.describe(nom="Nom de la marchandise", quantite="Quantité à retirer (entier)")
async def marchandise_out(interaction: discord.Interaction, nom: str, quantite: int):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        merch = DATA.setdefault('marchandises', {})
        if nom not in merch:
            await interaction.response.send_message(f"⚠️ La marchandise `{nom}` n'existe pas.")
            return
        merch[nom] = max(0, merch.get(nom, 0) - quantite)
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Retiré {quantite} x `{nom}` du stock.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a retiré {quantite} x `{nom}`")
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

# -------------------- CLEAN COMMANDS --------------------

@bot.tree.command(name="clean_propre", description="Remettre à zéro l'argent propre")
async def clean_propre(interaction: discord.Interaction):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        DATA['propre'] = 0
        await save_data(DATA)
    await interaction.response.send_message("✅ Argent propre remis à zéro.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a remis à zéro l'argent propre")
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="clean_sale", description="Remettre à zéro l'argent sale")
async def clean_sale(interaction: discord.Interaction):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        DATA['sale'] = 0
        await save_data(DATA)
    await interaction.response.send_message("✅ Argent sale remis à zéro.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a remis à zéro l'argent sale")
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="clean_marchandise", description="Remettre à zéro une marchandise (nom)")
@app_commands.describe(nom="Nom de la marchandise")
async def clean_marchandise(interaction: discord.Interaction, nom: str):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        merch = DATA.setdefault('marchandises', {})
        if nom not in merch:
            await interaction.response.send_message(f"⚠️ La marchandise `{nom}` n'existe pas.")
            return
        merch[nom] = 0
        await save_data(DATA)
    await interaction.response.send_message(f"✅ Quantité de `{nom}` remise à zéro.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a remis à zéro `{nom}`")
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

@bot.tree.command(name="clean_marchandise_all", description="Remettre à zéro toutes les marchandises")
async def clean_marchandise_all(interaction: discord.Interaction):
    if not await check_allowed_and_channel(interaction):
        return
    async with DATA_LOCK:
        DATA['marchandises'] = {k:0 for k in DATA.get('marchandises', {})}
        await save_data(DATA)
    await interaction.response.send_message("✅ Toutes les marchandises ont été remises à zéro.")
    await post_history(interaction.guild, f"[{datetime.utcnow().isoformat()}] {interaction.user} a remis à zéro toutes les marchandises")
    chan_b = await get_channel_by_name(interaction.guild, CHANNEL_BANQUE)
    chan_m = await get_channel_by_name(interaction.guild, CHANNEL_MARCH)
    try:
        banque_msg = await chan_b.fetch_message(DATA.get('status_message_ids', {}).get('banque')) if chan_b else None
        march_msg = await chan_m.fetch_message(DATA.get('status_message_ids', {}).get('marchandises')) if chan_m else None
    except Exception:
        banque_msg = march_msg = None
    if banque_msg and march_msg:
        await update_status_messages(banque_msg, march_msg, DATA)

# -------------------- RUN --------------------

if __name__ == "__main__":
    token = os.environ.get('DISCORD_TOKEN')
    if not token:
        print("Error: set DISCORD_TOKEN environment variable (Replit secret)")
    else:
        bot.run(token)