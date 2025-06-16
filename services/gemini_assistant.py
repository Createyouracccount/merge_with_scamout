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
    실질적 도움 제공 중심의 Gemini 보이스피싱 상담 어시스턴트
    """
    
    def __init__(self):
        self.is_enabled = False
        
        # Gemini 사용 가능성 체크
        if not GEMINI_AVAILABLE:
            logger.warning("❌ Gemini 라이브러리 없음 - 구조화된 모드 사용")
            return
            
        if not settings.GEMINI_API_KEY:
            logger.warning("❌ GEMINI_API_KEY 없음 - 구조화된 모드 사용")
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
        
        # 개선된 시스템 프롬프트 - 실질적 도움 중심
        self.system_prompt = """
당신은 실질적 도움을 제공하는 보이스피싱 전문 상담원입니다.

## 🎯 핵심 원칙: 당연한 말 대신 실질적 정보 제공

### ❌ 피해야 할 당연한 조치들
- "112에 신고하세요" (누구나 아는 정보)
- "경찰서에 가세요" (뻔한 얘기)
- "의심스러운 전화 차단하세요" (이미 당한 후)

### ✅ 제공해야 할 실질적 정보들

**🚨 즉시 조치사항 (긴급도 8+ 점)**
1. **mSAFER (www.msafer.or.kr)**: 휴대폰 명의도용 차단
   - PASS앱 → 전체 → '명의도용방지서비스'
   - 내 명의 모든 휴대폰 확인 후 명의도용시 즉시 해지

2. **보이스피싱제로 (voicephisingzero.co.kr)**: 확실한 300만원 지원
   - 중위소득 100% 이하면 생활비 300만원
   - 무료 법률상담 + 소송지원
   - 심리상담비 200만원

3. **payinfo.or.kr**: 계좌 명의도용 확인
   - 내가 모르는 계좌 개설 여부 확인
   - '내계좌 일괄지급정지' 기능 활용

4. **대한법률구조공단 132번**: 무료 전문 법률상담

**📞 중급 조치사항 (긴급도 6-7점)**
- 132번 무료 상담으로 개인 맞춤 전략 수립
- 보이스피싱제로 지원 조건 확인
- mSAFER 예방 서비스 등록

**🛡️ 예방 조치사항 (긴급도 5점 이하)**
- mSAFER 명의도용 방지 서비스 등록
- pd.fss.or.kr 개인정보노출자 등록
- 전문가 상담으로 정확한 상황 파악

### 🎯 핵심 메시지
"3일 환급 성공률은 30-40%이지만, 보이스피싱제로 생활비 지원은 조건만 맞으면 확실한 300만원입니다!"

## 응답 형식
항상 JSON 형식으로 응답하세요:
{
    "response": "실질적 도움이 되는 구체적 조치사항 (200자 이내)",
    "urgency_level": 1-10,
    "extracted_info": {
        "amount": "금액 정보",
        "time": "시간 정보",
        "actions_taken": "이미 취한 조치"
    },
    "next_priority": "immediate_action/expert_consultation/prevention/completion"
}
"""
        
        # 대화 기록
        self.conversation_history = []
        
        # 세션 상태
        self.session_state = {
            'total_turns': 0,
            'urgency_level': 3,
            'practical_guidance_provided': False
        }
    
    async def analyze_and_respond(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """실질적 도움 중심의 사용자 입력 분석 및 응답 생성"""
        
        if not self.is_enabled:
            return self._practical_rule_based_fallback(user_input)
        
        try:
            # Gemini API 호출
            gemini_response = await self._call_gemini_api(user_input, context)
            
            # 응답 검증 및 실질적 정보 강화
            validated_response = self._enhance_practical_guidance(gemini_response, user_input)
            
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
            return self._practical_emergency_fallback(user_input)
    
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
    
    def _enhance_practical_guidance(self, response: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """실질적 도움 정보 강화"""
        
        enhanced = response.copy()
        urgency = enhanced.get('urgency_level', 5)
        
        # 1. 긴급도별 실질적 조치 강화
        if urgency >= 8:
            if 'msafer' not in enhanced['response'].lower():
                enhanced['response'] = f"🚨 즉시: mSAFER (www.msafer.or.kr)에서 명의도용 차단하세요.\n\n{enhanced['response']}"
            
            if '보이스피싱제로' not in enhanced['response']:
                enhanced['response'] += "\n\n💰 확실한 지원: 보이스피싱제로 (voicephisingzero.co.kr)에서 300만원 생활비 지원"
        
        elif urgency >= 6:
            if '132' not in enhanced['response']:
                enhanced['response'] = f"📞 먼저: 대한법률구조공단 132번 무료 상담받으세요.\n\n{enhanced['response']}"
        
        # 2. 3일 환급의 현실 알림
        if urgency >= 7 and '3일' in enhanced['response']:
            enhanced['response'] += "\n\n🎯 참고: 3일 환급 성공률은 30-40%입니다. 보이스피싱제로 지원이 더 확실할 수 있어요."
        
        # 3. 응답 길이 제한
        if len(enhanced['response']) > settings.AI_RESPONSE_MAX_LENGTH:
            enhanced['response'] = enhanced['response'][:settings.AI_RESPONSE_MAX_LENGTH-3] + "..."
        
        return enhanced
    
    def _practical_rule_based_fallback(self, user_input: str) -> Dict[str, Any]:
        """실질적 도움 중심의 규칙 기반 폴백"""
        
        user_lower = user_input.lower()
        
        # 긴급도 계산
        urgency = 3
        urgent_words = ['돈', '송금', '보냈', '이체', '급해', '도와', '사기', '억', '만원']
        
        for word in urgent_words:
            if word in user_lower:
                urgency += 2
        
        urgency = min(urgency, 10)
        
        # 실질적 도움 응답 생성
        if urgency >= 8:
            response = """🚨 즉시 실행하세요:

