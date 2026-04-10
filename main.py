import os

import discord
from dotenv import load_dotenv
from google import genai
from google.genai import types


PREFIX = "유피야"
MODEL_NAME = "gemma-4-26b-a4b-it"
DISCORD_MESSAGE_LIMIT = 2000


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = []
    current_length = 0

    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append("".join(current))
                current = []
                current_length = 0

            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            continue

        if current_length + len(line) > limit:
            chunks.append("".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += len(line)

    if current:
        chunks.append("".join(current))

    return chunks


load_dotenv()

discord_token = os.getenv("DISCORD_BOT_TOKEN")
gemini_api_key = os.getenv("GEMINI_API_KEY")

if not discord_token:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env.")

if not gemini_api_key:
    raise RuntimeError("GEMINI_API_KEY is not set in .env.")


gemini_client = genai.Client(api_key=gemini_api_key)

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"{bot.user} is connected.")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    if not message.content.startswith(PREFIX):
        return

    user_prompt = message.content[len(PREFIX) :].strip()
    if not user_prompt:
        await message.channel.send("안녕!")
        return

    async with message.channel.typing():
        try:
            response = gemini_client.models.generate_content(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction="너는 디스코드에서 대화하는 챗봇인 '유피'야. 귀여운 아이가 된 것 같은 말투로 사용자에게 대답해. 특별한 이유가 없는 한 이모지는 사용하지 마."
                ),
                contents=user_prompt,
            )
            reply_text = (response.text or "").strip()
        except Exception as exc:
            await message.channel.send(f"Gemini API 오류: {exc}")
            return

    if not reply_text:
        await message.channel.send(
            "다시 한 번 보내주세요."
        )
        return

    for chunk in split_message(reply_text):
        await message.channel.send(chunk)


bot.run(discord_token)
