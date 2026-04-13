from discord import app_commands
from discord.ext import commands
from discord import Intents
from google import genai
from google.genai import types # type: ignore
from math import *
import random
import json
import os
from dotenv import load_dotenv
import sqlite3

load_dotenv()

MAIN_MODEL_NAME = "gemma-4-26b-a4b-it" # "gemma-4-e4b-it"
DISCORD_MESSAGE_LIMIT = 2000

bot = commands.Bot(command_prefix='/', intents=Intents.all())
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
connection = sqlite3.connect('chattings.db')
cursor = connection.cursor()

math1 = ['22예시10', '22예시13', '22예시15', '22예시20', '22예시21', '220609', '220610', '220612', '220613', '220615', '220621', '220910', '220912', '220913', '220915', '220921', '221109', '221111', '221113', '221115', '221121', '230610', '230612', '230613', '230615', '230621', '230909', '230911', '230913', '230915', '230921', '231109', '231111', '231113', '231115', '231121', '240609', '240612', '240613', '240615', '240621', '240909', '240912', '240914', '240920', '240921', '241109', '241111', '241113', '241115', '241121', '250610', '250612', '250614', '250620', '250622', '250910', '250912', '250914', '250920', '250922', '251110', '251112', '251114', '251120', '251122', '260610', '260612', '260614', '260620', '260622', '260910', '260912', '260914', '260920', '260922']
math2 = ['22예시09', '22예시11', '22예시12', '22예시14', '22예시22', '220611', '220614', '220620', '220622', '220909', '220911', '220914', '220920', '220922', '221110', '221112', '221114', '221120', '221122', '230609', '230611', '230614', '230620', '230622', '230910', '230912', '230914', '230920', '230922', '231110', '231112', '231114', '231120', '231122', '240610', '240611', '240614', '240620', '240622', '240910', '240911', '240913', '240915', '240922', '241110', '241112', '241114', '241120', '241122', '250609', '250611', '250613', '250615', '250621', '250909', '250911', '250913', '250915', '250921', '251109', '251111', '251113', '251115', '251121', '260609', '260611', '260613', '260615', '260621', '260909', '260911', '260913', '260915', '260921']
calculus = ['22예시27미', '22예시28미', '22예시29미', '22예시30미', '220627미', '220628미', '220629미', '220630미', '220927미', '220928미', '220929미', '220930미', '221127미', '221128미', '221129미', '221130미', '230627미', '230628미', '230629미', '230630미', '230927미', '230928미', '230929미', '230930미', '231127미', '231128미', '231129미', '231130미', '240627미', '240628미', '240629미', '240630미', '240927미', '240928미', '240929미', '240930미', '241127미', '241128미', '241129미', '241130미', '250627미', '250628미', '250629미', '250630미', '250927미', '250928미', '250929미', '250930미', '251127미', '251128미', '251129미', '251130미', '260627미', '260628미', '260629미', '260630미', '260927미', '260928미', '260929미', '260930미']

equationComponents = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '+', '-', '*', '/', '^' '(', ')', '&', '|', '!', '>', '<', '=']


def consistsOfEquation(text: str) -> bool:
    for c in text:
        if c not in equationComponents:
            return False
    return True


def init_db():
    cursor.execute("PRAGMA table_info(chat_history)")
    columns = [row[1] for row in cursor.fetchall()]

    if not columns:
        cursor.execute("""
            CREATE TABLE chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        connection.commit()
        return

    expected_columns = ['id', 'user_id', 'role', 'message', 'created_at']
    if columns == expected_columns:
        return

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    if columns == ['user_id', 'message', 'created_at']:
        cursor.execute("""
            INSERT INTO chat_history_new (user_id, role, message, created_at)
            SELECT
                user_id,
                CASE WHEN user_id = 0 THEN 'bot' ELSE 'user' END,
                message,
                created_at
            FROM chat_history
        """)

    cursor.execute("DROP TABLE chat_history")
    cursor.execute("ALTER TABLE chat_history_new RENAME TO chat_history")
    connection.commit()


def save_chat_message(user_id: int, role: str, message: str, created_at: str):
    cursor.execute(
        "INSERT INTO chat_history (user_id, role, message, created_at) VALUES (?, ?, ?, ?)",
        (user_id, role, message, created_at),
    )
    connection.commit()


def load_recent_history(user_id: int, limit: int = 10):
    cursor.execute(
        """
        SELECT role, message, created_at
        FROM chat_history
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = cursor.fetchall()
    rows.reverse()
    return rows

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s).')
    except Exception as e:
        print(f'Sync failed: {e}')
    init_db()

        
