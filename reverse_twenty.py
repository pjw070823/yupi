import random
import re
import time
from collections import deque
from dataclasses import dataclass, field


GAME_TIMEOUT_SECONDS = 60 * 60
MAX_WORD_LENGTH = 20
MAX_GENERATION_ATTEMPTS = 3
RECENT_ANSWER_LIMIT = 50

INVALID_WORD_MESSAGE = '올바르지 않은 제시어입니다.'

# 정답을 뽑을 때 AI에게 던져 줄 주제. 매번 다른 주제를 줘서 정답이 한쪽으로 쏠리지 않게 한다.
ANSWER_THEMES = [
    '길거리 음식', '한식 요리', '디저트와 간식', '과일과 채소', '음료',
    '포유류', '바다 생물', '곤충과 벌레', '새', '파충류와 양서류',
    '주방용품', '가전제품', '가구', '문구류', '욕실용품', '옷과 패션 소품', '운동 기구',
    '탈것', '악기', '장난감과 놀이', '전자기기',
    '건물과 시설', '자연 지형', '날씨와 자연 현상', '우주와 천체', '식물과 꽃',
    '직업', '스포츠 종목', '학교 생활', '명절과 기념일', '병원과 몸', '취미 활동',
    '동화와 전설 속 존재', '보석과 광물', '캠핑과 여행', '공사장과 공구',
]

# AI 호출이 실패했을 때만 쓰는 예비 정답 목록
FALLBACK_ANSWER_WORDS = [
    '햄버거', '떡볶이', '붕어빵', '팝콘', '수박',
    '펭귄', '기린', '돌고래', '햄스터', '거북이',
    '냉장고', '우산', '안경', '자전거', '지하철', '칫솔', '에어컨',
    '도서관', '놀이공원', '찜질방', '무지개', '눈사람', '화산', '선인장',
    '소방관', '요리사', '피아노', '크리스마스', '여름방학', '숙제',
]

# 글자 수, 초성, 받침 등 단어의 '표기'에 대한 질문을 걸러내기 위한 패턴
LETTER_HINT_PATTERNS = [
    r'글자', r'음절', r'초성', r'중성', r'종성', r'받침', r'자음', r'모음',
    r'철자', r'스펠링', r'알파벳',
    r'[ㄱ-ㅎㅏ-ㅣ]', r'(으)?로\s*시작', r'(으)?로\s*끝',
]

ANSWER_PROMPT = """너는 '리버스 스무고개' 게임의 출제자야. 참가자들이 맞혀야 할 정답 단어를 딱 하나 정해 줘.

[게임 방식]
참가자들이 아무 단어나 제시하면, 진행자는 그 단어와 정답 모두에 해당하는 가장 구체적인 공통점을 예/아니오 질문으로 알려 줘.
(예: 정답이 햄버거일 때 '피자'를 제시하면 "패스트푸드인가요?")
참가자들은 이 질문들을 단서로 삼아 범위를 좁혀 가며 정답을 추리해.

[이번 주제]
「{theme}」 주제 안에서, 또는 이 주제에서 자유롭게 연상되는 쪽으로 골라.

[좋은 정답의 조건]
1. 한국 초등학교 고학년 이상이면 누구나 아는 일반 명사여야 해. 한 번 들으면 "아 그거!" 하고 바로 떠올릴 수 있어야 해.
2. 뚜렷한 특징이 여러 개 있어서, 다른 단어들과 비교하며 좁혀 갈 수 있어야 해. 공통점 질문이 다양하게 나올 수 있는 단어가 좋아.
3. 너무 뻔한 단어(사과, 고양이, 강아지, 자동차, 컴퓨터, 학교, 물 등)는 피하고, 조금 의외지만 친숙한 단어를 골라서 게임을 재미있게 만들어. 창의적으로 골라.
4. 너무 넓은 범주 이름(음식, 동물, 가구 등)이나 너무 전문적이거나 드문 단어는 안 돼.
5. 고유명사(사람 이름, 브랜드, 지명, 작품 제목)와 비속어는 안 돼.
6. 띄어쓰기 없는 한 단어로, 한글로만 써. 합성어(예: 붕어빵, 회전목마)는 괜찮아.
7. 최근에 이미 나온 정답은 다시 쓰지 마: {recent}

[출력 형식]
설명, 따옴표, 문장부호 없이 정답 단어 하나만 출력해."""

