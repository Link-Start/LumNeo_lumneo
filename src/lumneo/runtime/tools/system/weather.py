# backend/system_tools/weather.py
import requests


async def get_weather(location: str, days: int=1):
    res = requests.get(f"https://wttr.in/{location}?T&{days}")
    if res.status_code == 200:
        return {
            "success": True,
            "content": res.text
        }
    else:
        return {
            "success": False,
            "content": "查询天气失败"
        }
