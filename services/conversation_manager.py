import asyncio
import logging
import threading
import time
import queue
from datetime import datetime
import numpy as np
from typing import Optional, Dict, Any, Callable
from enum import Enum

from services.stream_stt import RTZROpenAPIClient
from core.graph import OptimizedVoicePhishingGraph
from services.tts_service import tts_service
from services.audio_manager import audio_manager
from config.settings import settings
from core.state import VictimRecoveryState

logger = logging.getLogger(__name__)

class ConversationState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"

class HighPerformanceConversationManager:
    """
    고성능 대화 관리자
    - 비동기 처리 최적화
    - 메모리 효율성 개선
    - 실시간 응답 최적화
    - 향상된 오디오 동기화
    """
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        
        # 최적화된 컴포넌트들
        self.stt_client = None
        self.langgraph = OptimizedVoicePhishingGraph(debug=settings.DEBUG)
        self.tts_service = tts_service
        self.audio_manager = audio_manager
        
        # 상태 관리
        self.conversation_state = ConversationState.IDLE
        self.current_langgraph_state = None
        self.session_id = None
        
        # 고성능 제어 플래그
        self.is_running = False
        self.is_listening = False
        self.is_processing = False
        
        # 최적화된 STT 결과 큐 (크기 제한)
        self.stt_queue = queue.Queue(maxsize=10)
        self.stt_lock = threading.Lock()
        
        # 콜백 함수들
        self.callbacks = {
            'on_user_speech': None,
            'on_ai_response': None,
            'on_state_change': None
        }
        
        # 성능 통계
        self.performance_stats = {
            'conversation_start_time': None,
            'total_turns': 0,
            'avg_response_time': 0.0,
            'stt_accuracy': 0.0,
            'tts_success_rate': 0.0
        }
        
        # 응답 시간 추적
        self.response_times = []
        self.max_response_times = 50  # 최근 50개만 유지

        # 오디오 레벨 모니터링
        self.audio_monitor = {
            'is_monitoring' : False,
            'audio_level' : 0.0,
            'silence_threshold' : 0.015, # 침묵 임계값
            'last_audio_time' : None,
            # 'silence_check_interval': 1  # 1초마다 체크
        }


        # 침묵 감지
        self.silence_detection = {
            'enabled': True,
            'timeout': 5.0,  # 5초 침묵 시 다음으로
            'last_speech_time': None,
            'last_audio_activity' : None, # 마지막 오디오 활동 시간
            'is_first_interaction': True,  # 첫 번째 상호작용 체크
            'min_interactions': 1,  # 최소 상호작용 횟수
            'silence_check_interval': 0.2 
        }

    def _start_audio_monitoring(self):
        """오디오 레벨 모니터링 시작"""
        
        def audio_monitor_worker():
            """오디오 레벨 모니터링 워커"""
            try:
                import pyaudio
                
                # 오디오 스트림 설정
                chunk = 1024
                format = pyaudio.paInt16
                channels = 1
                rate = 16000
                
                p = pyaudio.PyAudio()
                
                stream = p.open(
                    format=format,
                    channels=channels,
                    rate=rate,
                    input=True,
                    frames_per_buffer=chunk
                )
                
                self.audio_monitor['monitor_stream'] = stream
                self.audio_monitor['is_monitoring'] = True
                
                logger.info("🎤 오디오 레벨 모니터링 시작")
                
                while self.is_running and self.audio_monitor['is_monitoring']:
                    try:
                        # 오디오 데이터 읽기
                        data = stream.read(chunk, exception_on_overflow=False)
                        
                        # 음성 레벨 계산
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        audio_level = np.abs(audio_data).mean() / 32768.0  # 정규화
                        
                        self.audio_monitor['audio_level'] = audio_level
                        
                        # 음성 활동 감지
                        if audio_level > self.audio_monitor['silence_threshold']:
                            self.audio_monitor['last_audio_time'] = time.time()
                            self.silence_detection['last_audio_activity'] = time.time()
                            
                            if settings.DEBUG:
                                logger.debug(f"🔊 오디오 레벨: {audio_level:.3f}")
                        
                    except Exception as e:
                        if self.is_running:
                            logger.error(f"오디오 모니터링 오류: {e}")
                        break
                
                # 정리
                stream.stop_stream()
                stream.close()
                p.terminate()
                
            except Exception as e:
                logger.error(f"오디오 모니터링 워커 오류: {e}")
            finally:
                self.audio_monitor['is_monitoring'] = False
        
        # 모니터링 스레드 시작
        monitor_thread = threading.Thread(target=audio_monitor_worker, daemon=True)
        monitor_thread.start()
    
    def _should_handle_silence(self) -> bool:
        """개선된 침묵 처리 여부 판단"""
        
        # 침묵 감지 비활성화 상태
        if not self.silence_detection['enabled']:
            return False
        
        # 첫 번째 상호작용이면 침묵 감지 안 함
        if self.silence_detection['is_first_interaction']:
            return False
        
        # 현재 처리 중이면 침묵 감지 안 함
        if self.is_processing:
            return False
        
        current_time = time.time()
        
        # 1. STT 기반 체크 (음성 인식된 시간)
        last_speech_time = self.silence_detection.get('last_speech_time')
        speech_silence_duration = float('inf')
        if last_speech_time:
            speech_silence_duration = current_time - last_speech_time
        
        # 2. 오디오 활동 기반 체크 (실제 소리 감지)
        last_audio_time = self.silence_detection.get('last_audio_activity')
        audio_silence_duration = float('inf')
        if last_audio_time:
            audio_silence_duration = current_time - last_audio_time
        
        # 둘 중 더 짧은 시간 사용 (더 정확한 감지)
        silence_duration = min(speech_silence_duration, audio_silence_duration)
        
        # 디버그 정보
        if settings.DEBUG and silence_duration < 60:  # 1분 이내만 로깅
            logger.debug(f"🔇 침묵 체크: {silence_duration:.1f}초 (임계값: {self.silence_detection['timeout']}초)")
        
        # 침묵 임계값 체크
        is_silence = silence_duration >= self.silence_detection['timeout']
        
        if is_silence:
            logger.info(f"⏰ 침묵 감지됨: {silence_duration:.1f}초")
        
        return is_silence
    
    def get_audio_status(self) -> dict:
        """오디오 상태 조회 (디버깅용)"""
        
        current_time = time.time()
        
        return {
            'is_monitoring': self.audio_monitor['is_monitoring'],
            'current_audio_level': self.audio_monitor['audio_level'],
            'silence_threshold': self.audio_monitor['silence_threshold'],
            'last_audio_time': self.audio_monitor.get('last_audio_time'),
            'seconds_since_audio': (
                current_time - self.audio_monitor['last_audio_time'] 
                if self.audio_monitor.get('last_audio_time') else None
            ),
            'silence_detection_enabled': self.silence_detection['enabled'],
            'silence_timeout': self.silence_detection['timeout']
        }



        
    async def initialize(self) -> bool:
        """고성능 초기화"""
        logger.info("🚀 고성능 대화 관리자 초기화...")
        
        try:
            # STT 클라이언트 초기화 (성능 최적화)
            self.stt_client = RTZROpenAPIClient(self.client_id, self.client_secret)
            logger.info("✅ STT 클라이언트 초기화 완료")
            
            # TTS 서비스 빠른 테스트
            if await asyncio.wait_for(self.tts_service.test_connection(), timeout=5.0):
                logger.info("✅ TTS 서비스 연결 확인")
                self.performance_stats['tts_success_rate'] = 1.0
            else:
                logger.warning("⚠️ TTS 서비스 연결 실패")
                self.performance_stats['tts_success_rate'] = 0.0
            
            # 오디오 매니저 초기화
            if self.audio_manager.initialize_output():
                logger.info("✅ 오디오 매니저 초기화 완료")
            else:
                logger.error("❌ 오디오 매니저 초기화 실패")
                return False
            
            # LangGraph 최적화 시작
            self.current_langgraph_state = await asyncio.wait_for(
                self.langgraph.start_conversation(), 
                timeout=3.0
            )
            
            if self.current_langgraph_state:
                self.session_id = self.current_langgraph_state['session_id']
                logger.info(f"✅ LangGraph 시작 - 세션: {self.session_id}")
            else:
                logger.error("❌ LangGraph 초기화 실패")
                return False
            
            # 초기 인사말 처리
            await self._handle_initial_greeting()
            
            self.performance_stats['conversation_start_time'] = datetime.now()
            self._set_state(ConversationState.IDLE)
            
            return True
            
        except asyncio.TimeoutError:
            logger.error("❌ 초기화 시간 초과")
            return False
        except Exception as e:
            logger.error(f"❌ 초기화 실패: {e}")
            self._set_state(ConversationState.ERROR)
            return False
    
    async def start_conversation(self):
        """최적화된 대화 시작"""
        if not await self.initialize():
            logger.error("❌ 대화 시작 실패")
            return
        
        self.is_running = True
        logger.info("🎙️ 고성능 대화 시작")
        
        try:
            # STT 리스닝 시작 (별도 스레드)
            self._start_optimized_stt()
            
            # 메인 이벤트 루프 (고성능)
            await self._main_conversation_loop()
            
        except KeyboardInterrupt:
            logger.info("사용자에 의한 종료")
        except Exception as e:
            logger.error(f"대화 중 오류: {e}")
        finally:
            await self.cleanup()

    async def _main_conversation_loop(self): 
        """고성능 메인 루프 - 침묵 감지 강화"""
        
        # 오디오 모니터링 시작
        logger.info("🎤 오디오 모니터링 시작 시도...")
        self._start_audio_monitoring()
        
        # 잠시 대기해서 모니터링이 시작되도록
        await asyncio.sleep(1)
        
        # 침묵 체크를 위한 마지막 체크 시간
        last_silence_check = time.time()
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # STT 결과 확인
                user_input = self._get_stt_result_fast()
                
                if user_input and not self.is_processing:
                    # 음성 입력이 있으면 시간 업데이트
                    self.silence_detection['last_speech_time'] = current_time
                    self.silence_detection['is_first_interaction'] = False
                    
                    await self._process_user_input_optimized(user_input)
                
                # 정기적인 침묵 체크 (0.5초마다)
                if (current_time - last_silence_check >= 
                    self.silence_detection['silence_check_interval']):
                    
                    if self._should_handle_silence():
                        await self._handle_silence_timeout()
                    
                    last_silence_check = current_time
                
                # 대화 완료 확인
                if self._should_end_conversation():
                    logger.info("✅ 대화 자동 완료")
                    break
                
                await asyncio.sleep(0.1)
                        
            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")
                await asyncio.sleep(0.5)
        
    def _start_optimized_stt(self):
        """최적화된 STT 시작"""
        
        def optimized_stt_worker():
            """성능 최적화된 STT 워커"""
            try:
                self.stt_client.reset_stream()
                
                # 커스텀 콜백으로 성능 최적화
                def fast_transcript_handler(start_time, transcript, is_final=False):
                    if is_final and transcript.alternatives:
                        text = transcript.alternatives[0].text.strip()
                        if text and len(text) > 1:  # 너무 짧은 텍스트 필터링
                            try:
                                # 큐가 가득 찬 경우 오래된 항목 제거
                                if self.stt_queue.full():
                                    try:
                                        self.stt_queue.get_nowait()
                                    except queue.Empty:
                                        pass
                                
                                self.stt_queue.put_nowait(text)
                                
                            except queue.Full:
                                logger.warning("STT 큐 가득참 - 메시지 무시")
                
                # 콜백 설정
                self.stt_client.print_transcript = fast_transcript_handler
                
                # STT 스트리밍 시작
                # STT 스트리밍 시작
                while self.is_running:  # 종료 조건 추가
                    try:
                        self.stt_client.transcribe_streaming_grpc()
                    except Exception as e:
                        if self.is_running:  # 실행 중일 때만 에러 로그
                            logger.error(f"STT 스트리밍 오류: {e}")
                        break
                    
            except Exception as e:
                if self.is_running:
                    logger.error(f"STT 워커 오류: {e}")
                
            # except Exception as e:
            #     logger.error(f"STT 워커 오류: {e}")
            #     self._set_state(ConversationState.ERROR)
        
        # 데몬 스레드로 시작
        stt_thread = threading.Thread(target=optimized_stt_worker, daemon=True)
        stt_thread.start()
        self.is_listening = True
        
        logger.info("🎤 최적화된 STT 시작")
    
    
    def _get_stt_result_fast(self) -> Optional[str]:
        """고속 STT 결과 가져오기"""
        try:
            return self.stt_queue.get_nowait()
        except queue.Empty:
            return None
    
    async def _process_user_input_optimized(self, user_input: str):
        """최적화된 사용자 입력 처리"""
        
        start_time = time.time()
        self.is_processing = True
        
        logger.info(f"👤 사용자: {user_input}")
        
        # 상태 변경
        self._set_state(ConversationState.PROCESSING)
        
        # 콜백 호출
        if self.callbacks['on_user_speech']:
            self.callbacks['on_user_speech'](user_input)
        
        try:
            # LangGraph 최적화 처리 (타임아웃 설정)
            self.current_langgraph_state = await asyncio.wait_for(
                self.langgraph.continue_conversation(
                    self.current_langgraph_state, 
                    user_input
                ),
                timeout=10.0  # 10초 타임아웃 / 짧게 줬는데 너무 빨리 타임아웃됨.
            )
            
            # AI 응답 추출 및 처리
            await self._handle_ai_response()
            
            # 성능 통계 업데이트
            processing_time = time.time() - start_time
            self._update_performance_stats(processing_time)
            
            self.performance_stats['total_turns'] += 1
            
            # 다음 상태로 전환
            if self._is_conversation_complete():
                await self.stop_conversation()
            else:
                self._set_state(ConversationState.LISTENING)
            
        except asyncio.TimeoutError:
            logger.warning("⏰ 처리 시간 초과 - 빠른 응답 생성")
            await self._handle_timeout_response(user_input)
        except Exception as e:
            logger.error(f"입력 처리 오류: {e}")
            await self._handle_error("처리 중 오류가 발생했습니다. 다시 말씀해 주세요.")
        finally:
            self.is_processing = False

    async def continue_conversation(self, state: VictimRecoveryState, user_input: str) -> VictimRecoveryState:
        """구조화된 대화 계속하기"""
        
        if not user_input.strip():
            state["messages"].append({
                "role": "assistant",
                "content": "죄송합니다. 다시 말씀해 주세요.",
                "timestamp": datetime.now()
            })
            return state
        
        # 사용자 메시지 추가
        state["messages"].append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now()
        })
        
        state["conversation_turns"] = state.get("conversation_turns", 0) + 1
        
        try:
            # 🔧 수정: 그래프 재실행으로 자동 흐름 진행
            config = {"recursion_limit": 5}
            updated_state = await self.langgraph.graph.ainvoke(state, config)
            
            if self.debug:
                print(f"✅ 구조화된 처리: 턴 {updated_state['conversation_turns']}")
            
            return updated_state
            
        except Exception as e:
            if self.debug:
                print(f"❌ 구조화된 처리 실패: {e}")
            
            state["messages"].append({
                "role": "assistant",
                "content": "처리 중 문제가 발생했습니다. 긴급한 경우 112로 연락하세요.",
                "timestamp": datetime.now()
            })
            return state
    
    async def _handle_ai_response(self):
        """AI 응답 처리"""
        
        if not self.current_langgraph_state or not self.current_langgraph_state.get('messages'):
            return
        
        last_message = self.current_langgraph_state['messages'][-1]
        if last_message.get('role') != 'assistant':
            return
        
        ai_response = last_message['content']
        logger.info(f"AI: {ai_response[:100]}...")
        
        # 콜백 호출
        if self.callbacks['on_ai_response']:
            self.callbacks['on_ai_response'](ai_response)
        
        # TTS 처리 (비동기)
        await self._speak_response_optimized(ai_response)
    
    async def _speak_response_optimized(self, text: str):
        """최적화된 TTS 처리"""
        
        self._set_state(ConversationState.SPEAKING)
        
        try:
            # 텍스트 길이 최적화 (너무 길면 요약)
            if len(text) > 300:
                text = self._summarize_text(text)
            
            # TTS 스트림 생성 (타임아웃 설정)
            audio_stream = await asyncio.wait_for(
                self._create_tts_stream(text),
                timeout=5.0
            )
            
            # 오디오 재생
            await self.audio_manager.play_audio_stream(audio_stream)
            
            logger.info("🔊 TTS 재생 완료")
            
        except asyncio.TimeoutError:
            logger.warning("⏰ TTS 시간 초과 - 텍스트 출력으로 대체")
            print(f"AI: {text}")
        except Exception as e:
            logger.error(f"TTS 오류: {e}")
            # TTS 실패 시 텍스트 출력
            print(f"AI: {text}")
            self.performance_stats['tts_success_rate'] *= 0.9  # 성공률 감소
    
    async def _create_tts_stream(self, text: str):
        """TTS 스트림 생성"""
        return self.tts_service.text_to_speech_stream(text)
    
    def _summarize_text(self, text: str) -> str:
        """텍스트 요약 (간단한 방식)"""
        
        # 문장 단위로 분할
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        
        # 중요한 문장들만 선택 (키워드 기반)
        important_keywords = ['긴급', '즉시', '신고', '112', '중요', '주의']
        important_sentences = []
        
        for sentence in sentences[:3]:  # 최대 3문장
            if any(keyword in sentence for keyword in important_keywords):
                important_sentences.append(sentence)
        
        if important_sentences:
            return '. '.join(important_sentences) + '.'
        else:
            # 중요 문장이 없으면 처음 2문장
            return '. '.join(sentences[:2]) + '.'
    
    async def _handle_timeout_response(self, user_input: str):
        """타임아웃 시 빠른 응답"""
        
        # 간단한 키워드 기반 빠른 응답
        user_lower = user_input.lower()
        
        if any(word in user_lower for word in ['돈', '송금', '보냈', '계좌', '이체', '계좌이체']):
            quick_response = "긴급 상황으로 보입니다. 즉시 112에 신고하세요."
        else:
            quick_response = "상황을 파악했습니다. 추가로 궁금한 점이 있으시면 말씀해 주세요."
        
        # 직접 응답 추가
        if self.current_langgraph_state:
            self.current_langgraph_state['messages'].append({
                "role": "assistant",
                "content": quick_response,
                "timestamp": datetime.now(),
                "type": "timeout_response"
            })
        
        await self._speak_response_optimized(quick_response)
    
    async def _handle_initial_greeting(self):
        """초기 인사말 처리"""
        
        if self.current_langgraph_state and self.current_langgraph_state.get('messages'):
            greeting = self.current_langgraph_state['messages'][-1]['content']
            logger.info("🔊 초기 인사말 재생")
            await self._speak_response_optimized(greeting)
    
    async def _handle_error(self, error_message: str):
        """오류 처리"""
        
        self._set_state(ConversationState.ERROR)
        logger.error(f"오류 처리: {error_message}")
        
        # 오류 메시지 재생
        await self._speak_response_optimized(error_message)
        
        # 리스닝 상태로 복귀
        self._set_state(ConversationState.LISTENING)
    
    def _should_end_conversation(self) -> bool:
        """대화 종료 여부 판단"""
        
        if not self.current_langgraph_state:
            return False
        
        # 완료 상태 확인
        if self.current_langgraph_state.get('current_step') == 'consultation_complete':
            return True
        
        current_step = self.current_langgraph_state.get('current_step')
        if current_step == 'consultation_complete':
            return True
        
        # 나머지 조건들은 더 관대하게
        if self.performance_stats['total_turns'] >= 20:  # 20턴으로 증가
            return True
        
        # 세션 타임아웃 확인
        if self.performance_stats['conversation_start_time']:
            elapsed = (datetime.now() - self.performance_stats['conversation_start_time']).total_seconds()
            if elapsed > settings.SESSION_TIMEOUT:
                return True
        
        return False
    
    def _is_conversation_complete(self) -> bool:
        """대화 완료 여부 확인 (간단한 버전)"""
        return self._should_end_conversation()
    
    def _update_performance_stats(self, processing_time: float):
        """성능 통계 업데이트"""
        
        # 응답 시간 추가
        self.response_times.append(processing_time)
        
        # 최대 개수 유지
        if len(self.response_times) > self.max_response_times:
            self.response_times.pop(0)
        
        # 평균 계산
        if self.response_times:
            self.performance_stats['avg_response_time'] = sum(self.response_times) / len(self.response_times)
    
    def _set_state(self, new_state: ConversationState):
        """상태 변경"""
        
        if self.conversation_state != new_state:
            old_state = self.conversation_state
            self.conversation_state = new_state
            
            logger.debug(f"상태 변경: {old_state.value} → {new_state.value}")
            
            # 콜백 호출
            if self.callbacks['on_state_change']:
                self.callbacks['on_state_change'](old_state, new_state)
    
    async def stop_conversation(self):
        """대화 중지"""
        
        logger.info("🛑 대화 중지")
        
        self.is_running = False
        self.is_listening = False
        
        # 마지막 인사말
        farewell = "상담이 완료되었습니다. 안전하세요!"
        await self._speak_response_optimized(farewell)
    
    async def cleanup(self):
        """최적화된 리소스 정리"""
        
        logger.info("🧹 고성능 매니저 정리 중...")
        
        try:
            self.is_running = False
            self.is_listening = False
            self.is_processing = False
            
            # STT 정리
            # if self.stt_client and hasattr(self.stt_client, 'stream'):
            #     self.stt_client.stream.terminate()

            # STT 스트림 강제 종료
            if self.stt_client and hasattr(self.stt_client, 'stream'):
                try:
                    self.stt_client.stream.terminate()
                except:
                    pass
                
            # 큐 정리
            while not self.stt_queue.empty():
                try:
                    self.stt_queue.get_nowait()
                except queue.Empty:
                    break
            
            # 오디오 매니저 정리
            self.audio_manager.cleanup()
            
            # 캐시 정리
            if hasattr(self.langgraph, 'clear_cache'):
                self.langgraph.clear_cache()
            
            # 성능 통계 출력
            self._print_performance_stats()
            
            logger.info("✅ 정리 완료")
            
        except Exception as e:
            logger.error(f"정리 중 오류: {e}")
    
    def _print_performance_stats(self):
        """성능 통계 출력"""
        
        stats = self.performance_stats
        
        if stats['conversation_start_time']:
            total_time = (datetime.now() - stats['conversation_start_time']).total_seconds()
            
            logger.info("📊 성능 통계:")
            logger.info(f"   총 대화 시간: {total_time:.1f}초")
            logger.info(f"   총 대화 턴: {stats['total_turns']}")
            logger.info(f"   평균 응답 시간: {stats['avg_response_time']:.3f}초")
            logger.info(f"   TTS 성공률: {stats['tts_success_rate']:.1%}")
            
            if self.response_times:
                logger.info(f"   최대 응답 시간: {max(self.response_times):.3f}초")
                logger.info(f"   최소 응답 시간: {min(self.response_times):.3f}초")
    
    # ========================================================================
    # 공개 메서드들
    # ========================================================================
    
    def get_conversation_status(self) -> Dict[str, Any]:
        """향상된 대화 상태 정보"""
        
        elapsed_time = 0
        if self.performance_stats['conversation_start_time']:
            elapsed_time = (datetime.now() - self.performance_stats['conversation_start_time']).total_seconds()
        
        return {
            "state": self.conversation_state.value,
            "session_id": self.session_id,
            "total_turns": self.performance_stats['total_turns'],
            "is_running": self.is_running,
            "is_listening": self.is_listening,
            "is_processing": self.is_processing,
            "elapsed_time": elapsed_time,
            "avg_response_time": self.performance_stats['avg_response_time'],
            "tts_success_rate": self.performance_stats['tts_success_rate'],
            "queue_size": self.stt_queue.qsize()
        }
    
    def set_callbacks(self, 
                     on_user_speech: Optional[Callable] = None,
                     on_ai_response: Optional[Callable] = None, 
                     on_state_change: Optional[Callable] = None):
        """콜백 함수 설정"""
        
        if on_user_speech:
            self.callbacks['on_user_speech'] = on_user_speech
        if on_ai_response:
            self.callbacks['on_ai_response'] = on_ai_response
        if on_state_change:
            self.callbacks['on_state_change'] = on_state_change

    async def _handle_silence_timeout(self):  # 👈 여기에 추가
        """침묵 타임아웃 처리"""
        
        logger.info("⏰ 침묵 감지 - 다음 질문으로 진행")
        
        # 침묵 감지 시간 리셋
        self.silence_detection['last_speech_time'] = time.time()
        self.silence_detection['last_audio_activity'] = time.time()
        
        # 상황에 따른 후속 질문 생성
        follow_up_question = self._generate_follow_up_question()
        
        # 후속 질문 전송
        await self._send_follow_up_question(follow_up_question)

    def _generate_follow_up_question(self) -> str:  # 👈 여기에 추가
        """상황에 맞는 후속 질문 생성"""
        
        if not self.current_langgraph_state:
            return "혹시 더 궁금한 점이 있으신가요?"
        
        urgency = self.current_langgraph_state.get('urgency_level', 3)
        conversation_turns = self.performance_stats['total_turns']
        
        # 긴급 상황 후속 질문
        if urgency >= 8:
            questions = [
                "지금 신고 진행하고 계신가요?",
                "추가로 필요한 조치가 있나요?",
                "다른 피해는 없으신가요?"
            ]
        elif urgency >= 6:
            questions = [
                "더 자세한 상황을 말씀해 주시겠어요?",
                "다른 궁금한 점이 있으신가요?",
                "추가로 확인하고 싶은 내용이 있나요?"
            ]
        else:
            questions = [
                "다른 질문이 있으시면 말씀해 주세요.",
                "더 도움이 필요한 부분이 있나요?",
                "혹시 놓친 부분이 있을까요?"
            ]
        
        # 대화 턴에 따라 질문 선택
        question_index = min(conversation_turns, len(questions) - 1)
        return questions[question_index]

    async def _send_follow_up_question(self, question: str):  # 👈 여기에 추가
        """후속 질문 전송"""
        
        try:
            # LangGraph 상태에 AI 메시지 추가
            if self.current_langgraph_state:
                self.current_langgraph_state['messages'].append({
                    "role": "assistant",
                    "content": question,
                    "timestamp": datetime.now(),
                    "metadata": {"type": "follow_up_silence"}
                })
            
            # 콜백 호출
            if self.callbacks['on_ai_response']:
                self.callbacks['on_ai_response'](question)
            
            # TTS로 재생
            await self._speak_response_optimized(question)
            
        except Exception as e:
            logger.error(f"후속 질문 전송 오류: {e}")    
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """성능 지표 조회"""
        
        return {
            **self.performance_stats,
            "current_queue_size": self.stt_queue.qsize(),
            "response_time_history": self.response_times.copy(),
            "memory_usage": len(self.current_langgraph_state.get('messages', [])) if self.current_langgraph_state else 0
        }


# 하위 호환성을 위한 별칭
ConversationManager = HighPerformanceConversationManager