QUESTION_PROMPT = """너는 '리버스 스무고개' 게임의 진행자야.
정답 단어는 「{answer}」이고, 게임이 끝날 때까지 절대 바뀌지 않아.

[규칙]
1. 사용자가 단어 하나를 제시하면, 제시 단어와 정답 단어 두 가지 모두에 대해 "네"라고 답할 수 있는 예/아니오 질문을 딱 하나 만들어.
2. 질문은 두 단어가 공통으로 속하는 범주·특징 중에서 **가장 세부적이고 구체적인 것**을 골라야 해.
   - 정답: 햄버거, 제시 단어: 피자 -> 패스트푸드인가요?
   - 정답: 냉장고, 제시 단어: 세탁기 -> 가전제품인가요?
   - 정답: 냉장고, 제시 단어: 코딱지 -> 사물인가요?
   두 단어가 가까울수록 좁은 범주, 멀수록 넓은 범주가 나와야 해. 더 구체적인 공통점이 있는데 넓은 범주로 뭉뚱그리지 마.
3. 단어의 표기에 대한 질문은 절대 금지야. 글자 수, 첫 글자, 초성, 받침, 특정 글자 포함 여부, 발음, 철자 같은 것은 묻지 마.
4. 질문 안에 정답 단어나 정답 단어의 일부를 절대 쓰지 마. 정답을 직접 암시하는 표현도 쓰지 마.

[정답 판정]
제시 단어가 정답과 사실상 같은 대상을 가리키면 질문 대신 정확히 「정답」이라고만 출력해. 다음은 모두 정답이야.
- 동의어, 흔히 쓰는 다른 이름: 휴대폰 = 핸드폰 = 스마트폰, 자전거 = 바이크(자전거를 뜻할 때)
- 줄임말과 본딧말: 에어컨 = 에어컨디셔너, 지하철 = 전철, 노트북 = 노트북컴퓨터
- 외래어·영어 표기, 한자어·고유어 차이: 냉장고 = refrigerator, 달걀 = 계란
- 띄어쓰기·맞춤법이 조금 틀린 같은 말: 떡볶이 = 떡뽁이
하지만 정답의 하위 종류나 상위 범주, 비슷하지만 다른 물건은 정답이 아니야.
(예: 정답 냉장고에 김치냉장고·가전제품·냉동고는 정답 아님)

[올바르지 않은 제시어]
제시 단어가 다음에 해당하면 질문 대신 정확히 「무효」라고만 출력해.
- 뜻이 없는 문자열, 오타가 심해 무슨 말인지 알 수 없는 것
- 단어가 아닌 문장이나 질문, 명령 (예: "정답 알려줘", "이거 뭐야")
- 비속어·욕설
단, 흔하지 않아도 실제로 있는 단어라면 무효가 아니야.

[출력 형식]
설명, 따옴표, 머리말 없이 다음 중 하나만 출력해.
- 「정답」
- 「무효」
- "~인가요?", "~나요?" 형태의 질문 한 문장"""


@dataclass
class ReverseTwentyGame:
    answer: str
    started_by: int
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    history: dict[str, str] = field(default_factory=dict)

    @property
    def attempts(self) -> int:
        return len(self.history)

    def is_expired(self) -> bool:
        return time.time() - self.last_activity > GAME_TIMEOUT_SECONDS


# 채널 ID -> 진행 중인 게임. 같은 채널의 누구나 제시어를 낼 수 있다.
games: dict[int, ReverseTwentyGame] = {}
recent_answers: deque[str] = deque(maxlen=RECENT_ANSWER_LIMIT)


