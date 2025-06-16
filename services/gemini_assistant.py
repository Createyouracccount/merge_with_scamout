import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("google-generativeai 패키지가 설치되지 않음. pip install google-generativeai")

from config.settings import settings

logger = logging.getLogger(__name__)

class GeminiAssistant:
    """
    Gemini API 통합 보이스피싱 상담 어시스턴트
    """
    
    def __init__(self):
        self.is_enabled = False
        
        # Gemini 사용 가능성 체크
        if not GEMINI_AVAILABLE:
            logger.warning("❌ Gemini 라이브러리 없음 - 규칙 기반으로 동작")
            return
            
        if not settings.GEMINI_API_KEY:
            logger.warning("❌ GEMINI_API_KEY 없음 - 규칙 기반으로 동작")
            return
        
        # Gemini 초기화
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.model = genai.GenerativeModel(settings.GEMINI_MODEL)
            self.is_enabled = True
            logger.info("✅ Gemini AI 초기화 완료")
        except Exception as e:
            logger.error(f"❌ Gemini 초기화 실패: {e}")
            self.is_enabled = False
        
        # 시스템 프롬프트
        self.system_prompt = """
당신은 보이스피싱 피해자를 돕는 전문 상담원입니다.

## 핵심 원칙
1. **3일 환급 신청 기한**을 절대 놓치지 마세요
2. **즉시 조치사항**을 긴급도에 따라 안내하세요  
3. **자연스럽고 따뜻한 대화**로 피해자를 안심시키세요
4. **불확실한 법적/의료 조언**은 절대 하지 마세요

## 즉시 조치사항 (긴급도 8 이상)
1. 즉시 112(경찰) 또는 1332(금감원)에 신고
2. 송금한 은행 고객센터에 지급정지 신청  
3. 휴대폰을 비행기모드로 전환 또는 전원 끄기

## 3일 규칙 (반드시 강조)
"3일 이내 경찰서에서 사건사고사실확인원을 발급받아 은행에 제출해야 환급 가능합니다"

## 응답 형식
항상 JSON 형식으로 응답하세요:
{
    "response": "사용자에게 할 말 (200자 이내)",
    "urgency_level": 1-10,
    "extracted_info": {
        "amount": "금액 정보",
        "time": "시간 정보",
        "actions_taken": "이미 취한 조치"
    },
    "next_priority": "immediate_action/info_gathering/guidance/completion"
}
"""
        
        # 대화 기록
        self.conversation_history = []
        
        # 세션 상태
        self.session_state = {
            'total_turns': 0,
            'urgency_level': 3,
            'three_day_rule_mentioned': False
        }
    
    async def analyze_and_respond(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """사용자 입력 분석 및 응답 생성"""
        
        if not self.is_enabled:
            return self._rule_based_fallback(user_input)
        
        try:
            # Gemini API 호출
            gemini_response = await self._call_gemini_api(user_input, context)
            
            # 응답 검증 및 안전장치 적용
            validated_response = self._validate_response(gemini_response, user_input)
            
            # 상태 업데이트
            self._update_session_state(validated_response)
            
            # 대화 기록 추가
            self.conversation_history.append({
                'user': user_input,
                'assistant': validated_response.get('response', ''),
                'timestamp': datetime.now()
            })
            
            return validated_response
            
        except Exception as e:
            logger.error(f"Gemini 처리 오류: {e}")
            return self._emergency_fallback(user_input)
    
    async def _call_gemini_api(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Gemini API 호출"""
        
        # 대화 맥락 구성
        conversation_context = self._build_context()
        
        # 현재 상황 정보
        current_info = f"""
현재 대화 턴: {self.session_state['total_turns']}
현재 긴급도: {self.session_state['urgency_level']}
사용자 입력: "{user_input}"
"""
        
        if context:
            current_info += f"추가 컨텍스트: {context}"
        
        # 전체 프롬프트
        full_prompt = f"{self.system_prompt}\n\n{conversation_context}\n\n{current_info}"
        
        # Gemini에 요청
        response = await asyncio.to_thread(
            self.model.generate_content, 
            full_prompt
        )
        
        # JSON 파싱
        response_text = response.text.strip()
        
        # JSON 추출 (마크다운 제거)
        if '```json' in response_text:
            json_start = response_text.find('```json') + 7
            json_end = response_text.find('```', json_start)
            response_text = response_text[json_start:json_end].strip()
        elif '```' in response_text:
            json_start = response_text.find('```') + 3
            json_end = response_text.find('```', json_start)
            response_text = response_text[json_start:json_end].strip()
        
        try:
            parsed_response = json.loads(response_text)
            logger.info(f"✅ Gemini 응답 성공: 긴급도 {parsed_response.get('urgency_level')}")
            return parsed_response
        except json.JSONDecodeError:
            logger.warning(f"JSON 파싱 실패, 원본 응답 사용: {response_text}")
            return self._parse_raw_response(response_text)
    
    def _build_context(self) -> str:
        """대화 맥락 구성"""
        
        if not self.conversation_history:
            return "대화 시작"
        
        # 최근 2턴만 포함
        recent = self.conversation_history[-2:]
        context_parts = ["최근 대화:"]
        
        for turn in recent:
            context_parts.append(f"사용자: {turn['user']}")
            context_parts.append(f"상담원: {turn['assistant']}")
        
        return "\n".join(context_parts)
    
    def _parse_raw_response(self, raw_text: str) -> Dict[str, Any]:
        """원본 텍스트에서 정보 추출"""
        
        # 긴급도 추정
        urgency = 5
        if any(word in raw_text.lower() for word in ['긴급', '즉시', '빨리', '112', '1332']):
            urgency = 8
        elif any(word in raw_text.lower() for word in ['도움', '상담', '안내']):
            urgency = 6
        
        return {
            "response": raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
            "urgency_level": urgency,
            "extracted_info": {},
            "next_priority": "continue"
        }
    
    def _validate_response(self, response: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """응답 검증 및 안전장치"""
        
        validated = response.copy()
        
        # 1. 긴급도 안전장치
        user_lower = user_input.lower()
        
        # 긴급 키워드 감지 시 최소 긴급도 보장
        urgent_keywords = ['돈', '송금', '보냈', '이체', '급해', '도와', '사기', '억']
        if any(keyword in user_lower for keyword in urgent_keywords):
            validated['urgency_level'] = max(validated.get('urgency_level', 5), 7)
        
        # 2. 3일 규칙 강제 포함
        if (validated['urgency_level'] >= 7 and 
            '3일' not in validated['response'] and 
            not self.session_state['three_day_rule_mentioned']):
            
            original_response = validated['response']
            validated['response'] = f"{original_response}\n\n⚠️ 중요: 3일 이내 경찰서에서 사건사고사실확인원을 발급받아 은행에 제출해야 환급 가능합니다."
            self.session_state['three_day_rule_mentioned'] = True
        
        # 3. 응답 길이 제한
        if len(validated['response']) > settings.AI_RESPONSE_MAX_LENGTH:
            validated['response'] = validated['response'][:settings.AI_RESPONSE_MAX_LENGTH-3] + "..."
        
        # 4. 필수 연락처 포함 (긴급 시)
        if (validated['urgency_level'] >= 8 and 
            '112' not in validated['response'] and 
            '1332' not in validated['response']):
            
            validated['response'] += "\n\n🚨 즉시 112(경찰) 또는 1332(금감원)에 신고하세요."
        
        return validated
    
    def _update_session_state(self, response: Dict[str, Any]):
        """세션 상태 업데이트"""
        
        self.session_state['total_turns'] += 1
        self.session_state['urgency_level'] = response.get('urgency_level', 3)
    
    def _rule_based_fallback(self, user_input: str) -> Dict[str, Any]:
        """규칙 기반 폴백 (Gemini 비활성화 시)"""
        
        user_lower = user_input.lower()
        
        # 긴급도 계산
        urgency = 3
        urgent_words = ['돈', '송금', '보냈', '이체', '급해', '도와', '사기']
        
        for word in urgent_words:
            if word in user_lower:
                urgency += 2
        
        urgency = min(urgency, 10)
        
        # 응답 생성
        if urgency >= 8:
            response = """긴급 상황으로 보입니다.

🚨 즉시 해야 할 것:
1. 112(경찰) 또는 1332(금감원) 신고
2. 송금한 은행에 지급정지 신청
3. 휴대폰 비행기모드 전환

⚠️ 3일 이내 경찰서에서 사건사고사실확인원 발급받아 은행 제출해야 환급 가능합니다."""
        elif urgency >= 6:
            response = "상황을 이해했습니다. 어떤 일이 있었는지 자세히 말씀해 주시겠어요?"
        else:
            response = "보이스피싱 상담센터입니다. 어떤 도움이 필요하신가요?"
        
        return {
            "response": response,
            "urgency_level": urgency,
            "extracted_info": {},
            "next_priority": "info_gathering"
        }
    
    def _emergency_fallback(self, user_input: str) -> Dict[str, Any]:
        """비상 상황 폴백"""
        
        return {
            "response": "시스템에 일시적 문제가 있습니다. 긴급한 경우 112나 1332로 직접 연락하세요.",
            "urgency_level": 9,
            "extracted_info": {},
            "next_priority": "emergency_contact"
        }
    
    def get_session_status(self) -> Dict[str, Any]:
        """세션 상태 조회"""
        
        return {
            'is_ai_enabled': self.is_enabled,
            'total_turns': self.session_state['total_turns'],
            'urgency_level': self.session_state['urgency_level'],
            'three_day_rule_mentioned': self.session_state['three_day_rule_mentioned'],
            'conversation_length': len(self.conversation_history)
        }

# 전역 인스턴스
gemini_assistant = GeminiAssistant()