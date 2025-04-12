import aiohttp
import asyncio

GITHUB_API = "https://api.github.com/users/{username}/repos"
RELEASES_API = "https://api.github.com/repos/{username}/{repo}/releases"

async def fetch_repos(username):
    async with aiohttp.ClientSession() as session:
        async with session.get(GITHUB_API.format(username=username)) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

async def fetch_latest_release(username, repo):
    async with aiohttp.ClientSession() as session:
        async with session.get(RELEASES_API.format(username=username, repo=repo)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data[0] if data else None
            return None