@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    if msg.content.startswith('기출 '):
        qNum = msg.content[3:]
        if len(qNum) > 7: return
        qPre = qNum[:4]
        if int(qNum[4:6]) > 22 and 22 <= int(qNum[:2]) <= 27 and qNum[-1] not in ['미', '기', '확', '가', '나', 'A', 'B']: qNum += '미' 
        if qPre[2:] in ['03', '04', '05', '07', '08', '10']:
            await msg.channel.send('https://pastkice.kr/question_image/ooe/grade3/mat/'+qPre+'/'+qNum+'.png')
        else: await msg.channel.send('https://pastkice.kr/question_image/kice/mat/'+qPre+'/'+qNum+'.png')


    elif msg.content.startswith('그래프 '):
        pass

    
    elif msg.content.startswith('똑똑한 유피야 '):
        text = msg.content[8:]
        if len(text) > 500:
            await msg.channel.send('메시지가 너무 길어요...')
        else:
            respond = client.models.generate_content(
                model= random.choice(["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3-flash"]),
                config=types.GenerateContentConfig(
                    temperature=1,
                    system_instruction = "너는 디스코드 챗봇인 유피이야. 너는 여자아이야. 사용자가 질문하거나 말하는 내용에 귀여운 말투로 대답해. 질문한 내용은 성실히 대답해.사용자에게 역질문은 하지마. 사용자가 골라달라하는거 같으면 아무거나 골라. 이모지는 사용하지 마. 어머 라는 감탄사는 쓰지 마. 대화형 챗봇인만큼 길지 않게 대답해.검색이라는 단어가 포함되면 무조건 검색 도구를 써.",
                    tools = [types.Tool(google_search=types.GoogleSearch()) , types.Tool(url_context=types.UrlContext()) , types.Tool(code_execution=types.ToolCodeExecution)]
                ),
                contents="다음 줄부터가 사용자의 입력이야.\n"+text
           )
            await msg.channel.send(respond.text)
        
        
    elif msg.content.startswith('유피야'):
        text = msg.content[3:].strip()
        if text == '':
            await msg.channel.send('안녕! '+msg.author.name)
        if len(text) > 500:
            await msg.channel.send('메시지가 너무 길어요...')
        else:
            created_at = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            save_chat_message(msg.author.id, "user", text, created_at)
            rows = load_recent_history(msg.author.id)

            api_content = msg.author.name + " 님과 이전 대화 내역 :\n"
            api_content += "\n".join(
                [f"[{row[2]}] {'사용자' if row[0] == 'user' else '유피'} : {row[1]}" for row in rows]
            )
            
            async with msg.channel.typing():
                try:
                    respond = client.models.generate_content(
                        model=MAIN_MODEL_NAME,
                        # config=types.GenerateContentConfig(
                        #     temperature=1
                        # ),
                        config=types.GenerateContentConfig(
                            system_instruction=
                            "너는 디스코드 챗봇인 유피이야.너는 여자아이야.대화 내역에서 사용자가 마지막으로 말한 내용에 대해 대답해.사용자가 질문하거나 말하는 내용에 귀여운 말투로 대답해.질문한 내용은 성실히 대답해.사용자에게 역질문은 하지마.사용자가 골라달라하는거 같으면 아무거나 골라.이모지는 사용하지 마.대화형 챗봇인만큼 길지 않게 대답해."
                            #"너는 디스코드에서 대화하는 챗봇인 '유피'야. 귀여운 아이가 된 것 같은 말투로 사용자에게 대답해. 특별한 이유가 없는 한 이모지는 사용하지 마."
                        ),
                        contents= api_content,
                    )
                    respond = (respond.text or "").strip()
                except Exception as exc:
                    await msg.channel.send(f"Gemini API 오류: {exc}")
                    return
            await msg.channel.send(respond)
            save_chat_message(msg.author.id, "bot", respond, created_at)


    elif msg.content.startswith('매우 똑똑한 유피야 '):
        text = msg.content[11:]
        if len(text) > 500:
            await msg.channel.send('메시지가 너무 길어요...')
        else:
            try:
                respond = client.models.generate_content(
                    model="gemini-3-pro-preview",
                    config=types.GenerateContentConfig(
                        temperature=1,
                        tools = [types.Tool(google_search=types.GoogleSearch()) , types.Tool(url_context=types.UrlContext()) , types.Tool(code_execution=types.ToolCodeExecution)]
                    ),
                    contents="너는 디스코드 채팅 앱의 챗봇인 유피이야. 사용자가 질문하거나 말하는 내용에 길지 않게  대답해. 다음 줄부터가 사용자의 입력이야.\n"+text
                )
                await msg.channel.send(respond.text)
            except Exception as exc:
                await msg.channel.send('오류가 났어요. 다시 시도해주세요.\n' + str(exc))


    elif consistsOfEquation(msg.content):
        equation = msg.content.relace('=', '==').replace('!=', 'neq').replace('!', ' not ').replace('neq', '!=').replace('^', '**')
        try:
            resultOfEquation = eval(equation)
            await msg.channel.send(resultOfEquation)
        except:
            await msg.channel.send('수식에 오류가 있어요.')


