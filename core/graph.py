import sys
import os
from datetime import datetime
from typing import Literal, Dict, Any, List, Optional
import asyncio
import re

# 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from langgraph.graph import StateGraph, START, END
from core.state import VictimRecoveryState, create_initial_recovery_state

class StructuredVoicePhishingGraph:
    """
    구조화된 보이스피싱 상담 그래프
    - 단계별 정보 수집
    - 강제 순서 진행
    - 명확한 질문-답변 구조
    """
    
    def __init__(self, debug: bool = True):
        self.debug = debug
        self.graph = self._build_structured_graph()
        
        # 구조화된 질문 순서
        self.question_flow = [
            {
                "key": "victim",
                "question": "피해자가 본인일까요? '네' 혹은 '아니요'로 대답해주세요.",
                "type": "yes_no",
                "field": "victim"
            },
            {
                "key": "loss_amount", 
                "question": "송금한 돈이 얼마인가요? 정확한 금액을 말씀해 주세요.",
                "type": "amount",
                "field": "loss_amount"
            },
            {
                "key": "time_context",
                "question": "언제 송금하셨나요? 생각나는 송금시간을 말씀해주세요.",
                "type": "time",
                "field": "time_context"
            },
            {
                "key": "account_frozen",
                "question": "계좌 지급정지 신청을 하셨나요? '네' 혹은 '아니요'로 답해주세요.",
                "type": "yes_no", 
                "field": "account_frozen"
            },
            {
                "key": "reported_to_police",
                "question": "경찰서에 신고하셨나요? '네' 혹은 '아니요'로 답해주세요.",
                "type": "yes_no",
                "field": "reported_to_police"
            }
        ]
        
        if debug:
            print("✅ StructuredVoicePhishingGraph 초기화 완료")
    
    def _build_structured_graph(self) -> StateGraph:
        """구조화된 그래프 구성"""
        
        workflow = StateGraph(VictimRecoveryState)
        
        # 구조화된 노드들
        workflow.add_node("greeting", self._greeting_node)
        workflow.add_node("initial_assessment", self._initial_assessment_node)
        workflow.add_node("collect_info", self._collect_info_node)
        workflow.add_node("emergency_action", self._emergency_action_node)
        workflow.add_node("complete", self._complete_node)
        
        # 단계별 흐름
        workflow.add_edge(START, "greeting")
        
        workflow.add_conditional_edges(
            "greeting",
            self._route_after_greeting,
            {
                "initial_assessment": "initial_assessment",
            }
        )
        
        workflow.add_conditional_edges(
            "initial_assessment", 
            self._route_after_initial,
            {
                "collect_info": "collect_info",
                "complete": "complete"
            }
        )
        
        workflow.add_conditional_edges(
            "collect_info",
            self._route_after_collect,
            {
                "collect_info": "collect_info",  # 다음 질문으로
                "emergency_action": "emergency_action",
                "complete": "complete"
            }
        )
        
        workflow.add_conditional_edges(
            "emergency_action",
            self._route_after_emergency,
            {
                "complete": "complete"
            }
        )
        
        workflow.add_edge("complete", END)
        
        return workflow.compile()
    
    def _greeting_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """인사 및 초기 설명"""
        
        if state.get("greeting_done", False):
            return state
            
        greeting_message = """안녕하세요! 보이스피싱 에프터케어 센터입니다.
신속한 도움을 위해 몇 가지 질문을 드리겠습니다. 힘드시겠지만,, 답변 부탁드립니다."""

        state["messages"].append({
            "role": "assistant",
            "content": greeting_message,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "greeting_complete"
        state["greeting_done"] = True
        state["current_question_index"] = 0  # 질문 인덱스 초기화
        
        if self.debug:
            print("✅ 인사 완료")
        
        return state
    
    def _assess_urgency_smart(self, user_input: str) -> int:
        """스마트한 긴급도 판단"""
        
        user_lower = user_input.lower().strip()
        urgency_score = 0
        
        # 1. 확실한 긴급 패턴 (높은 점수)
        high_urgency_patterns = [
            r'\d+억.*송금',           # "15억 송금했어요"
            r'\d+만원.*보냈',         # "500만원 보냈어요"  
            r'송금.*\d+분.*전',       # "송금한지 30분 전"
            r'사기.*당했',            # "사기 당했어요"
            r'돈.*털렸',             # "돈 털렸어요"
            r'계좌.*이체.*했',        # "계좌로 이체했어요"
            r'\d+.*보냈.*분.*전',     # "500만원 보낸지 30분 전"
        ]
        
        for pattern in high_urgency_patterns:
            if re.search(pattern, user_input):
                urgency_score += 8
                break
        
        # 2. 중간 긴급 패턴
        medium_urgency_patterns = [
            r'보이스.*피싱.*당했',     # "보이스피싱 당했어요"
            r'속았.*같아',            # "속은 것 같아요"
            r'의심.*스러운.*전화',     # "의심스러운 전화"
            r'링크.*클릭.*했',        # "링크 클릭했어요"
            r'앱.*설치.*했',          # "앱 설치했어요"
            r'대출.*변경.',           # "대출 변경을 유도했어요."
        ]
        
        for pattern in medium_urgency_patterns:
            if re.search(pattern, user_input):
                urgency_score += 5
                break
        
        # 3. 단순 키워드 (낮은 점수, 맥락 고려)
        simple_keywords = {
            '급해': 4, '빨리': 4, '도와': 3,
            '송금': 2, '이체': 2, '보냈': 2,
            '사기': 2, '의심': 1, '이상': 1
        }
        
        for word, score in simple_keywords.items():
            if word in user_lower:
                urgency_score += score
        
        # 4. 맥락 기반 점수 조정 (긴급도 감소 요인)
        negative_contexts = [
            '이름', '뭐야', '모르', '아니', '그냥', '궁금', '질문', 
            '문의', '알고싶', '설명', '뜻', '의미'
        ]
        
        for neg_word in negative_contexts:
            if neg_word in user_lower:
                urgency_score = max(0, urgency_score - 3)  # 더 큰 감점
        
        # 5. 시간 관련 긴급성 (최근일수록 긴급)
        time_indicators = [
            (r'방금', 3), (r'\d+분.*전', 3), (r'\d+시간.*전', 2), (r'오늘', 2)
        ]
        
        for time_pattern, score in time_indicators:
            if re.search(time_pattern, user_input):
                urgency_score += score
                break
        
        # 6. 문장 특성 고려
        if len(user_input) <= 5:  # 너무 짧으면 긴급도 감소
            urgency_score = max(0, urgency_score - 2)
        
        if '?' in user_input or '궁금' in user_input:  # 질문 형태면 긴급도 감소
            urgency_score = max(0, urgency_score - 2)
        
        # 7. 최종 점수를 1-10 범위로 조정
        final_urgency = min(max(urgency_score, 1), 10)
        
        return final_urgency
    
    def _initial_assessment_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """개선된 초기 상황 평가"""
        
        last_message = self._get_last_user_message(state)
        
        # 스마트한 긴급도 판단
        urgency_level = self._assess_urgency_smart(last_message)
        
        state["urgency_level"] = urgency_level
        
        # 긴급도에 따른 응답 생성
        if urgency_level >= 8:
            state["is_emergency"] = True
            response = """🚨 긴급 상황으로 판단됩니다! 
            
    즉시 도움이 필요하시군요. 빠른 조치를 위해 몇 가지 정보가 필요합니다."""
            
        elif urgency_level >= 6:
            state["is_emergency"] = False
            response = """상황이 심각해 보입니다. 
            
    자세한 내용을 듣고 적절한 도움을 드리겠습니다."""
            
        elif urgency_level >= 4:
            state["is_emergency"] = False
            response = """말씀하신 내용을 보니 걱정되는 상황이시네요.
            
    어떤 일이 있었는지 차근차근 말씀해 주시겠어요?"""
            
        else:
            state["is_emergency"] = False
            response = """보이스피싱 상담센터입니다.
            
    어떤 상황인지 자세히 말씀해 주시면 도움을 드리겠습니다."""
        
        state["messages"].append({
            "role": "assistant", 
            "content": response,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "assessment_complete"
        
        if self.debug:
            print(f"✅ 스마트 평가 완료 - 긴급도: {urgency_level} (입력: '{last_message}')")
        
        return state
    
    def _collect_info_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """구조화된 정보 수집"""
        
        current_index = state.get("current_question_index", 0)
        
        # 이전 답변 처리 (첫 번째 질문이 아닌 경우)
        if current_index > 0:
            last_user_message = self._get_last_user_message(state)
            prev_question = self.question_flow[current_index - 1]
            
            # 답변 파싱 및 저장
            parsed_answer = self._parse_answer(last_user_message, prev_question["type"])
            state[prev_question["field"]] = parsed_answer
            
            # 확인 메시지
            confirmation = self._generate_confirmation(prev_question["field"], parsed_answer)
            
            if self.debug:
                print(f"✅ 수집: {prev_question['field']} = {parsed_answer}")
        
        # 다음 질문 확인
        if current_index < len(self.question_flow):
            current_question = self.question_flow[current_index]
            
            # 질문 생성
            if current_index > 0:
                # 확인 + 다음 질문
                response = f"{confirmation}\n\n{current_question['question']}"
            else:
                # 첫 번째 질문
                response = current_question['question']
            
            state["current_question_index"] = current_index + 1
            
        else:
            # 모든 질문 완료
            response = "정보 수집이 완료되었습니다. 상황을 분석하겠습니다."
            state["info_collection_complete"] = True
        
        state["messages"].append({
            "role": "assistant",
            "content": response, 
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "collecting_info"
        
        return state
    
    def _generate_smart_confirmation(self, field: str, extraction_result: dict) -> str:
        """스마트 확인 메시지 생성"""
        
        field_names = {
            "victim": "피해자",
            "loss_amount": "송금 금액", 
            "time_context": "송금 시기",
            "account_frozen": "계좌 지급정지",
            "reported_to_police": "경찰 신고"
        }
        
        field_name = field_names.get(field, field)
        
        if field == "loss_amount":
            value = extraction_result.get('formatted', extraction_result.get('raw_text'))
        else:
            value = extraction_result.get('answer', extraction_result.get('normalized', extraction_result.get('raw_text')))
        
        return f"✅ {field_name}: {value}"
    
    def _emergency_action_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """긴급 조치 안내"""
        
        # 수집된 정보 기반 긴급 조치
        victim = state.get("victim", "unknown")
        loss_amount = state.get("loss_amount", 0)
        account_frozen = state.get("account_frozen", False)
        reported_to_police = state.get("reported_to_police", False)
        
        emergency_actions = []
        
        # 지급정지 신청
        if not account_frozen and loss_amount > 0:
            emergency_actions.append("즉시 일일이(경찰, 112) 또는 일삼삼이(금감원, 1332)에 신고하세요.")
        
        # 경찰 신고
        if not reported_to_police:
            emergency_actions.append("가까운 경찰서에 보이스피싱 피해 신고를 하세요.")
        
        # 추가 피해 방지
        emergency_actions.append("의심스러운 전화는 즉시 차단하세요.")
        emergency_actions.append("모든 금융 앱의 비밀번호를 변경하세요.")
        
        if emergency_actions:
            response = "🚨 긴급 조치 사항:\n\n" + "\n\n".join(emergency_actions)
        else:
            response = "필요한 조치를 모두 완료하셨습니다. 추가 피해가 없도록 주의하세요."
        
        state["messages"].append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "emergency_complete"
        
        if self.debug:
            print("✅ 긴급 조치 안내 완료")
        
        return state
    
    def _complete_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """상담 완료"""
        
        # 수집된 정보 요약
        summary = self._generate_summary(state)
        
        completion_message = f"""상담이 완료되었습니다.

📋 수집된 정보 요약:
{summary}

⚠️ 중요: 삼(3)일 이내 경찰서에서 사건사고사실확인원을 발급받아 은행에 제출해야 환급 가능합니다.

앞으로도 의심스러운 연락에 주의하시고, 문제가 발생하면 즉시 일일이(112) 또는 일삼삼이(1332) 연락하세요."""

        state["messages"].append({
            "role": "assistant",
            "content": completion_message,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "consultation_complete"
        
        if self.debug:
            print("✅ 상담 완료")
        
        return state
    
    # ========================================================================
    # 라우팅 함수들
    # ========================================================================
    
    def _route_after_greeting(self, state: VictimRecoveryState) -> Literal["initial_assessment"]:
        """인사 후 라우팅 - 무조건 평가로"""
        return "initial_assessment"

    def _route_after_initial(self, state: VictimRecoveryState) -> Literal["collect_info"]:
        """초기 평가 후 라우팅 - 무조건 정보수집으로"""
        return "collect_info"

    def _route_after_collect(self, state: VictimRecoveryState) -> Literal["emergency_action", "complete"]:
        """정보 수집 후 라우팅 - 완료 조건 명확화"""
        
        # 정보 수집 완료 체크
        current_index = state.get("current_question_index", 0)
        
        if current_index >= len(self.question_flow):
            # 모든 질문 완료
            state["info_collection_complete"] = True
            
            if state.get("is_emergency", False):
                return "emergency_action"
            else:
                return "complete"
        else:
            # 아직 질문이 남아있으면 다시 collect_info로 가지 말고 complete로
            return "complete"
        
    def _route_after_emergency(self, state: VictimRecoveryState) -> Literal["complete"]:
        """긴급 조치 후 라우팅"""
        return "complete"
    
    # ========================================================================
    # 유틸리티 함수들
    # ========================================================================
    
    def _parse_answer(self, answer: str, answer_type: str) -> Any:
        """답변 파싱"""
        
        answer = answer.strip().lower()
        
        if answer_type == "yes_no":
            if any(word in answer for word in ["네", "예", "맞아", "맛", "맛아", "맞", "웅", "엉", "yes", "응"]):
                return "네"
            elif any(word in answer for word in ["아니", "no", "아님", "땡", "아닌"]):
                return "아니요"
            else:
                return "미확인"
        
        elif answer_type == "amount":
            # 숫자 추출
            import re
            numbers = re.findall(r'[\d,]+', answer)
            if numbers:
                try:
                    # 쉼표 제거하고 숫자로 변환
                    amount = int(numbers[0].replace(',', ''))
                    
                    # 단위 추정 (더 스마트하게)
                    if '억' in answer:
                        amount = amount * 100000000
                    elif '천만' in answer:
                        amount = amount * 10000000
                    elif '백만' in answer:
                        amount = amount * 1000000
                    elif '만' in answer:
                        amount = amount * 10000
                    
                    return f"{amount:,}원"
                except:
                    pass
            return answer.strip()
        
        elif answer_type == "time":
            # 시간 표현 정규화
            time_mappings = {
                "오늘": "오늘",
                "어제": "어제", 
                "그제": "그제",
                "일주일": "일주일 전",
                "한달": "한 달 전"
            }
            
            for key, value in time_mappings.items():
                if key in answer:
                    return value
            
            # 불완전한 표현 정리 ("25분 전에 다" → "25분 전")
            if '분' in answer and '전' in answer:
                import re
                cleaned = re.sub(r'에?\s*다$', '', answer).strip()
                return cleaned
            
            return answer.strip()
        
        else:
            return answer.strip()
    
    def _generate_confirmation(self, field: str, value: Any) -> str:
        """확인 메시지 생성"""
        
        field_names = {
            "victim": "피해자",
            "loss_amount": "송금 금액", 
            "time_context": "송금 시기",
            "account_frozen": "계좌 지급정지",
            "reported_to_police": "경찰 신고"
        }
        
        field_name = field_names.get(field, field)
        return f"✅ {field_name}: {value}"
    
    def _generate_summary(self, state: VictimRecoveryState) -> str:
        """정보 요약 생성"""
        
        summary_parts = []
        
        victim = state.get("victim", "미확인")
        if victim != "미확인":
            summary_parts.append(f"• 피해자: {victim}")
        
        loss_amount = state.get("loss_amount", "미확인")
        if loss_amount != "미확인":
            summary_parts.append(f"• 손실 금액: {loss_amount}")
        
        time_context = state.get("time_context", "미확인")
        if time_context != "미확인":
            summary_parts.append(f"• 발생 시기: {time_context}")
        
        account_frozen = state.get("account_frozen", "미확인")
        if account_frozen != "미확인":
            summary_parts.append(f"• 지급정지 신청: {account_frozen}")
        
        reported_to_police = state.get("reported_to_police", "미확인")
        if reported_to_police != "미확인":
            summary_parts.append(f"• 경찰 신고: {reported_to_police}")
        
        return "\n".join(summary_parts) if summary_parts else "• 정보 수집 미완료"
    
    def _get_last_user_message(self, state: VictimRecoveryState) -> str:
        """마지막 사용자 메시지 추출"""
        
        messages = state.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "").strip()
        return ""
    
    # ========================================================================
    # 메인 인터페이스
    # ========================================================================
    
    async def start_conversation(self, session_id: str = None) -> VictimRecoveryState:
        """구조화된 상담 시작"""
        
        if not session_id:
            session_id = f"struct_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        initial_state = create_initial_recovery_state(session_id)
        
        try:
            config = {"recursion_limit": 20} # 무한루프에 빠지지 않도록
            result = await self.graph.ainvoke(initial_state, config)
        

            if self.debug:
                print(f"✅ 구조화된 상담 시작: {result.get('current_step', 'unknown')}")
            
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
        """Gemini 통합 대화 처리"""
        
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
            # 🔥 핵심: Gemini 사용 여부 확인
            use_gemini = self._check_gemini_available()
            
            if use_gemini:
                # Gemini AI 처리
                ai_response = await self._process_with_gemini(user_input, state)
            else:
                # 기존 구조화된 처리 (폴백)
                ai_response = await self._process_structured_fallback(user_input, state)
            
            # AI 응답 추가
            state["messages"].append({
                "role": "assistant",
                "content": ai_response.get('response', '처리 중 오류가 발생했습니다.'),
                "timestamp": datetime.now(),
                "ai_metadata": {
                    "mode": "gemini" if use_gemini else "structured",
                    "urgency_level": ai_response.get('urgency_level', 3),
                    "extracted_info": ai_response.get('extracted_info', {})
                }
            })
            
            # 상태 업데이트
            state["urgency_level"] = ai_response.get('urgency_level', state.get('urgency_level', 3))
            
            if self.debug:
                mode = "Gemini" if use_gemini else "구조화"
                print(f"✅ {mode} 처리: 턴 {state['conversation_turns']}")
            
            return state
            
        except Exception as e:
            if self.debug:
                print(f"❌ 대화 처리 실패: {e}")
            
            state["messages"].append({
                "role": "assistant",
                "content": "처리 중 문제가 발생했습니다. 긴급한 경우 112로 연락하세요.",
                "timestamp": datetime.now()
            })
            return state
    
    def _check_gemini_available(self) -> bool:
        """Gemini 사용 가능 여부 확인"""
        
        try:
            # Gemini 어시스턴트 import 시도
            from services.gemini_assistant import gemini_assistant
            return gemini_assistant.is_enabled
        except ImportError:
            if self.debug:
                print("⚠️ Gemini 어시스턴트 없음 - 구조화된 모드 사용")
            return False
        except Exception as e:
            if self.debug:
                print(f"⚠️ Gemini 확인 오류: {e}")
            return False

    async def _process_with_gemini(self, user_input: str, state: VictimRecoveryState) -> Dict[str, Any]:
        """Gemini AI 처리"""
        
        try:
            from services.gemini_assistant import gemini_assistant
            
            # 현재 상태를 컨텍스트로 구성
            context = {
                'conversation_turns': state.get('conversation_turns', 0),
                'current_urgency': state.get('urgency_level', 3),
                'collected_info': {
                    'amount': state.get('loss_amount'),
                    'time': state.get('time_context'),
                    'victim_status': state.get('victim'),
                    'actions_taken': state.get('actions_taken', [])
                },
                'current_step': state.get('current_step', 'unknown')
            }
            
            # Gemini에 요청
            response = await gemini_assistant.analyze_and_respond(user_input, context)
            
            # 추출된 정보 상태에 반영
            extracted = response.get('extracted_info', {})
            if extracted.get('amount'):
                state['loss_amount'] = extracted['amount']
            if extracted.get('time'):
                state['time_context'] = extracted['time']
            if extracted.get('actions_taken'):
                state['actions_taken'] = extracted['actions_taken']
            
            return response
            
        except Exception as e:
            if self.debug:
                print(f"❌ Gemini 처리 실패: {e}")
            
            # 구조화된 방식으로 폴백
            return await self._process_structured_fallback(user_input, state)

    async def _process_structured_fallback(self, user_input: str, state: VictimRecoveryState) -> Dict[str, Any]:
        """기존 구조화된 처리 (폴백)"""
        
        # 기존 로직 사용
        current_step = state.get("current_step", "greeting_complete")
        
        if current_step == "greeting_complete":
            # 초기 평가 + 첫 질문
            state = self._initial_assessment_node(state)
            state = self._collect_info_node(state)
            
            # 마지막 AI 메시지 추출
            last_ai_message = ""
            for msg in reversed(state.get("messages", [])):
                if msg.get("role") == "assistant":
                    last_ai_message = msg.get("content", "")
                    break
            
            return {
                'response': last_ai_message or "다시 말씀해 주세요.",
                'urgency_level': state.get('urgency_level', 3),
                'extracted_info': {},
                'mode': 'structured_fallback'
            }
            
        elif current_step == "collecting_info":
            # 정보 수집 계속
            if not state.get("info_collection_complete", False):
                state = self._collect_info_node(state)
            else:
                # 수집 완료 처리
                if state.get("is_emergency", False):
                    state = self._emergency_action_node(state)
                else:
                    state = self._complete_node(state)
            
            # 마지막 AI 메시지 추출
            last_ai_message = ""
            for msg in reversed(state.get("messages", [])):
                if msg.get("role") == "assistant":
                    last_ai_message = msg.get("content", "")
                    break
            
            return {
                'response': last_ai_message or "계속 진행하겠습니다.",
                'urgency_level': state.get('urgency_level', 3),
                'extracted_info': {},
                'mode': 'structured_fallback'
            }
        
        else:
            # 기본 응답
            return {
                'response': "상황을 파악했습니다. 더 자세히 말씀해 주시겠어요?",
                'urgency_level': state.get('urgency_level', 3),
                'extracted_info': {},
                'mode': 'structured_fallback'
            }
    def get_collected_info(self, state: VictimRecoveryState) -> Dict[str, Any]:
        """수집된 정보 조회"""
        
        return {
            "victim": state.get("victim", "미확인"),
            "loss_amount": state.get("loss_amount", "미확인"),
            "time_context": state.get("time_context", "미확인"), 
            "account_frozen": state.get("account_frozen", "미확인"),
            "reported_to_police": state.get("reported_to_police", "미확인"),
            "urgency_level": state.get("urgency_level", 3),
            "current_question_index": state.get("current_question_index", 0),
            "collection_complete": state.get("info_collection_complete", False)
        }

# 하위 호환성을 위한 별칭
OptimizedVoicePhishingGraph = StructuredVoicePhishingGraph