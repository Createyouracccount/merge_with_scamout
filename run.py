#!/usr/bin/env python3
"""
보이스피싱 상담 시스템 실행 스크립트
환경 설정 및 의존성 확인 후 메인 애플리케이션 실행
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Python 버전 확인"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 이상이 필요합니다.")
        print(f"현재 버전: {sys.version}")
        sys.exit(1)
    
    print(f"✅ Python 버전: {sys.version}")

def check_dependencies():
    """필수 패키지 설치 확인"""
    print("📦 패키지 의존성 확인 중...")
    
    required_packages = [
        'pyaudio',
        'grpc', 
        'elevenlabs',
        'langgraph',
        'pydub',

        'requests'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} (누락)")
    
    if missing_packages:
        print(f"\n❌ 누락된 패키지들: {', '.join(missing_packages)}")
        print("다음 명령어로 설치하세요:")
        print("pip install -r requirements.txt")
        sys.exit(1)
    
    print("✅ 모든 패키지 설치 확인됨")

def check_environment():
    """환경 변수 확인"""
    print("🔧 환경 변수 확인 중...")
    
    # .env 파일 로드 시도
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ .env 파일 로드됨")
    except ImportError:
        print("⚠️ python-dotenv 미설치 - 환경 변수를 직접 설정하세요")
    except Exception:
        print("⚠️ .env 파일을 찾을 수 없음")
    
    # 필수 환경 변수 확인
    required_env = {
        'RETURNZERO_CLIENT_ID': 'ReturnZero STT API 클라이언트 ID',
        'RETURNZERO_CLIENT_SECRET': 'ReturnZero STT API 클라이언트 시크릿'
    }
    
    optional_env = {
        'ELEVENLABS_API_KEY': 'ElevenLabs TTS API 키 (없으면 TTS 비활성화)'
    }
    
    missing_required = []
    
    for env_var, description in required_env.items():
        if not os.getenv(env_var):
            missing_required.append(f"{env_var}: {description}")
            print(f"❌ {env_var}")
        else:
            print(f"✅ {env_var}")
    
    for env_var, description in optional_env.items():
        if not os.getenv(env_var):
            print(f"⚠️ {env_var} (선택사항)")
        else:
            print(f"✅ {env_var}")
    
    if missing_required:
        print(f"\n❌ 필수 환경 변수가 설정되지 않았습니다:")
        for var in missing_required:
            print(f"   - {var}")
        print("\n.env 파일을 생성하거나 환경 변수를 직접 설정하세요.")
        print("예시: .env.example 파일을 참고하세요.")
        sys.exit(1)
    
    print("✅ 환경 변수 확인 완료")

def check_audio_system():
    """오디오 시스템 확인"""
    print("🔊 오디오 시스템 확인 중...")
    
    try:
        import pyaudio
        
        # PyAudio 초기화 테스트
        pa = pyaudio.PyAudio()
        
        # 입력 장치 확인
        input_devices = []
        output_devices = []
        
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                input_devices.append(info['name'])
            if info['maxOutputChannels'] > 0:
                output_devices.append(info['name'])
        
        pa.terminate()
        
        if input_devices:
            print(f"✅ 입력 장치 {len(input_devices)}개 발견")
        else:
            print("❌ 마이크 장치를 찾을 수 없습니다")
            return False
        
        if output_devices:
            print(f"✅ 출력 장치 {len(output_devices)}개 발견")
        else:
            print("❌ 스피커 장치를 찾을 수 없습니다")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 오디오 시스템 오류: {e}")
        return False

def main():
    """메인 실행 함수"""
    print("🛡️ 보이스피싱 AI 상담 시스템 시작")
    print("=" * 50)
    
    # 체크리스트 실행
    check_python_version()
    check_dependencies()
    check_environment()
    
    if not check_audio_system():
        print("⚠️ 오디오 시스템에 문제가 있지만 계속 진행합니다...")
    
    print("\n🚀 모든 확인 완료 - 애플리케이션 시작")
    print("=" * 50)
    
    # 메인 애플리케이션 실행
    try:
        # 현재 디렉토리를 프로젝트 루트로 변경
        project_root = Path(__file__).parent
        os.chdir(project_root)
        
        # main.py 실행
        import main
        import asyncio
        
        asyncio.run(main.main())
        
    except KeyboardInterrupt:
        print("\n👋 사용자에 의한 종료")
    except Exception as e:
        print(f"\n❌ 실행 중 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()