@bot.tree.command(name='기출', description='기출')
@app_commands.describe(subject='수1, 수2, 미적, 문항번호')
async def 기출(interaction, subject: str):
    rlcnf_num = ''
    if subject == '수1': rlcnf_num = random.choice(math1)
    if subject == '수2': rlcnf_num = random.choice(math2)
    if subject == '미적': rlcnf_num = random.choice(calculus)
    else: rlcnf_num = subject
    
    qNum = rlcnf_num
    if len(qNum) > 7: return
    qPre = qNum[:4]
    if int(qNum[4:6]) > 22 and qNum[-1] not in ['미', '기', '확', '가', '나', 'A', 'B']: qNum += '미' 
    if qPre[2:] in ['03', '04', '05', '07', '08', '10']:
        await interaction.response.send_message('https://pastkice.kr/question_image/ooe/grade3/mat/'+qPre+'/'+qNum+'.png')
    else: await interaction.response.send_message('https://pastkice.kr/question_image/kice/mat/'+qPre+'/'+qNum+'.png') 

@bot.tree.command(name='calc', description='계산하기')
@app_commands.describe(text1='계산할 식')
async def calc(interaction, text1: str):
    respond = ''
    baned = False
    ban_list = ['print', 'input', 'eval', 'bot', 'client', 'return', 'break', 'on_message', 'chat', 'calc']
    for element in ban_list:
        if element in text1:
            baned = True
    if baned:
        await interaction.response.send_message('금지어가 포함되어 있어요.')
        return 
    try:
        respond = eval(text1)
    except Exception as e:
        respond = '잘못된 수식이에요'
    await interaction.response.send_message(respond)
    
@bot.tree.command(name='chat', description='AI와 대화하기')
@app_commands.describe(text='내용')
async def chat(interaction, text: str):
    if len(text) > 500:
        await interaction.response.send_message('메시지가 너무 길어요...')
    else:
        respond = client.models.generate_content(
            model=MAIN_MODEL_NAME,
            config=types.GenerateContentConfig(
                temperature=2
            ),
            contents="너는 디스코드 채팅 앱의 챗봇인 유피이야. 사용자가 질문하거나 말하는 내용을 정확히 대답해. 다음 줄부터가 사용자의 입력이야.\n"+text
        )
        await interaction.response.send_message(respond.text)


@bot.tree.command(name='유피야', description='유피와 대화하기')
@app_commands.describe(text='내용')
async def yupiya(interaction, text: str):
    if len(text) > 500:
        await interaction.response.send_message('메시지가 너무 길어요...')
    else:
        if text == '':
            await interaction.response.send_message('안녕! '+ interaction.user.name)
        if len(text) > 500:
            await interaction.response.send_message('메시지가 너무 길어요...')
        else:
            await interaction.response.send_message('잠시 기다려주세요')

            created_at = interaction.created_at.strftime("%Y-%m-%d %H:%M:%S")
            save_chat_message(interaction.user.id, "user", text, created_at)
            rows = load_recent_history(interaction.user.id)

            api_content = interaction.user.name + " 님과 이전 대화 내역 :\n"
            api_content += "\n".join(
                [f"[{row[2]}] {'사용자' if row[0] == 'user' else '유피'} : {row[1]}" for row in rows]
            )
            
            try:
                respond = client.models.generate_content(
                    model=MAIN_MODEL_NAME,
                    # config=types.GenerateContentConfig(
                    #     temperature=1
                    # ),
                    config=types.GenerateContentConfig(
                        system_instruction=
                        "너는 디스코드 챗봇인 유피이야.너는 여자아이야.대화 내역에서 사용자가 마지막으로 말한 내용에 대해 대답해.사용자가 질문하거나 말하는 내용에 귀여운 말투로 대답해.질문한 내용은 성실히 대답해.사용자에게 역질문은 하지마.사용자가 골라달라하는거 같으면 아무거나 골라.이모지는 사용하지 마.대화형 챗봇인만큼 길지 않게 대답해."
                        #"너는 디스코드에서 대화하는 챗봇인 '유피'야. 귀여운 아이가 된 것 같은 말투로 사용자에게 대답해. 특별한 이유가 없는 한 이모지는 사용하지 마."
                    ),
                    contents= api_content,
                )
                respond = (respond.text or "").strip()
            except Exception as exc:
                await interaction.edit_original_response(content=f"Gemini API 오류: {exc}")
                return
            await interaction.edit_original_response(content=respond)
            save_chat_message(interaction.user.id, "bot", respond, created_at)


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
