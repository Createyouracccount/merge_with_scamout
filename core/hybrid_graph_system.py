# core/hybrid_graph_system.py 수정 (기존 파일에 Gemini 통합)

import sys
import os
from datetime import datetime
from typing import Literal, Dict, Any, List, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

# Gemini 통합
try:
    from services.gemini_assistant import gemini_assistant
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("Gemini 어시스턴트를 가져올 수 없음")

# 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from langgraph.graph import StateGraph, START, END
from core.state import VictimRecoveryState, create_initial_recovery_state
from config.settings import settings

class HybridVoicePhishingGraph:
    """
    Gemini 통합 하이브리드 보이스피싱 상담 그래프
    - Gemini AI + 규칙 기반 폴백
    - 실제 대처방법 기반
    - 유연한 대화 흐름
    """
    
    def __init__(self, debug: bool = True):
        self.debug = debug
        
        # Gemini 통합
        self.use_ai = (GEMINI_AVAILABLE and 
                      settings.USE_AI_ASSISTANT and 
                      gemini_assistant.is_enabled if GEMINI_AVAILABLE else False)
        
        if self.use_ai:
            self.ai_assistant = gemini_assistant
            if debug:
                print("✅ Gemini AI 모드 활성화")
        else:
            self.ai_assistant = None
            if debug:
                print("✅ 규칙 기반 모드 활성화")
        
        self.graph = self._build_hybrid_graph()
        
        # 실제 대처방법 가이드라인 (금융감독원 기준)
        self.emergency_guidelines = {
            'immediate_actions': [
                "즉시 112(경찰) 또는 1332(금감원)에 신고하세요",
                "송금한 은행 고객센터에 지급정지 신청하세요", 
                "휴대폰을 비행기모드로 전환하거나 전원을 끄세요"
            ],
            'three_day_rule': "3일 이내 경찰서에서 사건사고사실확인원을 발급받아 은행에 제출해야 환급 가능합니다",
            'info_security': [
                "개인정보 노출사실을 pd.fss.or.kr에 등록하세요",
                "계좌개설 여부를 www.payinfo.or.kr에서 확인하세요",
                "휴대폰 명의도용을 www.msafer.or.kr에서 확인하세요"
            ]
        }
        
        if debug:
            print("✅ HybridVoicePhishingGraph 초기화 완료")
    
    def _build_hybrid_graph(self) -> StateGraph:
        """하이브리드 그래프 구성"""
        
        workflow = StateGraph(VictimRecoveryState)
        
        # 간소화된 노드 구조
        workflow.add_node("greeting", self._greeting_node)
        workflow.add_node("ai_processing", self._ai_processing_node)
        workflow.add_node("emergency_response", self._emergency_response_node)
        workflow.add_node("completion", self._completion_node)
        
        # 단순한 흐름
        workflow.add_edge(START, "greeting")
        
        workflow.add_conditional_edges(
            "greeting",
            self._route_after_greeting,
            {
                "ai_processing": "ai_processing",
            }
        )
        
        workflow.add_conditional_edges(
            "ai_processing", 
            self._route_after_ai,
            {
                "emergency_response": "emergency_response",
                "ai_processing": "ai_processing",
                "completion": "completion"
            }
        )
        
        workflow.add_conditional_edges(
            "emergency_response",
            self._route_after_emergency,
            {
                "ai_processing": "ai_processing",
                "completion": "completion"
            }
        )
        
        workflow.add_edge("completion", END)
        
        return workflow.compile()
    
    def _greeting_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """인사 노드"""
        
        if state.get("greeting_done", False):
            return state
            
        greeting_message = """안녕하세요, 보이스피싱 상담센터입니다.
지금 어떤 상황이신지 편하게 말씀해 주세요. 도와드리겠습니다."""

        state["messages"].append({
            "role": "assistant",
            "content": greeting_message,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "greeting_complete"
        state["greeting_done"] = True
        
        if self.debug:
            print("✅ 인사 완료")
        
        return state
    
    def _ai_processing_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """AI 처리 노드 (핵심)"""
        
        last_message = self._get_last_user_message(state)
        
        if self.use_ai:
            # Gemini AI 처리
            ai_response = asyncio.create_task(self._process_with_gemini(last_message, state))
            # 동기적으로 실행하기 위해 임시 이벤트 루프 사용
            try:
                loop = asyncio.get_event_loop()
                response_data = loop.run_until_complete(ai_response)
            except RuntimeError:
                # 이미 실행 중인 루프가 있는 경우
                response_data = self._process_with_rules_fallback(last_message)
        else:
            # 규칙 기반 처리
            response_data = self._process_with_rules_fallback(last_message)
        
        # 응답 추가
        state["messages"].append({
            "role": "assistant",
            "content": response_data.get('response', '죄송합니다. 다시 말씀해 주세요.'),
            "timestamp": datetime.now(),
            "ai_metadata": response_data
        })
        
        # 상태 업데이트
        state["urgency_level"] = response_data.get('urgency_level', 3)
        state["current_step"] = "ai_processed"
        state["conversation_turns"] = state.get("conversation_turns", 0) + 1
        
        # 추출된 정보 저장
        extracted = response_data.get('extracted_info', {})
        if extracted.get('amount'):
            state['loss_amount'] = extracted['amount']
        if extracted.get('time'):
            state['time_context'] = extracted['time']
        if extracted.get('actions_taken'):
            state['actions_taken'] = extracted['actions_taken']
        
        if self.debug:
            mode = "AI" if self.use_ai else "규칙"
            print(f"✅ {mode} 처리: 긴급도 {response_data.get('urgency_level')}, 턴 {state['conversation_turns']}")
        
        return state
    
    async def _process_with_gemini(self, user_input: str, state: VictimRecoveryState) -> Dict[str, Any]:
        """Gemini AI 처리"""
        
        try:
            # 현재 상태를 컨텍스트로 구성
            context = {
                'conversation_turns': state.get('conversation_turns', 0),
                'current_urgency': state.get('urgency_level', 3),
                'collected_info': {
                    'amount': state.get('loss_amount'),
                    'time': state.get('time_context'),
                    'victim_status': state.get('victim'),
                    'actions_taken': state.get('actions_taken', [])
                }
            }
            
            # Gemini에 요청
            response = await self.ai_assistant.analyze_and_respond(user_input, context)
            
            # 추가 안전장치
            if response.get('urgency_level', 0) >= 8:
                response = self._add_emergency_safety_net(response)
            
            return response
            
        except Exception as e:
            logger.error(f"Gemini 처리 실패: {e}")
            return self._process_with_rules_fallback(user_input)
    
    def _process_with_rules_fallback(self, user_input: str) -> Dict[str, Any]:
        """규칙 기반 폴백 처리"""
        
        user_lower = user_input.lower()
        
        # 긴급도 계산
        urgency = 3
        
        # 긴급 키워드
        high_urgency_words = ['돈', '송금', '보냈', '이체', '급해', '빨리', '도와', '사기', '속았']
        medium_urgency_words = ['앱', '설치', '링크', '의심', '이상']
        
        for word in high_urgency_words:
            if word in user_lower:
                urgency += 3
        
        for word in medium_urgency_words:
            if word in user_lower:
                urgency += 1
        
        # 금액 관련
        if any(word in user_lower for word in ['억', '천만', '백만']):
            urgency += 4
        elif any(word in user_lower for word in ['만원', '원']):
            urgency += 2
        
        # 시간 관련
        if any(word in user_lower for word in ['분 전', '시간 전', '방금']):
            urgency += 3
        
        urgency = min(urgency, 10)
        
        # 응답 생성
        if urgency >= 9:
            response = self._generate_critical_emergency_response()
        elif urgency >= 7:
            response = self._generate_emergency_response()
        elif urgency >= 5:
            response = self._generate_concern_response()
        else:
            response = self._generate_standard_response()
        
        # 정보 추출 (간단)
        extracted_info = {}
        
        if any(word in user_lower for word in ['억', '만원', '원']):
            extracted_info['amount'] = "금액 언급됨"
        
        if any(word in user_lower for word in ['분', '시간', '전', '오늘', '어제']):
            extracted_info['time'] = "시간 정보 있음"
        
        if any(word in user_lower for word in ['신고', '경찰', '은행']):
            extracted_info['actions_taken'] = "일부 조치 취함"
        
        return {
            'response': response,
            'urgency_level': urgency,
            'extracted_info': extracted_info,
            'next_priority': 'emergency_action' if urgency >= 8 else 'continue',
            'processing_mode': 'rule_based'
        }
    
    def _generate_critical_emergency_response(self) -> str:
        """치명적 긴급 상황 응답"""
        
        return """🚨 매우 긴급한 상황으로 보입니다!

**지금 즉시 해야 할 것:**
1️⃣ 112(경찰) 또는 1332(금감원)에 신고
2️⃣ 송금한 은행 고객센터에 지급정지 신청  
3️⃣ 휴대폰 비행기모드 전환

⚠️ **중요**: 3일 이내 경찰서에서 사건사고사실확인원 발급받아 은행 제출 필수!

어떤 조치부터 하고 계신가요?"""
    
    def _generate_emergency_response(self) -> str:
        """긴급 상황 응답"""
        
        return """상황이 심각해 보입니다. 빠르게 도와드리겠습니다.

🚨 **즉시 조치사항:**
• 112(경찰) 또는 1332(금감원) 신고
• 송금한 은행에 지급정지 신청
• 휴대폰 보안 설정

지금까지 어떤 조치를 취하셨나요?"""
    
    def _generate_concern_response(self) -> str:
        """우려 상황 응답"""
        
        return """걱정되는 상황이시군요. 자세한 내용을 듣고 도움을 드리겠습니다.

어떤 일이 있었는지 차근차근 말씀해 주시겠어요?
- 언제 일어난 일인가요?
- 어떤 피해가 있었나요?
- 지금까지 취한 조치가 있나요?"""
    
    def _generate_standard_response(self) -> str:
        """일반 응답"""
        
        return """보이스피싱 상담센터입니다. 

어떤 상황인지 말씀해 주시면 적절한 도움을 드리겠습니다. 
혹시 의심스러운 연락을 받으셨거나 피해가 있으셨나요?"""
    
    def _add_emergency_safety_net(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """긴급 상황 안전망 추가"""
        
        original_response = response.get('response', '')
        
        # 필수 연락처가 없으면 추가
        if '112' not in original_response and '1332' not in original_response:
            response['response'] = f"{original_response}\n\n🚨 긴급연락처: 112(경찰), 1332(금감원)"
        
        # 3일 규칙이 없으면 추가
        if '3일' not in original_response:
            response['response'] += f"\n\n⚠️ {self.emergency_guidelines['three_day_rule']}"
        
        return response
    
    def _emergency_response_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """긴급 대응 노드"""
        
        urgency = state.get("urgency_level", 3)
        
        if urgency >= 8:
            emergency_guide = self._generate_detailed_emergency_guide(state)
            
            state["messages"].append({
                "role": "assistant",
                "content": emergency_guide,
                "timestamp": datetime.now(),
                "type": "emergency_guidance"
            })
            
            state["emergency_guidance_provided"] = True
        
        state["current_step"] = "emergency_handled"
        
        if self.debug:
            print(f"✅ 긴급 대응 완료: 긴급도 {urgency}")
        
        return state
    
    def _generate_detailed_emergency_guide(self, state: VictimRecoveryState) -> str:
        """상세한 긴급 가이드 생성"""
        
        guide_parts = [
            "📋 **긴급 조치사항 체크리스트**",
            "",
            "**즉시 (지금 당장):**"
        ]
        
        for i, action in enumerate(self.emergency_guidelines['immediate_actions'], 1):
            guide_parts.append(f"{i}. {action}")
        
        guide_parts.extend([
            "",
            "**3일 이내 (환급을 위해 필수):**",
            f"• {self.emergency_guidelines['three_day_rule']}",
            "",
            "**추가 보안 조치:**"
        ])
        
        for action in self.emergency_guidelines['info_security']:
            guide_parts.append(f"• {action}")
        
        guide_parts.extend([
            "",
            "현재 어느 단계까지 완료하셨는지 알려주세요."
        ])
        
        return "\n".join(guide_parts)
    
    def _completion_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """완료 노드"""
        
        summary = self._generate_consultation_summary(state)
        
        state["messages"].append({
            "role": "assistant",
            "content": summary,
            "timestamp": datetime.now(),
            "type": "consultation_summary"
        })
        
        state["current_step"] = "consultation_complete"
        state["consultation_complete"] = True
        
        if self.debug:
            print("✅ 상담 완료")
        
        return state
    
    def _generate_consultation_summary(self, state: VictimRecoveryState) -> str:
        """상담 요약 생성"""
        
        urgency = state.get("urgency_level", 3)
        
        summary_parts = [
            "📋 **상담 완료**",
            "",
            "오늘 상담해드린 내용을 정리해드렸습니다."
        ]
        
        if urgency >= 8:
            summary_parts.extend([
                "",
                "⚠️ **반드시 기억하세요:**",
                "• 3일 이내 경찰서 방문 (사건사고사실확인원 발급)",
                "• 확인원을 은행에 제출 (환급 신청)",
                "• 추가 피해 방지를 위한 보안 조치"
            ])
        
        summary_parts.extend([
            "",
            "앞으로도 의심스러운 연락에 주의하시고,",
            "문제가 발생하면 112, 1332로 즉시 연락하세요.",
            "",
            "안전하세요! 🙏"
        ])
        
        return "\n".join(summary_parts)
    
    # ========================================================================
    # 라우팅 함수들
    # ========================================================================
    
    def _route_after_greeting(self, state: VictimRecoveryState) -> Literal["ai_processing"]:
        """인사 후 라우팅"""
        messages = state.get("messages", [])
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        
        if len(user_messages) > 0:
            return "ai_processing"
        else:
            return "ai_processing"  # 기본적으로 AI 처리로
    
    def _route_after_ai(self, state: VictimRecoveryState) -> Literal["emergency_response", "ai_processing", "completion"]:
        """AI 처리 후 라우팅"""
        
        urgency = state.get("urgency_level", 3)
        turns = state.get("conversation_turns", 0)
        
        # 긴급 상황이고 아직 가이드 제공 안 함
        if urgency >= 8 and not state.get("emergency_guidance_provided"):
            return "emergency_response"
        
        # 대화 종료 조건
        if turns >= 15 or state.get("user_satisfied"):
            return "completion"
        
        # 계속 대화
        return "ai_processing"
    
    def _route_after_emergency(self, state: VictimRecoveryState) -> Literal["ai_processing", "completion"]:
        """긴급 처리 후 라우팅"""
        turns = state.get("conversation_turns", 0)
        
        if turns >= 20:
            return "completion"
        else:
            return "ai_processing"
    
    # ========================================================================
    # 유틸리티 함수들
    # ========================================================================
    
    def _get_last_user_message(self, state: VictimRecoveryState) -> str:
        """마지막 사용자 메시지 추출"""
        
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "").strip()
        return ""
    
    # ========================================================================
    # 메인 인터페이스 (기존과 동일)
    # ========================================================================
    
    async def start_conversation(self, session_id: str = None) -> VictimRecoveryState:
        """하이브리드 상담 시작"""
        
        if not session_id:
            session_id = f"hybrid_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        initial_state = create_initial_recovery_state(session_id)
        
        try:
            config = {"recursion_limit": 5}
            result = await self.graph.ainvoke(initial_state, config)
            
            if self.debug:
                print(f"✅ 하이브리드 상담 시작: {result.get('current_step', 'unknown')}")
            
            return result
            
        except Exception as e:
            if self.debug:
                print(f"❌ 상담 시작 실패: {e}")
            
            # 실패 시 기본 상태 반환
            initial_state["current_step"] = "greeting_complete"
            initial_state["messages"].append({
                "role": "assistant",
                "content": "안녕하세요! 보이스피싱 상담센터입니다. 어떤 일이 있었는지 말씀해 주세요.",
                "timestamp": datetime.now()
            })
            return initial_state
    
    async def continue_conversation(self, state: VictimRecoveryState, user_input: str) -> VictimRecoveryState:
        """하이브리드 대화 계속하기"""
        
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
            # 하이브리드 그래프로 처리
            config = {"recursion_limit": 5}
            updated_state = await self.graph.ainvoke(state, config)
            
            if self.debug:
                print(f"✅ 하이브리드 처리: 턴 {updated_state['conversation_turns']}")
            
            return updated_state
            
        except Exception as e:
            if self.debug:
                print(f"❌ 하이브리드 처리 실패: {e}")
            
            # 폴백 응답
            fallback_response = self._generate_fallback_response(user_input, state)
            state["messages"].append({
                "role": "assistant", 
                "content": fallback_response,
                "timestamp": datetime.now()
            })
            return state
    
    def _generate_fallback_response(self, user_input: str, state: VictimRecoveryState) -> str:
        """폴백 응답 생성"""
        
        # 긴급 키워드가 있으면 즉시 조치 안내
        urgent_keywords = ['돈', '송금', '사기', '급해', '도와']
        if any(keyword in user_input for keyword in urgent_keywords):
            return """긴급한 상황으로 보입니다. 
            
🚨 즉시 연락처:
• 경찰: 112
• 금융감독원: 1332
• 송금한 은행 고객센터

지급정지 신청을 최우선으로 하세요."""
        
        # 일반적인 폴백
        return "시스템에 일시적인 문제가 있습니다. 긴급한 경우 112나 1332로 직접 연락하세요. 다시 말씀해 주시겠어요?"


# 하위 호환성을 위한 별칭
StructuredVoicePhishingGraph = HybridVoicePhishingGraph
OptimizedVoicePhishingGraph = HybridVoicePhishingGraph