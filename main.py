#!/usr/bin/env python3
"""
고성능 보이스피싱 상담 시스템 메인 애플리케이션
최적화된 STT → LangGraph → TTS 통합 파이프라인
"""

import asyncio
import logging
import signal
import sys
import psutil
import gc
import threading
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 패스에 추가
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings
from services.conversation_manager import HighPerformanceConversationManager, ConversationState

# 최적화된 로깅 설정
def setup_optimized_logging():
    """고성능 로깅 설정"""
    
    # 로그 레벨 설정
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    
    # 커스텀 포매터
    formatter = logging.Formatter(
        '%(asctime)s | %(name)-12s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # 콘솔 핸들러 (성능 최적화)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # 파일 핸들러 (비동기 방식)
    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            'voice_phishing_system.log',
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
    except Exception:
        file_handler = None
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    if file_handler:
        root_logger.addHandler(file_handler)
    
    # 외부 라이브러리 로그 레벨 조정 (성능 최적화)
    logging.getLogger('elevenlabs').setLevel(logging.WARNING)
    logging.getLogger('grpc').setLevel(logging.ERROR)
    logging.getLogger('pyaudio').setLevel(logging.ERROR)

setup_optimized_logging()
logger = logging.getLogger(__name__)



class HighPerformanceVoicePhishingApp:
    """고성능 보이스피싱 상담 메인 애플리케이션"""
    
    def __init__(self):
        self.conversation_manager = None
        self.is_running = False
        self.start_time = None
        
        # 시스템 모니터링
        self.process = psutil.Process()
        self.initial_memory = self.process.memory_info().rss
        
        # 성능 통계
        self.performance_stats = {
            'start_time': None,
            'total_runtime': 0,
            'peak_memory_usage': 0,
            'total_conversations': 0,
            'avg_cpu_usage': 0.0
        }
        
        # 설정 검증
        self._validate_configuration()
    
    def _validate_configuration(self):
        """설정 검증 및 최적화"""
        
        # API 키 확인
        if not settings.RETURNZERO_CLIENT_ID or not settings.RETURNZERO_CLIENT_SECRET:
            logger.error("❌ ReturnZero API 키가 설정되지 않았습니다.")
            logger.info("환경변수 RETURNZERO_CLIENT_ID, RETURNZERO_CLIENT_SECRET를 설정해주세요.")
            sys.exit(1)
        
        if not settings.ELEVENLABS_API_KEY:
            logger.warning("⚠️ ElevenLabs API 키가 설정되지 않았습니다. TTS가 비활성화됩니다.")
        
        # 성능 모드 설정
        if settings.DEBUG:
            logger.info("🐛 디버그 모드 활성화 - 성능이 저하될 수 있습니다")
        else:
            # 프로덕션 최적화
            self._optimize_for_production()
    
    def _optimize_for_production(self):
        """프로덕션 환경 최적화"""
        
        # 가비지 컬렉션 최적화
        gc.set_threshold(700, 10, 10)  # 더 자주 GC 실행
        
        # 메모리 최적화 설정
        import sys
        sys.setswitchinterval(0.005)  # 스레드 스위칭 간격 단축
        
        logger.info("🚀 프로덕션 모드 최적화 완료")
    
    async def initialize(self):
        """고성능 애플리케이션 초기화"""
        
        logger.info("=" * 60)
        logger.info("🛡️  고성능 보이스피싱 AI 상담 시스템")
        logger.info("=" * 60)
        
        self.start_time = datetime.now()
        self.performance_stats['start_time'] = self.start_time
        
        try:
            # 메모리 사용량 체크
            initial_memory_mb = self.initial_memory / 1024 / 1024
            logger.info(f"🧠 초기 메모리 사용량: {initial_memory_mb:.1f} MB")
            
            # 대화 매니저 생성 (고성능 버전)
            self.conversation_manager = HighPerformanceConversationManager(
                client_id=settings.RETURNZERO_CLIENT_ID,
                client_secret=settings.RETURNZERO_CLIENT_SECRET
            )
            
            # 콜백 함수 설정
            self.conversation_manager.set_callbacks(
                on_user_speech=self._on_user_speech,
                on_ai_response=self._on_ai_response,
                on_state_change=self._on_state_change
            )
            
            # 초기화 시간 측정
            init_time = (datetime.now() - self.start_time).total_seconds()
            logger.info(f"✅ 애플리케이션 초기화 완료 ({init_time:.2f}초)")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 초기화 실패: {e}")
            return False
        
    def _setup_debug_commands(self):
        """디버그 명령어 설정"""
    
        def debug_input_worker():
            """디버그 입력 워커"""
            while self.is_running:
                try:
                    cmd = input().strip().lower()
                    
                    if cmd == 'status':
                        # 오디오 상태 출력
                        if self.conversation_manager:
                            status = self.conversation_manager.get_audio_status()
                            print("\n📊 오디오 상태:")
                            for key, value in status.items():
                                print(f"   {key}: {value}")
                            print()
                    
                    elif cmd == 'silence':
                        # 강제 침묵 처리 트리거
                        if self.conversation_manager:
                            asyncio.create_task(
                                self.conversation_manager._handle_silence_timeout()
                            )
                            print("🔇 침묵 처리 강제 실행")
                    
                    elif cmd == 'help':
                        print("\n💡 디버그 명령어:")
                        print("   status  - 오디오 상태 확인")
                        print("   silence - 침묵 처리 강제 실행")
                        print("   help    - 도움말")
                        print()
                    
                except (EOFError, KeyboardInterrupt):
                    break
                except Exception as e:
                    logger.error(f"디버그 입력 오류: {e}")
        
        # 디버그 모드에서만 활성화
        if settings.DEBUG:
            debug_thread = threading.Thread(target=debug_input_worker, daemon=True)
            debug_thread.start()
            print("\n💡 디버그 모드: 'status', 'silence', 'help' 명령어 사용 가능")
    
    async def run(self):
        """최적화된 메인 실행"""
        
        if not await self.initialize():
            logger.error("❌ 애플리케이션 시작 실패")
            return
        
        self.is_running = True
        
        try:
            logger.info("🚀 고성능 보이스피싱 상담 시스템 시작")
            logger.info("💡 종료하려면 Ctrl+C를 누르세요")
            logger.info("-" * 60)
            
            # 시그널 핸들러 설정
            self._setup_signal_handlers()

            # Debug 명령어 설정
            self._setup_debug_commands()
            
            # 모니터링 및 대화 태스크 생성
            tasks = await self._create_main_tasks()
            
            # 모든 태스크 실행
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("\n🛑 사용자에 의한 종료")
        except Exception as e:
            logger.error(f"❌ 실행 중 오류: {e}")
        finally:
            await self.cleanup()

    
    
    async def _create_main_tasks(self):
        """메인 태스크들 생성"""
        
        tasks = []
        
        # 시스템 모니터링 태스크
        tasks.append(asyncio.create_task(
            self._system_monitor(), 
            name="SystemMonitor"
        ))
        
        # 메모리 관리 태스크
        tasks.append(asyncio.create_task(
            self._memory_manager(), 
            name="MemoryManager"
        ))
        
        # 성능 통계 태스크
        tasks.append(asyncio.create_task(
            self._performance_reporter(), 
            name="PerformanceReporter"
        ))
        
        # 메인 대화 태스크
        tasks.append(asyncio.create_task(
            self.conversation_manager.start_conversation(),
            name="ConversationManager"
        ))
        
        return tasks
    
    def _setup_signal_handlers(self):
    
        def signal_handler(signum, frame):
            logger.info(f"\n📶 종료 신호 수신 - 즉시 종료")
            import os
            os._exit(0)  # 즉시 강제 종료
        
        signal.signal(signal.SIGINT, signal_handler)
    
    async def _system_monitor(self):
        """시스템 리소스 모니터링"""
        
        while self.is_running:
            try:
                # CPU 사용률
                cpu_percent = self.process.cpu_percent()
                
                # 메모리 사용률
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                
                # 최대 메모리 사용량 추적
                if memory_mb > self.performance_stats['peak_memory_usage']:
                    self.performance_stats['peak_memory_usage'] = memory_mb
                
                # CPU 평균 계산
                current_avg = self.performance_stats['avg_cpu_usage']
                self.performance_stats['avg_cpu_usage'] = (current_avg + cpu_percent) / 2
                
                # 디버그 모드에서만 상세 정보 출력
                if settings.DEBUG:
                    logger.debug(f"💻 CPU: {cpu_percent:.1f}%, 메모리: {memory_mb:.1f}MB")
                
                # 리소스 경고
                if memory_mb > 500:  # 500MB 초과
                    logger.warning(f"⚠️ 높은 메모리 사용량: {memory_mb:.1f}MB")
                
                if cpu_percent > 80:  # 80% 초과
                    logger.warning(f"⚠️ 높은 CPU 사용률: {cpu_percent:.1f}%")
                
                await asyncio.sleep(15)  # 15초마다 체크
                
            except Exception as e:
                logger.error(f"시스템 모니터링 오류: {e}")
                await asyncio.sleep(30)
    
    async def _memory_manager(self):
        """메모리 관리 및 최적화"""
        
        while self.is_running:
            try:
                # 메모리 사용량 체크
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                
                # 메모리 임계값 체크 (400MB)
                if memory_mb > 400:
                    logger.info("🧹 메모리 정리 시작...")
                    
                    # 가비지 컬렉션 강제 실행
                    collected = gc.collect()
                    
                    # 대화 매니저 캐시 정리
                    if hasattr(self.conversation_manager, 'langgraph'):
                        if hasattr(self.conversation_manager.langgraph, 'clear_cache'):
                            self.conversation_manager.langgraph.clear_cache()
                    
                    # TTS 캐시 정리
                    if hasattr(self.conversation_manager, 'tts_service'):
                        if hasattr(self.conversation_manager.tts_service, 'clear_cache'):
                            self.conversation_manager.tts_service.clear_cache()
                    
                    # 정리 후 메모리 확인
                    new_memory = self.process.memory_info().rss / 1024 / 1024
                    saved_mb = memory_mb - new_memory
                    
                    logger.info(f"🧹 메모리 정리 완료: {saved_mb:.1f}MB 절약 (GC: {collected})")
                
                await asyncio.sleep(60)  # 1분마다 체크
                
            except Exception as e:
                logger.error(f"메모리 관리 오류: {e}")
                await asyncio.sleep(120)
    
    async def _performance_reporter(self):
        """성능 통계 리포트"""
        
        while self.is_running:
            try:
                await asyncio.sleep(300)  # 5분마다 리포트
                
                if not self.conversation_manager:
                    continue
                
                # 대화 매니저 통계
                conv_status = self.conversation_manager.get_conversation_status()
                perf_metrics = self.conversation_manager.get_performance_metrics()
                
                # 현재 런타임 계산
                if self.start_time:
                    runtime = (datetime.now() - self.start_time).total_seconds()
                    self.performance_stats['total_runtime'] = runtime
                
                # 성능 리포트 생성
                self._log_performance_report(conv_status, perf_metrics)
                
            except Exception as e:
                logger.error(f"성능 리포트 오류: {e}")
                await asyncio.sleep(300)
    
    def _log_performance_report(self, conv_status: dict, perf_metrics: dict):
        """성능 리포트 로깅"""
        
        runtime_mins = self.performance_stats['total_runtime'] / 60
        memory_mb = self.performance_stats['peak_memory_usage']
        
        logger.info("📊 === 성능 리포트 ===")
        logger.info(f"   실행 시간: {runtime_mins:.1f}분")
        logger.info(f"   최대 메모리: {memory_mb:.1f}MB")
        logger.info(f"   평균 CPU: {self.performance_stats['avg_cpu_usage']:.1f}%")
        logger.info(f"   대화 턴: {conv_status.get('total_turns', 0)}")
        logger.info(f"   평균 응답시간: {conv_status.get('avg_response_time', 0):.3f}초")
        logger.info(f"   TTS 성공률: {conv_status.get('tts_success_rate', 0):.1%}")
        logger.info(f"   큐 크기: {conv_status.get('queue_size', 0)}")
        logger.info("=" * 25)
    
    def _on_user_speech(self, text: str):
        """사용자 음성 인식 콜백"""
        
        # 간결한 출력
        display_text = text[:50] + "..." if len(text) > 50 else text
        print(f"\n👤 사용자: {display_text}")
        
        # 상세 로그는 파일에만
        logger.info(f"사용자 입력 ({len(text)}자): {text}")
    
    def _on_ai_response(self, response: str):
        """AI 응답 콜백"""
        
        # 간결한 출력
        display_response = response[:100] + "..." if len(response) > 100 else response
        print(f"\n🤖 상담원: {display_response}")
        
        # 상세 로그는 파일에만
        logger.info(f"AI 응답 ({len(response)}자): {response}")
    
    def _on_state_change(self, old_state: ConversationState, new_state: ConversationState):
        """상태 변경 콜백"""
        
        if settings.DEBUG:
            state_icons = {
                ConversationState.IDLE: "💤",
                ConversationState.LISTENING: "👂", 
                ConversationState.PROCESSING: "🧠",
                ConversationState.SPEAKING: "🗣️",
                ConversationState.ERROR: "❌"
            }
            
            old_icon = state_icons.get(old_state, "❓")
            new_icon = state_icons.get(new_state, "❓")
            
            print(f"\n{old_icon} → {new_icon} ({new_state.value})")
        
        logger.debug(f"상태 변경: {old_state.value} → {new_state.value}")
    
    async def cleanup(self):
        """최적화된 리소스 정리"""
        
        logger.info("🧹 애플리케이션 종료 중...")
        
        try:
            self.is_running = False
            
            # 대화 매니저 정리
            if self.conversation_manager:
                await self.conversation_manager.cleanup()
            
            # 최종 성능 통계
            self._print_final_statistics()
            
            # 메모리 정리
            gc.collect()
            
            logger.info("✅ 정리 완료")
            
        except Exception as e:
            logger.error(f"정리 중 오류: {e}")
    
    def _print_final_statistics(self):
        """최종 통계 출력"""
        
        if not self.start_time:
            return
        
        total_runtime = (datetime.now() - self.start_time).total_seconds()
        final_memory = self.process.memory_info().rss / 1024 / 1024
        
        logger.info("📈 === 최종 성능 통계 ===")
        logger.info(f"   총 실행 시간: {total_runtime/60:.1f}분")
        logger.info(f"   최대 메모리 사용량: {self.performance_stats['peak_memory_usage']:.1f}MB")
        logger.info(f"   최종 메모리 사용량: {final_memory:.1f}MB")
        logger.info(f"   평균 CPU 사용률: {self.performance_stats['avg_cpu_usage']:.1f}%")
        
        if self.conversation_manager:
            conv_status = self.conversation_manager.get_conversation_status()
            logger.info(f"   총 대화 턴: {conv_status.get('total_turns', 0)}")
            logger.info(f"   평균 응답 시간: {conv_status.get('avg_response_time', 0):.3f}초")
        
        logger.info("=" * 30)

async def main():
    """메인 함수"""
    
    # 이벤트 루프 최적화
    loop = asyncio.get_running_loop()
    loop.set_debug(settings.DEBUG)
    
    # 애플리케이션 실행
    app = HighPerformanceVoicePhishingApp()
    await app.run()

if __name__ == "__main__":
    try:
        # 성능 최적화된 이벤트 루프 실행
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            # Windows 최적화
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n👋 안전하게 종료되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        sys.exit(1)

        # 터미널에 입력해서 상태를 파악할 수 있다.