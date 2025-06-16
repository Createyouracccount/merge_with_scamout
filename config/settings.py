import os
from pathlib import Path

# .env 파일 로드 추가
try:
    from dotenv import load_dotenv
    # 프로젝트 루트의 .env 파일 로드
    BASE_DIR = Path(__file__).resolve().parent.parent
    dotenv_path = BASE_DIR / '.env'
    load_dotenv(dotenv_path)
    print(f"✅ .env 파일 로드됨: {dotenv_path}")
except ImportError:
    print("⚠️ python-dotenv가 설치되지 않음")
except Exception as e:
    print(f"⚠️ .env 로드 실패: {e}")

# 프로젝트 루트 디렉토리
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    """애플리케이션 설정"""
    
    # STT 설정 (ReturnZero)
    RETURNZERO_CLIENT_ID = os.getenv("RETURNZERO_CLIENT_ID", "")
    RETURNZERO_CLIENT_SECRET = os.getenv("RETURNZERO_CLIENT_SECRET", "")
    
    # TTS 설정 (ElevenLabs)
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
    
    # 하드코딩으로 강제 설정 (환경변수 무시)
    TTS_VOICE_ID = "uyVNoMrnUku1dZyVEXwD"
    TTS_MODEL = "eleven_flash_v2_5" # eleven_multilingual_v2
    TTS_OPTIMIZE_LATENCY = 1

   # Gemini AI 설정 (새로 추가)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
    GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "10"))
    
    # AI 응답 설정
    USE_AI_ASSISTANT = os.getenv("USE_AI_ASSISTANT", "True").lower() == "true"
    AI_RESPONSE_MAX_LENGTH = int(os.getenv("AI_RESPONSE_MAX_LENGTH", "300"))
    
    # 오디오 설정
    SAMPLE_RATE = 16000
    CHUNK_SIZE = int(SAMPLE_RATE / 10)  # 100ms
    CHANNELS = 1
    FORMAT = "paInt16"
    
    # 시스템 설정
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # 상담 설정
    MAX_SILENCE_DURATION = 3.0  # 3초 무음 시 응답
    MAX_CONVERSATION_TURNS = 20  # 최대 대화 턴
    SESSION_TIMEOUT = 1800  # 30분 세션 타임아웃

    # 침묵 감지 설정
    SILENCE_DETECTION_ENABLED = True
    SILENCE_TIMEOUT = 5.0  # 5초
    SKIP_FIRST_INTERACTION = True

settings = Settings()

# 디버깅용 출력
if __name__ == "__main__":
    print(f"TTS_VOICE_ID: '{settings.TTS_VOICE_ID}'")
    print(f"길이: {len(settings.TTS_VOICE_ID)}")
    print(f"공백 포함: {' ' in settings.TTS_VOICE_ID}")