# 유피 Discord Bot

한국어 사용자를 위한 AI 대화 Discord 봇입니다. OpenRouter API를 통해 다양한 AI 모델을 활용하며, 대화 기록 저장 및 이미지 인식을 지원합니다.

## 기능

### 메시지 트리거

| 트리거 | 설명 | 모델 |
|--------|------|------|
| `유피야 [메시지]` | 대화 기록을 기억하는 메인 AI 대화. 이미지 첨부 가능 | DeepSeek V4 Flash |
| `멍청한 유피야 [메시지]` | 대화 기록 없는 가벼운 단발성 대화 | Gemma-2 9B |
| `매우 똑똑한 유피야 [메시지]` | 대화 기록 없는 고성능 AI 대화 | Gemini 2.5 Pro |
| `기출 [문항번호]` | 수능/모의고사 기출문제 이미지 직접 조회 | - |
| 수식 입력 | 메시지가 수식으로만 이루어진 경우 자동 계산 | - |

> `유피야`에 이미지를 첨부하면 Vision 모델(Gemini 2.5 Flash-Lite)로 이미지를 분석합니다.

### 슬래시 커맨드

| 커맨드 | 설명 |
|--------|------|
| `/유피야 [내용]` | 대화 기록 기반 AI 대화 |
| `/chat [내용]` | 단발성 AI 대화 |
| `/calc [수식]` | 수식 계산기 |
| `/기출 [과목]` | 과목별 랜덤 기출문제 조회 (`수1` / `수2` / `미적`) |

## 설치 및 실행

### 요구사항

```
discord.py
openai
python-dotenv
```

```bash
pip install discord.py openai python-dotenv
```

### 환경변수 설정

`.env` 파일을 생성하고 아래 값을 입력합니다.

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
OPENROUTER_API_KEY=your_openrouter_api_key
```

### 실행

```bash
python bot.py
```

## 기술 스택

- **언어:** Python
- **Discord 라이브러리:** discord.py
- **AI API:** OpenRouter API
- **데이터베이스:** SQLite (`chattings.db`) — 사용자별 대화 기록 저장
