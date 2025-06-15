import asyncio
import io
import logging
import time
import hashlib
from typing import AsyncGenerator, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from elevenlabs import ElevenLabs, AsyncElevenLabs
from config.settings import settings

logger = logging.getLogger(__name__)

class OptimizedTTSService:
    """
    최적화된 ElevenLabs TTS 서비스
    - 응답 속도 최적화
    - 메모리 효율성 개선
    - 캐싱 시스템
    - 에러 복구 강화
    - 적응형 품질 조정
    """
    
    def __init__(self):
        # API 키 확인
        if not settings.ELEVENLABS_API_KEY:
            logger.warning("ElevenLabs API key not found. TTS will be disabled.")
            self.client = None
            self.async_client = None
            self.is_enabled = False
        else:
            self.client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
            self.async_client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
            self.is_enabled = True
        
        # 최적화된 음성 설정
        self.voice_config = {
            'voice_id': settings.TTS_VOICE_ID,
            'model': settings.TTS_MODEL,
            'output_format': 'mp3_44100_128',  # 최적화된 포맷
            'optimize_latency': settings.TTS_OPTIMIZE_LATENCY
        }
        
        # 성능 최적화 설정
        self.performance_config = {
            'max_chunk_size': 500,      # 최대 텍스트 청크 크기
            'stream_chunk_size': 4096,  # 스트림 청크 크기
            'timeout': 10.0,            # 요청 타임아웃
            'max_retries': 2,           # 최대 재시도 횟수
            'cache_ttl': 3600,          # 캐시 TTL (1시간)
            'max_cache_size': 50        # 최대 캐시 항목 수
        }
        
        # 캐싱 시스템
        self.response_cache = {}
        self.cache_stats = {'hits': 0, 'misses': 0}
        
        # 스레드 풀 (비동기 처리용)
        self.thread_pool = ThreadPoolExecutor(
            max_workers=3, 
            thread_name_prefix="TTS"
        )
        
        # 성능 통계
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0.0,
            'cache_hit_rate': 0.0,
            'total_characters': 0
        }
        
        # 응답 시간 추적
        self.response_times = []
        self.max_response_history = 20
        
    async def text_to_speech_stream(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        최적화된 실시간 TTS 스트리밍
        - 캐싱 활용
        - 청크 단위 처리
        - 오류 복구
        """
        
        if not self.is_enabled:
            logger.error("TTS 서비스가 비활성화됨")
            yield b''
            return
        
        start_time = time.time()
        self.stats['total_requests'] += 1
        
        try:
            # 텍스트 전처리
            processed_text = self._preprocess_text(text)
            
            # 캐시 확인
            cache_key = self._generate_cache_key(processed_text)
            cached_result = self._get_from_cache(cache_key)
            
            if cached_result:
                self.cache_stats['hits'] += 1
                logger.debug(f"캐시 히트: {processed_text[:30]}...")
                
                # 캐시된 데이터를 청크로 분할하여 yield
                async for chunk in self._stream_cached_data(cached_result):
                    yield chunk
                
                self._update_success_stats(start_time)
                return
            
            self.cache_stats['misses'] += 1
            
            # 텍스트가 너무 길면 분할 처리
            if len(processed_text) > self.performance_config['max_chunk_size']:
                async for chunk in self._process_long_text(processed_text, cache_key):
                    yield chunk
            else:
                async for chunk in self._process_short_text(processed_text, cache_key):
                    yield chunk
            
            self._update_success_stats(start_time)
            
        except Exception as e:
            logger.error(f"TTS 스트리밍 오류: {e}")
            self.stats['failed_requests'] += 1
            
            # 폴백 처리
            async for chunk in self._handle_tts_error(text):
                yield chunk
    
    async def _process_short_text(self, text: str, cache_key: str) -> AsyncGenerator[bytes, None]:
        """짧은 텍스트 처리"""
        
        try:
            # ElevenLabs API 호출 (비동기 최적화)
            audio_data = await self._call_elevenlabs_api(text)
            
            if audio_data:
                # 캐시에 저장
                self._save_to_cache(cache_key, audio_data)
                
                # 청크 단위로 스트리밍
                async for chunk in self._stream_audio_data(audio_data):
                    yield chunk
            else:
                logger.warning("TTS API로부터 빈 응답")
                yield b''
                
        except Exception as e:
            logger.error(f"짧은 텍스트 처리 오류: {e}")
            yield b''
    
    async def _process_long_text(self, text: str, base_cache_key: str) -> AsyncGenerator[bytes, None]:
        """긴 텍스트 분할 처리"""
        
        # 문장 단위로 분할
        sentences = self._split_text_intelligently(text)
        
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            
            try:
                # 각 문장별 캐시 키
                sentence_cache_key = f"{base_cache_key}_part_{i}"
                
                # 캐시 확인
                cached_audio = self._get_from_cache(sentence_cache_key)
                
                if cached_audio:
                    async for chunk in self._stream_cached_data(cached_audio):
                        yield chunk
                else:
                    # API 호출
                    audio_data = await self._call_elevenlabs_api(sentence.strip())
                    
                    if audio_data:
                        self._save_to_cache(sentence_cache_key, audio_data)
                        async for chunk in self._stream_audio_data(audio_data):
                            yield chunk
                
                # 문장 간 짧은 휴식 (자연스러운 발음)
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"문장 처리 오류: {e}")
                continue
    
    async def _call_elevenlabs_api(self, text: str) -> bytes:
        """ElevenLabs API 호출 (최적화)"""
        
        def sync_api_call():
            """동기 API 호출 (스레드에서 실행)"""
            try:
                # stream 방식으로 호출 (더 빠름)
                audio_stream = self.client.text_to_speech.stream(
                    text=text,
                    voice_id=self.voice_config['voice_id'],
                    model_id=self.voice_config['model'],
                    output_format=self.voice_config['output_format']
                )
                
                # 스트림 데이터 수집
                chunks = []
                for chunk in audio_stream:
                    if isinstance(chunk, bytes):
                        chunks.append(chunk)
                
                return b''.join(chunks)
                
            except Exception as e:
                logger.warning(f"stream 호출 실패, convert로 폴백: {e}")
                
                # convert 방식으로 폴백
                try:
                    audio_generator = self.client.text_to_speech.convert(
                        text=text,
                        voice_id=self.voice_config['voice_id'],
                        model_id=self.voice_config['model'],
                        output_format=self.voice_config['output_format']
                    )
                    
                    chunks = []
                    for chunk in audio_generator:
                        if isinstance(chunk, bytes):
                            chunks.append(chunk)
                    
                    return b''.join(chunks)
                    
                except Exception as fallback_error:
                    logger.error(f"convert 폴백도 실패: {fallback_error}")
                    return b''
        
        # 스레드 풀에서 비동기 실행
        try:
            audio_data = await asyncio.wait_for(
                asyncio.to_thread(sync_api_call),
                timeout=self.performance_config['timeout']
            )
            
            self.stats['total_characters'] += len(text)
            return audio_data
            
        except asyncio.TimeoutError:
            logger.error(f"TTS API 타임아웃: {text[:50]}...")
            return b''
        except Exception as e:
            logger.error(f"TTS API 호출 오류: {e}")
            return b''
    
    async def _stream_audio_data(self, audio_data: bytes) -> AsyncGenerator[bytes, None]:
        """오디오 데이터 청크 스트리밍"""
        
        chunk_size = self.performance_config['stream_chunk_size']
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            if chunk:
                yield chunk
                # 스트리밍 지연 최소화
                await asyncio.sleep(0.001)
    
    async def _stream_cached_data(self, cached_data: bytes) -> AsyncGenerator[bytes, None]:
        """캐시된 데이터 스트리밍"""
        async for chunk in self._stream_audio_data(cached_data):
            yield chunk
    
    async def _handle_tts_error(self, original_text: str) -> AsyncGenerator[bytes, None]:
        """TTS 오류 처리"""
        
        logger.info("TTS 오류 - 빈 응답 반환")
        yield b''
    
    def _preprocess_text(self, text: str) -> str:
        """텍스트 전처리"""
        
        # 기본 정리
        processed = text.strip()
        
        # 너무 긴 텍스트 자르기
        max_length = 1000
        if len(processed) > max_length:
            # 문장 경계에서 자르기
            sentences = processed.split('.')
            truncated = []
            current_length = 0
            
            for sentence in sentences:
                if current_length + len(sentence) > max_length:
                    break
                truncated.append(sentence)
                current_length += len(sentence)
            
            processed = '.'.join(truncated)
            if not processed.endswith('.'):
                processed += '.'
        
        # 특수 문자 처리
        processed = processed.replace('🚨', '긴급:')
        processed = processed.replace('⚠️', '주의:')
        processed = processed.replace('✅', '완료:')
        processed = processed.replace('📞', '연락처:')
        
        return processed
    
    def _split_text_intelligently(self, text: str) -> list:
        """지능적 텍스트 분할"""
        
        # 문장 분할 우선순위
        splitters = ['. ', '! ', '? ', '\n', ':', ';']
        
        sentences = [text]
        
        for splitter in splitters:
            new_sentences = []
            for sentence in sentences:
                if splitter in sentence:
                    parts = sentence.split(splitter)
                    for i, part in enumerate(parts):
                        if part.strip():
                            if i < len(parts) - 1:
                                new_sentences.append(part + splitter.strip())
                            else:
                                new_sentences.append(part)
                else:
                    new_sentences.append(sentence)
            sentences = new_sentences
        
        # 너무 짧은 문장들 합치기
        final_sentences = []
        current_group = []
        
        for sentence in sentences:
            current_group.append(sentence)
            
            # 50자 이상이거나 마지막 문장이면 그룹 완성
            if (sum(len(s) for s in current_group) >= 50 or 
                sentence == sentences[-1]):
                final_sentences.append(' '.join(current_group))
                current_group = []
        
        return final_sentences
    
    def _generate_cache_key(self, text: str) -> str:
        """캐시 키 생성"""
        
        # 텍스트와 음성 설정을 포함한 해시
        content = f"{text}_{self.voice_config['voice_id']}_{self.voice_config['model']}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> Optional[bytes]:
        """캐시에서 데이터 조회"""
        
        if cache_key in self.response_cache:
            cache_entry = self.response_cache[cache_key]
            
            # TTL 확인
            if time.time() - cache_entry['timestamp'] < self.performance_config['cache_ttl']:
                return cache_entry['data']
            else:
                # 만료된 캐시 삭제
                del self.response_cache[cache_key]
        
        return None
    
    def _save_to_cache(self, cache_key: str, data: bytes):
        """캐시에 데이터 저장"""
        
        # 캐시 크기 제한
        if len(self.response_cache) >= self.performance_config['max_cache_size']:
            # 가장 오래된 항목 삭제
            oldest_key = min(
                self.response_cache.keys(),
                key=lambda k: self.response_cache[k]['timestamp']
            )
            del self.response_cache[oldest_key]
        
        self.response_cache[cache_key] = {
            'data': data,
            'timestamp': time.time()
        }
    
    def _update_success_stats(self, start_time: float):
        """성공 통계 업데이트"""
        
        self.stats['successful_requests'] += 1
        
        # 응답 시간 계산
        response_time = time.time() - start_time
        self.response_times.append(response_time)
        
        # 히스토리 크기 제한
        if len(self.response_times) > self.max_response_history:
            self.response_times.pop(0)
        
        # 평균 응답 시간 계산
        if self.response_times:
            self.stats['avg_response_time'] = sum(self.response_times) / len(self.response_times)
        
        # 캐시 히트율 계산
        total_cache_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        if total_cache_requests > 0:
            self.stats['cache_hit_rate'] = self.cache_stats['hits'] / total_cache_requests
    
    async def text_to_speech_file(self, text: str) -> bytes:
        """파일 방식 TTS (호환성용)"""
        
        audio_chunks = []
        async for chunk in self.text_to_speech_stream(text):
            if chunk:
                audio_chunks.append(chunk)
        
        return b''.join(audio_chunks)
    
    async def test_connection(self) -> bool:
        """연결 테스트 (최적화)"""
        
        if not self.is_enabled:
            return False
        
        try:
            test_audio = await asyncio.wait_for(
                self.text_to_speech_file("테스트"),
                timeout=5.0
            )
            
            success = len(test_audio) > 0
            logger.info(f"TTS 연결 테스트: {'성공' if success else '실패'}")
            return success
            
        except asyncio.TimeoutError:
            logger.error("TTS 테스트 타임아웃")
            return False
        except Exception as e:
            logger.error(f"TTS 테스트 실패: {e}")
            return False
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """성능 통계 조회"""
        
        return {
            **self.stats,
            'cache_stats': self.cache_stats.copy(),
            'cache_size': len(self.response_cache),
            'is_enabled': self.is_enabled,
            'response_time_history': self.response_times.copy()
        }
    
    def clear_cache(self):
        """캐시 정리"""
        
        cache_size = len(self.response_cache)
        self.response_cache.clear()
        self.cache_stats = {'hits': 0, 'misses': 0}
        
        logger.info(f"TTS 캐시 정리 완료: {cache_size}개 항목 삭제")
    
    def optimize_for_speed(self):
        """속도 최적화 설정"""
        
        self.performance_config.update({
            'max_chunk_size': 300,
            'timeout': 5.0,
            'max_cache_size': 100
        })
        
        self.voice_config['output_format'] = 'mp3_22050_32'  # 낮은 품질, 빠른 속도
        logger.info("🚀 TTS 속도 최적화 모드 활성화")
    
    def optimize_for_quality(self):
        """품질 최적화 설정"""
        
        self.performance_config.update({
            'max_chunk_size': 800,
            'timeout': 15.0,
            'max_cache_size': 20
        })
        
        self.voice_config['output_format'] = 'mp3_44100_192'  # 높은 품질
        logger.info("🎵 TTS 품질 최적화 모드 활성화")
    
    def cleanup(self):
        """리소스 정리"""
        
        try:
            logger.info("🧹 TTS 서비스 정리 중...")
            
            # 캐시 정리
            self.clear_cache()
            
            # 스레드 풀 종료
            if self.thread_pool:
                self.thread_pool.shutdown(wait=True, timeout=3)
            
            # 최종 통계 출력
            stats = self.get_performance_stats()
            logger.info("📊 TTS 최종 통계:")
            logger.info(f"   총 요청: {stats['total_requests']}")
            logger.info(f"   성공률: {stats['successful_requests']}/{stats['total_requests']}")
            logger.info(f"   캐시 히트율: {stats['cache_hit_rate']:.1%}")
            logger.info(f"   평균 응답시간: {stats['avg_response_time']:.3f}초")
            
            logger.info("✅ TTS 서비스 정리 완료")
            
        except Exception as e:
            logger.error(f"TTS 정리 오류: {e}")


# 하위 호환성을 위한 별칭 및 전역 인스턴스
TTSService = OptimizedTTSService
tts_service = OptimizedTTSService()

# import asyncio
# import io
# import logging
# from typing import AsyncGenerator
# from elevenlabs import ElevenLabs, AsyncElevenLabs
# from config.settings import settings

# logger = logging.getLogger(__name__)

# class TTSService:
#     """
#     ElevenLabs TTS 서비스 (공식 Python SDK 기준)
    
#     올바른 SDK 메서드 사용:
#     - client.text_to_speech.convert() - 파일 생성
#     - client.text_to_speech.stream() - 스트리밍
#     """
    
#     def __init__(self):
#         if not settings.ELEVENLABS_API_KEY:
#             logger.warning("ElevenLabs API key not found. TTS will be disabled.")
#             self.client = None
#             self.async_client = None
#         else:
#             self.client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
#             self.async_client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)
        
#         # 음성 설정
#         self.voice_id = settings.TTS_VOICE_ID
#         self.model = settings.TTS_MODEL
    
#     async def text_to_speech_stream(self, text: str) -> AsyncGenerator[bytes, None]:
#         """
#         텍스트를 실시간 오디오 스트림으로 변환
#         공식 SDK stream() 메서드 사용
#         """
        
#         if not self.client:
#             logger.error("TTS client not initialized")
#             return
        
#         try:
#             logger.info(f"🔊 TTS 스트림 시작: {text[:50]}...")
            
#             # 공식 SDK 스트리밍 메서드 사용 (동기 버전이 더 안정적)
#             def generate_stream():
#                 audio_stream = self.client.text_to_speech.stream(
#                     text=text,
#                     voice_id=self.voice_id,
#                     model_id=self.model,
#                     output_format="mp3_44100_128"
#                 )
                
#                 # 스트림을 수집
#                 chunks = []
#                 for chunk in audio_stream:
#                     if isinstance(chunk, bytes):
#                         chunks.append(chunk)
                
#                 return b''.join(chunks)
            
#             # 별도 스레드에서 실행
#             audio_data = await asyncio.to_thread(generate_stream)
            
#             if audio_data:
#                 # 청크 단위로 yield
#                 chunk_size = 4096
#                 for i in range(0, len(audio_data), chunk_size):
#                     yield audio_data[i:i + chunk_size]
                
#                 logger.info(f"✅ TTS 스트림 완료: {len(audio_data)} bytes")
#             else:
#                 logger.warning("❌ TTS 스트림 데이터 없음")
#                 yield b''
                    
#         except Exception as e:
#             logger.error(f"TTS streaming error: {e}")
#             # 폴백으로 convert 사용
#             try:
#                 logger.info("🔄 convert 메서드로 폴백...")
#                 audio_data = await self.text_to_speech_file(text)
#                 if audio_data:
#                     yield audio_data
#                 else:
#                     yield b''
#             except Exception as fallback_error:
#                 logger.error(f"폴백 오류: {fallback_error}")
#                 yield b''
    
#     async def text_to_speech_file(self, text: str) -> bytes:
#         """
#         텍스트를 오디오 파일로 변환
#         공식 SDK convert() 메서드 사용
#         """
        
#         if not self.client:
#             return b''
        
#         try:
#             logger.info(f"🔊 TTS 파일 변환: {text[:30]}...")
            
#             def generate_audio():
#                 # 공식 SDK convert 메서드 사용
#                 audio_generator = self.client.text_to_speech.convert(
#                     text=text,
#                     voice_id=self.voice_id,
#                     model_id=self.model,
#                     output_format="mp3_44100_128"
#                 )
                
#                 # generator를 bytes로 변환
#                 chunks = []
#                 for chunk in audio_generator:
#                     if isinstance(chunk, bytes):
#                         chunks.append(chunk)
                
#                 return b''.join(chunks)
            
#             # 별도 스레드에서 실행
#             audio_data = await asyncio.to_thread(generate_audio)
            
#             if audio_data:
#                 logger.info(f"✅ TTS 파일 변환 완료: {len(audio_data)} bytes")
#             else:
#                 logger.warning("❌ TTS 데이터 없음")
                
#             return audio_data
            
#         except Exception as e:
#             logger.error(f"TTS conversion error: {e}")
#             return b''
    
#     async def test_connection(self) -> bool:
#         """TTS 서비스 연결 테스트"""
        
#         if not self.client:
#             logger.warning("TTS 클라이언트가 초기화되지 않음")
#             return False
        
#         try:
#             # 간단한 테스트
#             test_audio = await self.text_to_speech_file("테스트")
#             success = len(test_audio) > 0
            
#             if success:
#                 logger.info("✅ TTS 연결 테스트 성공")
#                 logger.info(f"📊 테스트 오디오 크기: {len(test_audio)} bytes")
#             else:
#                 logger.warning("❌ TTS 연결 테스트 실패 - 빈 응답")
                
#             return success
            
#         except Exception as e:
#             logger.error(f"TTS test failed: {e}")
#             return False
    
#     def test_sync_basic(self) -> bool:
#         """동기 기본 테스트 (디버깅용)"""
        
#         if not self.client:
#             return False
        
#         try:
#             logger.info("🧪 동기 기본 테스트...")
            
#             # 가장 기본적인 사용법
#             audio_generator = self.client.text_to_speech.convert(
#                 text="테스트",
#                 voice_id=self.voice_id,
#                 model_id=self.model
#             )
            
#             # 첫 번째 청크만 확인
#             first_chunk = next(iter(audio_generator))
#             success = isinstance(first_chunk, bytes) and len(first_chunk) > 0
            
#             if success:
#                 logger.info("✅ 동기 기본 테스트 성공")
#             else:
#                 logger.warning("❌ 동기 기본 테스트 실패")
            
#             return success
            
#         except Exception as e:
#             logger.error(f"동기 기본 테스트 오류: {e}")
#             return False

# # 전역 TTS 서비스 인스턴스
# tts_service = TTSService()