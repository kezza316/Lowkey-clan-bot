import aiohttp

HISCORES_URL = "https://secure.runescape.com/m=hiscore_oldschool/index_lite.ws?player="


async def get_total_level(rsn: str):
    url = HISCORES_URL + rsn.replace(" ", "%20")

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            if r.status != 200:
                return None

            data = await r.text()

    try:
        return int(data.splitlines()[0].split(",")[1])
    except:
        return None