1️⃣ mSAFER (www.msafer.or.kr)에서 명의도용 차단
2️⃣ 보이스피싱제로 (voicephisingzero.co.kr)에서 300만원 생활비 지원 신청
3️⃣ payinfo.or.kr에서 계좌 명의도용 확인

💡 3일 환급보다 300만원 지원이 더 확실합니다!"""

        elif urgency >= 6:
            response = """📞 전문가 상담 우선:

1️⃣ 대한법률구조공단 132번 무료 상담
2️⃣ 보이스피싱제로 지원 조건 확인
3️⃣ mSAFER 명의도용 방지 설정

개인 상황에 맞는 최적 전략을 수립하세요."""

        else:
            response = """🛡️ 예방 중심 조치:

1️⃣ mSAFER (www.msafer.or.kr) 명의도용 방지 서비스 등록
2️⃣ 132번으로 정확한 상황 확인
3️⃣ 실제 피해인지 전문가와 확인

예방이 가장 중요합니다."""
        
        return {
            "response": response,
            "urgency_level": urgency,
            "extracted_info": {},
            "next_priority": "practical_guidance"
        }
    
    def _practical_emergency_fallback(self, user_input: str) -> Dict[str, Any]:
        """실질적 도움 중심의 비상 폴백"""
        
        return {
            "response": """시스템 오류가 발생했습니다.

🚨 긴급한 경우:
1️⃣ mSAFER (www.msafer.or.kr)에서 명의도용 차단
2️⃣ 대한법률구조공단 132번 무료 상담
3️⃣ 보이스피싱제로 (voicephisingzero.co.kr) 지원 확인

이 3가지만 기억하세요!""",
            "urgency_level": 8,
            "extracted_info": {},
            "next_priority": "emergency_contact"
        }
    
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
        if any(word in raw_text.lower() for word in ['긴급', '즉시', '빨리', 'msafer', '보이스피싱제로']):
            urgency = 8
        elif any(word in raw_text.lower() for word in ['상담', '132', '확인']):
            urgency = 6
        
        return {
            "response": raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
            "urgency_level": urgency,
            "extracted_info": {},
            "next_priority": "continue"
        }
    
    def _update_session_state(self, response: Dict[str, Any]):
        """세션 상태 업데이트"""
        
        self.session_state['total_turns'] += 1
        self.session_state['urgency_level'] = response.get('urgency_level', 3)
        self.session_state['practical_guidance_provided'] = True
    
    def get_session_status(self) -> Dict[str, Any]:
        """세션 상태 조회"""
        
        return {
            'is_ai_enabled': self.is_enabled,
            'total_turns': self.session_state['total_turns'],
            'urgency_level': self.session_state['urgency_level'],
            'practical_guidance_provided': self.session_state['practical_guidance_provided'],
            'conversation_length': len(self.conversation_history)
        }

# 전역 인스턴스
gemini_assistant = GeminiAssistant()