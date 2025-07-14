import os 
import discord
from discord.ext import commands
import requests
import logging
from dotenv import load_dotenv


# ----- Load environment variables from .env file -----
load_dotenv()
RIOT_API_KEY = os.getenv('RIOT_API_KEY')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
# print(f"RIOT_API_KEY: {RIOT_API_KEY}")  # Debugging line to check if the key is loaded
# print(f"DISCORD_TOKEN: {DISCORD_TOKEN}")  # Debugging line to check if the token is loaded

# ----- Basic Discord setup -----
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents) # Set the command prefix to '!' for the bot

# ----- Remove default help command -----
bot.remove_command('help')

# ----- Region mapping (simple, extendable) -----
VALID_PLATFORM_REGIONS = {
    'na1': 'americas',
    'br1': 'americas',
    'lan1': 'americas',
    'las1': 'americas',
    'oc1': 'americas',
    'euw1': 'europe',
    'eune1': 'europe',
    'tr1': 'europe',
    'ru': 'europe',
    'kr': 'asia',
    'jp1': 'asia',
}

# riot uses two kinds of regions:
# - routing regions for account-v1 (americas, europe, asia)
# - platform regions for summoner-v4, league-v4 (na1, euw1, etc.)

ROUTING_MAP = {
    'na1': 'americas',
    'br1': 'americas',
    'lan1': 'americas',
    'las1': 'americas',
    'oc1': 'americas',
    'euw1': 'europe',
    'eune1': 'europe',
    'tr1': 'europe',
    'ru': 'europe',
    'kr': 'asia',
    'jp1': 'asia',
}

# ----- Check if API keys are set -----
def validate_riot_key():
    url = "https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/zeno/csx"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        logging.info("✅ Riot API key valid")
    elif r.status_code == 403:
        logging.error("❌ Riot API key rejected: 403 Forbidden")
    elif r.status_code == 401:
        logging.error("❌ Riot API key unauthorized: 401")
    elif r.status_code == 429:
        logging.error("⚠️ Riot API rate limited: 429 Too Many Requests")
    else:
        logging.error(f"Riot key check failed with status code {r.status_code}")

# ----- Discord starrtup -----
@bot.event
async def on_ready():
    logging.info(f"✅ Logged in as {bot.user}")
    validate_riot_key()  

# ----- utils: riot api wrappers -----
def get_account_by_riot_id(platform_region, game_name, tag_line):
    routing_region = ROUTING_MAP.get(platform_region)
    if not routing_region:
        logging.warning(f"invalid region: {platform_region}")
        return None
    url = f"https://{routing_region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        logging.warning(f"failed account lookup {game_name}#{tag_line} @ {platform_region} ({r.status_code})")
    return r.json() if r.status_code == 200 else None

def get_summoner_by_puuid(platform_region, puuid):
    url = f"https://{platform_region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    r = requests.get(url, headers=headers)
    return r.json() if r.status_code == 200 else None

def get_ranked_data(platform_region, summoner_id):
    url = f"https://{platform_region}.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    headers = {"X-Riot-Token": RIOT_API_KEY}
    r = requests.get(url, headers=headers)
    return r.json() if r.status_code == 200 else None

# ----- Commands ----- 
@bot.command()
async def summoner_data(ctx, region='euw1', *, riot_id: str):
    """
    Get summoner information by name.

    Usage: !summoner_data <region> username#tagline
    Example: !summoner_data na1 Faker#KR1
    If region omitted, defaults to euw1.
    
    """

    # ----- Clean Inputs -----
    region = region.lower()
    if region not in VALID_PLATFORM_REGIONS:
        await ctx.send(f"Invalid region '{region}'. Valid regions are: {', '.join(VALID_PLATFORM_REGIONS)}.")
        return
    
    if '#' not in riot_id:
        await ctx.send("Please provide a valid Riot ID in the format 'username#tagline'.")
        return
    
    game_name, tag_line = riot_id.split('#', 1)


    # ----- Get summoner info by riot id -----
    account = get_account_by_riot_id(region, game_name, tag_line)
    if not account:
        await ctx.send(f"account lookup failed for {riot_id} @ {region}")
        return
    if 'puuid' not in account:
        await ctx.send(f"account found but no puuid returned. response: {account}")
        return
    
    summoner = get_summoner_by_puuid(region, account['puuid'])
    if not summoner or 'id' not in summoner:
        await ctx.send(f"couldn’t fetch summoner data for {riot_id}")
        return

    ranked = get_ranked_data(region, summoner['id'])
    if not ranked:
        await ctx.send(f"no ranked data found for {riot_id}")
        return
    
    embed = discord.Embed(title=f"{summoner['name']}'s Ranked Stats")

    found = False
    for queue in ranked:
        qtype = queue["queueType"]
        tier = queue["tier"].capitalize()
        rank = queue["rank"]
        lp = queue["leaguePoints"]
        wins = queue["wins"]
        losses = queue["losses"]
        winrate = round(100 * wins / (wins + losses), 1)

        if qtype == "RANKED_SOLO_5x5":
            embed.add_field(
                name="Solo Queue",
                value=f"{tier} {rank} - {lp} LP\nWinrate: {winrate}% ({wins}W / {losses}L)",
                inline=False
            )
            found = True
        elif qtype == "RANKED_FLEX_SR":
            embed.add_field(
                name="Flex Queue",
                value=f"{tier} {rank} - {lp} LP\nWinrate: {winrate}% ({wins}W / {losses}L)",
                inline=False
            )
            found = True
    if not found:
        await ctx.send(f"{riot_id} has no solo or flex ranked data")
        return
    
    await ctx.send(embed=embed)


@bot.command(name='help')
async def custom_help(ctx):
    embed = discord.Embed(title="League Bot Commands", color=discord.Color.blue())
    embed.add_field(
        name="!summoner_data <region> <username#tagline>", 
        value="Get ranked stats for a league player.\nExample: `!summoner_data kr1 Faker#KR1`", 
        inline=False
    )
    # ----- Add more commands here as needed -----
    await ctx.send(embed=embed)

try:
    bot.run(DISCORD_TOKEN)
except discord.LoginFailure:
    logging.error("❌ Invalid Discord token. Please check your .env file.")
except Exception as e:
    logging.error(f"❌ An error occurred: {e}")