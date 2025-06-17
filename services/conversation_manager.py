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
from core.graph import VoiceFriendlyPhishingGraph
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

class VoiceFriendlyConversationManager:
    """
    음성 친화적 대화 관리자
    - 응답 속도 최우선 (3초 이내)
    - 간결한 응답 (80자 이내)
    - 즉시 실행 가능한 조치 안내
    - 실질적 도움 중심
    """
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        
        # 음성 친화적 컴포넌트들
        self.stt_client = None
        self.langgraph = VoiceFriendlyPhishingGraph(debug=settings.DEBUG)
        self.tts_service = tts_service
        self.audio_manager = audio_manager
        
        # 상태 관리
        self.conversation_state = ConversationState.IDLE
        self.current_langgraph_state = None
        self.session_id = None
        
        # 빠른 처리 플래그
        self.is_running = False
        self.is_listening = False
        self.is_processing = False
        
        # 간단한 STT 큐 (크기 제한)
        self.stt_queue = queue.Queue(maxsize=5)  # 더 작은 큐
        self.stt_lock = threading.Lock()
        
        # 콜백 함수들
        self.callbacks = {
            'on_user_speech': None,
            'on_ai_response': None,
            'on_state_change': None
        }
        
        # 간단한 성능 통계
        self.stats = {
            'conversation_start_time': None,
            'total_turns': 0,
            'avg_response_time': 0.0,
            'fast_responses': 0,  # 3초 이내 응답
            'emergency_handled': 0
        }
        
        # 응답 시간 추적 (최근 5개만)
        self.response_times = []
        self.max_response_history = 5
        
        # 침묵 감지 (더 여유있게)
        self.silence_detection = {
            'enabled': True,
            'timeout': 8.0,  # 8초로 증가 (사용자 생각 시간)
            'last_speech_time': None,
            'last_audio_activity': None,
            'is_first_interaction': True,
            'silence_check_interval': 0.5,  # 0.5초마다 체크 (덜 자주)
            'min_silence_after_ai': 3.0     # AI 답변 후 최소 3초 대기
        }
        
        # 음성 레벨 모니터링 (덜 민감하게)
        self.audio_monitor = {
            'is_monitoring': False,
            'audio_level': 0.0,
            'silence_threshold': 0.03,  # 덜 민감하게 (0.02 → 0.03)
            'last_audio_time': None
        }
        
        # STT 품질 관리
        self.stt_quality = {
            'min_text_length': 3,           # 최소 3글자
            'last_ai_response_time': None,  # 마지막 AI 응답 시간
            'min_wait_after_ai': 2.0        # AI 응답 후 최소 2초 대기
        }
    
    async def initialize(self) -> bool:
        """빠른 초기화"""
        logger.info("🚀 음성 친화적 대화 관리자 초기화...")
        
        try:
            # STT 클라이언트 빠른 초기화
            self.stt_client = RTZROpenAPIClient(self.client_id, self.client_secret)
            logger.info("✅ STT 클라이언트 초기화 완료")
            
            # TTS 빠른 테스트 (2초 타임아웃)
            if await asyncio.wait_for(self.tts_service.test_connection(), timeout=2.0):
                logger.info("✅ TTS 서비스 연결 확인")
            else:
                logger.warning("⚠️ TTS 서비스 연결 실패 - 텍스트 모드로 진행")
            
            # 오디오 매니저 초기화
            if self.audio_manager.initialize_output():
                logger.info("✅ 오디오 매니저 초기화 완료")
            else:
                logger.warning("⚠️ 오디오 매니저 초기화 실패")
            
            # LangGraph 빠른 시작 (2초 타임아웃)
            self.current_langgraph_state = await asyncio.wait_for(
                self.langgraph.start_conversation(), 
                timeout=2.0
            )
            
            if self.current_langgraph_state:
                self.session_id = self.current_langgraph_state['session_id']
                logger.info(f"✅ 음성 친화적 상담 시작 - 세션: {self.session_id}")
            else:
                logger.error("❌ LangGraph 초기화 실패")
                return False
            
            # 초기 인사말 빠른 처리
            await self._handle_initial_greeting_fast()
            
            self.stats['conversation_start_time'] = datetime.now()
            self._set_state(ConversationState.IDLE)
            
            return True
            
        except asyncio.TimeoutError:
            logger.error("❌ 초기화 시간 초과 (2초)")
            return False
        except Exception as e:
            logger.error(f"❌ 초기화 실패: {e}")
            return False
    
    async def start_conversation(self):
        """음성 친화적 대화 시작"""
        if not await self.initialize():
            logger.error("❌ 대화 시작 실패")
            return
        
        self.is_running = True
        logger.info("🎙️ 음성 친화적 대화 시작")
        
        try:
            # STT 빠른 시작
            self._start_fast_stt()
            
            # 간단한 메인 루프
            await self._simple_conversation_loop()
            
        except KeyboardInterrupt:
            logger.info("사용자에 의한 종료")
        except Exception as e:
            logger.error(f"대화 중 오류: {e}")
        finally:
            await self.cleanup()
    
    async def _simple_conversation_loop(self):
        """간단한 메인 루프"""
        
        # 오디오 모니터링 시작
        self._start_simple_audio_monitoring()
        
        last_silence_check = time.time()
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # STT 결과 빠른 확인
                user_input = self._get_stt_result_immediate()
                
                if user_input and not self.is_processing:
                    # 음성 입력 시간 업데이트
                    self.silence_detection['last_speech_time'] = current_time
                    self.silence_detection['is_first_interaction'] = False
                    
                    await self._process_user_input_fast(user_input)
                
                # 빠른 침묵 체크 (0.5초마다)
                if (current_time - last_silence_check >= 
                    self.silence_detection['silence_check_interval']):
                    
                    if self._should_handle_silence_smart():
                        await self._handle_silence_fast()
                    
                    last_silence_check = current_time
                
                # 대화 완료 체크
                if self._should_end_conversation_fast():
                    logger.info("✅ 대화 완료")
                    break
                
                await asyncio.sleep(0.2)  # 더 여유있는 루프
                        
            except Exception as e:
                logger.error(f"메인 루프 오류: {e}")
                await asyncio.sleep(0.1)
    
    def _start_fast_stt(self):
        """빠른 STT 시작"""
        
        def fast_stt_worker():
            """빠른 STT 워커"""
            try:
                self.stt_client.reset_stream()
                
                def immediate_transcript_handler(start_time, transcript, is_final=False):
                    if is_final and transcript.alternatives:
                        text = transcript.alternatives[0].text.strip()
                        if text and len(text) > 1:
                            try:
                                # 큐가 가득 차면 오래된 것 제거
                                if self.stt_queue.full():
                                    try:
                                        self.stt_queue.get_nowait()
                                    except queue.Empty:
                                        pass
                                
                                self.stt_queue.put_nowait(text)
                                
                            except queue.Full:
                                pass  # 조용히 무시
                
                self.stt_client.print_transcript = immediate_transcript_handler
                
                # STT 스트리밍 실행
                while self.is_running:
                    try:
                        self.stt_client.transcribe_streaming_grpc()
                    except Exception as e:
                        if self.is_running:
                            logger.error(f"STT 스트리밍 오류: {e}")
                        break
                    
            except Exception as e:
                if self.is_running:
                    logger.error(f"빠른 STT 워커 오류: {e}")
        
        # 빠른 시작
        stt_thread = threading.Thread(target=fast_stt_worker, daemon=True)
        stt_thread.start()
        self.is_listening = True
        
        logger.info("🎤 빠른 STT 시작")
    
    def _start_simple_audio_monitoring(self):
        """간단한 오디오 모니터링"""
        
        def simple_audio_monitor():
            try:
                import pyaudio
                
                chunk = 512  # 더 작은 청크
                p = pyaudio.PyAudio()
                
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=chunk
                )
                
                self.audio_monitor['is_monitoring'] = True
                
                while self.is_running and self.audio_monitor['is_monitoring']:
                    try:
                        data = stream.read(chunk, exception_on_overflow=False)
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        audio_level = np.abs(audio_data).mean() / 32768.0
                        
                        self.audio_monitor['audio_level'] = audio_level
                        
                        if audio_level > self.audio_monitor['silence_threshold']:
                            self.audio_monitor['last_audio_time'] = time.time()
                            self.silence_detection['last_audio_activity'] = time.time()
                        
                    except Exception:
                        break
                
                stream.stop_stream()
                stream.close()
                p.terminate()
                
            except Exception as e:
                logger.error(f"오디오 모니터링 오류: {e}")
            finally:
                self.audio_monitor['is_monitoring'] = False
        
        # 간단한 모니터링 시작
        monitor_thread = threading.Thread(target=simple_audio_monitor, daemon=True)
        monitor_thread.start()
    
    def _get_stt_result_immediate(self) -> Optional[str]:
        """STT 결과 가져오기 (품질 필터링)"""
        try:
            text = self.stt_queue.get_nowait()
            
            # 후처리 교정 추가 
            text = self._post_process_correction(text)

            # 품질 필터링
            if len(text) < self.stt_quality['min_text_length']:
                return None
            
            # AI 응답 직후에는 잠시 대기
            last_ai_time = self.stt_quality.get('last_ai_response_time')
            if last_ai_time:
                time_since_ai = time.time() - last_ai_time
                if time_since_ai < self.stt_quality['min_wait_after_ai']:
                    return None
            
            # 너무 짧은 단어들 필터링
            short_words = ['네', '예', '응', '어', '음', '말', '것', '좀', '그', '이']
            if text.strip() in short_words:
                return None
            
            return text
        except queue.Empty:
            return None
        
    def _post_process_correction(self, text: str) -> str:
        """STT 결과 후처리 교정 작업"""
        corrections = {
            "지금정지": "지급정지",
            "지금 정지": "지급정지", 
            "보이스 삐싱": "보이스피싱",
            "보이스삐싱": "보이스피싱",
            "보이스미싱": "보이스피싱",
            "일 삼 이": "132",
            "일삼이": "132", 
            "일 팔 일 일": "1811",
            "일팔일일": "1811",
            "명의 도용": "명의도용",
            "계좌 이체": "계좌이체",
            "사기 신고": "사기신고"
        }

        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)

        return text
    
    async def _process_user_input_fast(self, user_input: str):
        """빠른 사용자 입력 처리 (3초 이내 목표)"""
        
        start_time = time.time()
        self.is_processing = True
        
        logger.info(f"👤 사용자: {user_input}")
        
        # 상태 변경
        self._set_state(ConversationState.PROCESSING)
        
        # 콜백 호출
        if self.callbacks['on_user_speech']:
            self.callbacks['on_user_speech'](user_input)
        
        try:
            # LangGraph 빠른 처리 (2초 타임아웃)
            self.current_langgraph_state = await asyncio.wait_for(
                self.langgraph.continue_conversation(
                    self.current_langgraph_state, 
                    user_input
                ),
                timeout=2.0
            )
            
            # AI 응답 빠른 처리
            await self._handle_ai_response_fast()
            
            # 성능 통계 업데이트
            processing_time = time.time() - start_time
            self._update_performance_stats_fast(processing_time)
            
            self.stats['total_turns'] += 1
            
            # 빠른 응답 체크
            if processing_time <= 3.0:
                self.stats['fast_responses'] += 1
            
            # 다음 상태로
            if self._is_conversation_complete_fast():
                await self.stop_conversation()
            else:
                self._set_state(ConversationState.LISTENING)
            
        except asyncio.TimeoutError:
            logger.warning("⏰ 처리 시간 초과 - 빠른 응답 생성")
            await self._handle_timeout_response_fast(user_input)
        except Exception as e:
            logger.error(f"입력 처리 오류: {e}")
            await self._handle_error_fast("처리 중 문제가 발생했습니다.")
        finally:
            self.is_processing = False
    
    async def _handle_ai_response_fast(self):
        """AI 응답 빠른 처리"""
        
        if not self.current_langgraph_state or not self.current_langgraph_state.get('messages'):
            return
        
        last_message = self.current_langgraph_state['messages'][-1]
        if last_message.get('role') != 'assistant':
            return
        
        ai_response = last_message['content']
        
        # 응답 길이 강제 제한 (80자)
        if len(ai_response) > 80:
            ai_response = ai_response[:77] + "..."
        
        logger.info(f"🤖 AI: {ai_response}")
        
        # 콜백 호출
        if self.callbacks['on_ai_response']:
            self.callbacks['on_ai_response'](ai_response)
        
        # 빠른 TTS 처리
        await self._speak_response_fast(ai_response)
    
    async def _speak_response_fast(self, text: str):
        """빠른 TTS 처리 (AI 응답 시간 기록)"""
        
        self._set_state(ConversationState.SPEAKING)
        
        try:
            # 긴급도 체크
            is_emergency = any(word in text for word in ['긴급', '급해', '즉시', '당장'])
            
            if is_emergency:
                self.stats['emergency_handled'] += 1
                # 응급 상황용 TTS 최적화
                self.tts_service.optimize_for_emergency()
            
            # TTS 스트림 빠른 생성 (2초 타임아웃)
            audio_stream = await asyncio.wait_for(
                self._create_tts_stream_fast(text),
                timeout=2.0
            )
            
            # 즉시 오디오 재생
            await self.audio_manager.play_audio_stream(audio_stream)
            
            # AI 응답 시간 기록 (STT 필터링용)
            self.stt_quality['last_ai_response_time'] = time.time()
            
            logger.info("🔊 빠른 TTS 완료")
            
        except asyncio.TimeoutError:
            logger.warning("⏰ TTS 시간 초과 - 텍스트 출력")
            print(f"🤖 {text}")
            # 응답 시간 기록
            self.stt_quality['last_ai_response_time'] = time.time()
        except Exception as e:
            logger.error(f"TTS 오류: {e}")
            # TTS 실패 시 텍스트 출력
            print(f"🤖 {text}")
            # 응답 시간 기록
            self.stt_quality['last_ai_response_time'] = time.time()
    
    async def _create_tts_stream_fast(self, text: str):
        """빠른 TTS 스트림 생성"""
        return self.tts_service.text_to_speech_stream(text)
    
    async def _handle_timeout_response_fast(self, user_input: str):
        """타임아웃 시 빠른 응답"""
        
        # 간단한 키워드 기반 빠른 응답
        user_lower = user_input.lower()
        
        if any(word in user_lower for word in ['돈', '송금', '보냈', '급해']):
            quick_response = "즉시 일삼이번으로 전화하세요."
        elif any(word in user_lower for word in ['의심', '이상']):
            quick_response = "일삼이번으로 상담받으세요."
        else:
            quick_response = "도움이 필요하시면 일삼이번으로 연락하세요."
        
        # 직접 응답 추가
        if self.current_langgraph_state:
            self.current_langgraph_state['messages'].append({
                "role": "assistant",
                "content": quick_response,
                "timestamp": datetime.now(),
                "type": "timeout_response"
            })
        
        await self._speak_response_fast(quick_response)
    
    async def _handle_initial_greeting_fast(self):
        """초기 인사말 빠른 처리"""
        
        if self.current_langgraph_state and self.current_langgraph_state.get('messages'):
            greeting = self.current_langgraph_state['messages'][-1]['content']
            
            # 인사말도 길이 제한
            if len(greeting) > 80:
                greeting = "상담센터입니다. 급하게 도움이 필요한 상황인가요?"
            
            logger.info("🔊 초기 인사말 빠른 재생")
            await self._speak_response_fast(greeting)
    
    async def _handle_error_fast(self, error_message: str):
        """빠른 오류 처리"""
        
        self._set_state(ConversationState.ERROR)
        logger.error(f"빠른 오류 처리: {error_message}")
        
        # 간단한 오류 메시지
        simple_error = "문제가 발생했습니다. 일일이번으로 신고하세요."
        await self._speak_response_fast(simple_error)
        
        # 즉시 리스닝 상태로
        self._set_state(ConversationState.LISTENING)
    
    def _should_handle_silence_smart(self) -> bool:
        """스마트한 침묵 처리 여부 판단"""
        
        if not self.silence_detection['enabled']:
            return False
        
        if self.silence_detection['is_first_interaction']:
            return False
        
        if self.is_processing:
            return False
        
        current_time = time.time()
        
        # AI 응답 직후에는 추가 대기
        last_ai_time = self.stt_quality.get('last_ai_response_time')
        if last_ai_time:
            time_since_ai = current_time - last_ai_time
            min_silence_after_ai = self.silence_detection.get('min_silence_after_ai', 3.0)
            if time_since_ai < min_silence_after_ai:
                return False
        
        # 음성 인식 기반 체크
        last_speech_time = self.silence_detection.get('last_speech_time')
        speech_silence = float('inf')
        if last_speech_time:
            speech_silence = current_time - last_speech_time
        
        # 오디오 활동 기반 체크
        last_audio_time = self.silence_detection.get('last_audio_activity')
        audio_silence = float('inf')
        if last_audio_time:
            audio_silence = current_time - last_audio_time
        
        # 더 관대한 침묵 시간 사용
        silence_duration = min(speech_silence, audio_silence)
        
        return silence_duration >= self.silence_detection['timeout']
    
    async def _handle_silence_fast(self):
        """빠른 침묵 처리"""
        
        logger.info("⏰ 침묵 감지 - 간단한 후속 질문")
        
        # 시간 리셋
        self.silence_detection['last_speech_time'] = time.time()
        self.silence_detection['last_audio_activity'] = time.time()
        
        # 간단한 후속 질문
        follow_up = self._generate_simple_follow_up()
        
        # 빠른 전송
        await self._send_follow_up_fast(follow_up)
    
    def _generate_simple_follow_up(self) -> str:
        """간단한 후속 질문 생성"""
        
        if not self.current_langgraph_state:
            return "더 도움이 필요하신가요?"
        
        urgency = self.current_langgraph_state.get('urgency_level', 3)
        
        if urgency >= 8:
            return "지금 조치하고 계신가요?"
        elif urgency >= 6:
            return "더 궁금한 점이 있으신가요?"
        else:
            return "다른 질문이 있으시면 말씀하세요."
    
    async def _send_follow_up_fast(self, question: str):
        """빠른 후속 질문 전송"""
        
        try:
            # LangGraph 상태에 추가
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
            
            # 빠른 TTS 재생
            await self._speak_response_fast(question)
            
        except Exception as e:
            logger.error(f"후속 질문 전송 오류: {e}")
    
    def _should_end_conversation_fast(self) -> bool:
        """빠른 대화 종료 판단"""
        
        if not self.current_langgraph_state:
            return False
        
        # 완료 상태 체크
        if self.current_langgraph_state.get('current_step') == 'consultation_complete':
            return True
        
        # 턴 수 체크 (8턴으로 제한)
        if self.stats['total_turns'] >= 8:
            return True
        
        # 세션 타임아웃 (10분)
        if self.stats['conversation_start_time']:
            elapsed = (datetime.now() - self.stats['conversation_start_time']).total_seconds()
            if elapsed > 600:  # 10분
                return True
        
        return False
    
    def _is_conversation_complete_fast(self) -> bool:
        """빠른 대화 완료 확인"""
        return self._should_end_conversation_fast()
    
    def _update_performance_stats_fast(self, processing_time: float):
        """빠른 성능 통계 업데이트"""
        
        # 응답 시간 추가 (최근 5개만)
        self.response_times.append(processing_time)
        
        if len(self.response_times) > self.max_response_history:
            self.response_times.pop(0)
        
        # 평균 계산
        if self.response_times:
            self.stats['avg_response_time'] = sum(self.response_times) / len(self.response_times)
    
    def _set_state(self, new_state: ConversationState):
        """빠른 상태 변경"""
        
        if self.conversation_state != new_state:
            old_state = self.conversation_state
            self.conversation_state = new_state
            
            # 콜백 호출
            if self.callbacks['on_state_change']:
                self.callbacks['on_state_change'](old_state, new_state)
    
    async def stop_conversation(self):
        """빠른 대화 중지"""
        
        logger.info("🛑 대화 중지")
        
        self.is_running = False
        self.is_listening = False
        
        # 간단한 마지막 인사
        farewell = "상담 완료되었습니다."
        await self._speak_response_fast(farewell)
    
    async def cleanup(self):
        """빠른 리소스 정리"""
        
        logger.info("🧹 음성 친화적 매니저 정리 중...")
        
        try:
            self.is_running = False
            self.is_listening = False
            self.is_processing = False
            
            # STT 정리
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
            
            # 성능 통계 출력
            self._print_simple_stats()
            
            logger.info("✅ 음성 친화적 정리 완료")
            
        except Exception as e:
            logger.error(f"정리 중 오류: {e}")
    
    def _print_simple_stats(self):
        """간단한 성능 통계 출력"""
        
        stats = self.stats
        
        if stats['conversation_start_time']:
            total_time = (datetime.now() - stats['conversation_start_time']).total_seconds()
            fast_rate = (stats['fast_responses'] / max(stats['total_turns'], 1)) * 100
            
            logger.info("📊 음성 친화적 통계:")
            logger.info(f"   총 대화 시간: {total_time:.1f}초")
            logger.info(f"   총 대화 턴: {stats['total_turns']}")
            logger.info(f"   빠른 응답률: {fast_rate:.1f}%")
            logger.info(f"   평균 응답 시간: {stats['avg_response_time']:.3f}초")
            logger.info(f"   응급 처리: {stats['emergency_handled']}회")
    
    # ========================================================================
    # 공개 메서드들
    # ========================================================================
    
    def get_conversation_status(self) -> Dict[str, Any]:
        """간단한 대화 상태 정보"""
        
        elapsed_time = 0
        if self.stats['conversation_start_time']:
            elapsed_time = (datetime.now() - self.stats['conversation_start_time']).total_seconds()
        
        return {
            "state": self.conversation_state.value,
            "session_id": self.session_id,
            "total_turns": self.stats['total_turns'],
            "is_running": self.is_running,
            "is_listening": self.is_listening,
            "is_processing": self.is_processing,
            "elapsed_time": elapsed_time,
            "avg_response_time": self.stats['avg_response_time'],
            "fast_response_rate": f"{(self.stats['fast_responses'] / max(self.stats['total_turns'], 1)) * 100:.1f}%",
            "emergency_handled": self.stats['emergency_handled']
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
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """간단한 성능 지표"""
        
        return {
            **self.stats,
            "current_queue_size": self.stt_queue.qsize(),
            "response_time_history": self.response_times.copy(),
            "audio_level": self.audio_monitor.get('audio_level', 0.0),
            "is_monitoring": self.audio_monitor.get('is_monitoring', False)
        }
    
    def get_audio_status(self) -> dict:
        """오디오 상태 조회"""
        
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
            'silence_timeout': self.silence_detection['timeout']
        }


# 하위 호환성을 위한 별칭
ConversationManager = VoiceFriendlyConversationManager
HighPerformanceConversationManager = VoiceFriendlyConversationManager