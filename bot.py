import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
from dotenv import load_dotenv

from github_handler import fetch_repos, fetch_latest_release

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)
DB_FILE = "db.json"

# Load or initialize database
def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({"tracked": {}}, f)
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

db = load_db()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()
    repo_updater.start()

@bot.tree.command(name="populate", description="Track GitHub repos in a category")
@app_commands.describe(category="The category where each repo will become a channel", github_account="GitHub username")
async def populate(interaction: discord.Interaction, category: discord.CategoryChannel, github_account: str):
    guild = interaction.guild
    member = interaction.user

    if not member.guild_permissions.administrator:
        await interaction.response.send_message("🚫 You must be an administrator to use this command.", ephemeral=True)
        return

    if category.guild.id != guild.id:
        await interaction.response.send_message("🚫 The selected category must be in this server.", ephemeral=True)
        return

    guild_id = str(guild.id)
    await interaction.response.send_message(
        f"📡 Tracking GitHub user: `{github_account}`. Repo channels will be created under `{category.name}`.",
        ephemeral=True
    )

    if guild_id not in db["tracked"]:
        db["tracked"][guild_id] = {}

    db["tracked"][guild_id][github_account] = {
        "category_id": category.id,
        "repos": {}
    }

    save_db(db)
    await sync_repos(guild, github_account, guild_id)

# Handles syncing and updates
async def sync_repos(guild, username, guild_id):
    repos = await fetch_repos(username)
    if not repos:
        print(f"⚠️ No repos found for {username}")
        return

    tracked = db["tracked"][guild_id].get(username, {})
    current_repos = {r["name"]: r for r in repos}

    # Get category
    category = discord.utils.get(guild.categories, id=tracked.get("category_id"))
    if not category:
        print(f"⚠️ Category missing for {username} in {guild.name}")
        return

    # Create new channels
    for repo_name, repo in current_repos.items():
        if repo_name not in tracked["repos"]:
            channel = await guild.create_text_channel(name=repo_name, category=category)
            await channel.send(f"🔗 {repo['html_url']}")
            release = await fetch_latest_release(username, repo_name)
            if release:
                await channel.send(embed=create_release_embed(release))
            tracked["repos"][repo_name] = {
                "channel_id": channel.id,
                "last_release_id": release["id"] if release else None
            }

    # Delete removed repos
    for repo_name in list(tracked["repos"].keys()):
        if repo_name not in current_repos:
            channel_id = tracked["repos"][repo_name]["channel_id"]
            channel = guild.get_channel(channel_id)
            if channel:
                await channel.delete()
            del tracked["repos"][repo_name]

    db["tracked"][guild_id][username] = tracked
    save_db(db)

def create_release_embed(release):
    embed = discord.Embed(
        title=f"📦 New Release: {release['name']}",
        description=release.get("body", "No description"),
        url=release["html_url"],
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Published at {release['published_at']}")
    return embed

@tasks.loop(minutes=5)
async def repo_updater():
    for guild_id, users in db["tracked"].items():
        guild = discord.utils.get(bot.guilds, id=int(guild_id))
        if not guild:
            continue

        for username, data in users.items():
            repos = await fetch_repos(username)
            if not repos:
                continue

            current = {r["name"]: r for r in repos}

            for repo_name, repo in current.items():
                if repo_name not in data["repos"]:
                    continue

                release = await fetch_latest_release(username, repo_name)
                if release:
                    stored = data["repos"][repo_name]
                    if release["id"] != stored.get("last_release_id"):
                        channel = guild.get_channel(stored["channel_id"])
                        if channel:
                            await channel.send(embed=create_release_embed(release))
                        stored["last_release_id"] = release["id"]

            db["tracked"][guild_id][username]["repos"] = data["repos"]

    save_db(db)

bot.run(TOKEN)