def normalize_word(word: str) -> str:
    return re.sub(r'\s+', '', word).lower()


def strip_wrapping(text: str) -> str:
    return text.strip().strip('"\'「」“”`*.。 ').strip()


def is_well_formed_word(word: str) -> bool:
    return 0 < len(word) <= MAX_WORD_LENGTH and re.fullmatch(r'[가-힣A-Za-z0-9 \-]+', word) is not None


async def generate_answer(client, model: str) -> str:
    for _ in range(MAX_GENERATION_ATTEMPTS):
        try:
            response = await client.chat.send_async(
                model=model,
                temperature=1.1,
                messages=[
                    {"role": "system", "content": ANSWER_PROMPT.format(
                        theme=random.choice(ANSWER_THEMES),
                        recent=', '.join(recent_answers) or '없음',
                    )},
                    {"role": "user", "content": "정답 단어를 하나 정해 줘."},
                ],
            )
        except Exception:
            continue

        lines = (response.choices[0].message.content or "").strip().splitlines()
        word = strip_wrapping(lines[0]) if lines else ""
        if re.fullmatch(r'[가-힣]{2,10}', word) and word not in recent_answers:
            return word

    candidates = [word for word in FALLBACK_ANSWER_WORDS if word not in recent_answers]
    return random.choice(candidates or FALLBACK_ANSWER_WORDS)


async def start_game(client, model: str, channel_id: int, user_id: int) -> ReverseTwentyGame:
    answer = await generate_answer(client, model)
    recent_answers.append(answer)
    game = ReverseTwentyGame(answer=answer, started_by=user_id)
    games[channel_id] = game
    return game


def get_game(channel_id: int) -> ReverseTwentyGame | None:
    game = games.get(channel_id)
    if game and game.is_expired():
        del games[channel_id]
        return None
    return game


def end_game(channel_id: int) -> ReverseTwentyGame | None:
    return games.pop(channel_id, None)


def is_valid_question(question: str, answer: str) -> bool:
    if not question or len(question) > 100 or '\n' in question:
        return False

    compact = normalize_word(question)
    target = normalize_word(answer)

    # 정답 단어 또는 정답의 두 글자 이상 조각이 질문에 들어가면 정답 유출
    for size in range(2, len(target) + 1):
        for start in range(len(target) - size + 1):
            if target[start:start + size] in compact:
                return False
    if len(target) == 1 and target in compact:
        return False

    return not any(re.search(pattern, question) for pattern in LETTER_HINT_PATTERNS)


def clean_question(raw: str) -> str:
    text = strip_wrapping(raw)
    text = re.sub(r'^(질문|Q)\s*[:.]\s*', '', text)
    if text and not text.endswith('?'):
        text += '?'
    return text


async def ask_question(client, model: str, game: ReverseTwentyGame, word: str) -> tuple[str, str | None]:
    """제시어를 판정한다. ('correct' | 'invalid' | 'question' | 'failed', 질문) 을 돌려준다."""
    game.last_activity = time.time()

    if not is_well_formed_word(word):
        return 'invalid', None

    key = normalize_word(word)
    if key == normalize_word(game.answer):
        return 'correct', None
    if key in game.history:
        return 'question', game.history[key]

    for _ in range(MAX_GENERATION_ATTEMPTS):
        response = await client.chat.send_async(
            model=model,
            temperature=0.4,
            messages=[
                {"role": "system", "content": QUESTION_PROMPT.format(answer=game.answer)},
                {"role": "user", "content": f"제시 단어: {word}"},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        verdict = strip_wrapping(raw)

        if verdict == '정답':
            return 'correct', None
        if verdict == '무효':
            return 'invalid', None

        question = clean_question(raw)
        if is_valid_question(question, game.answer):
            game.history[key] = question
            return 'question', question

    return 'failed', None
