import sys
import os
from datetime import datetime
from typing import Literal, Dict, Any, List, Optional
import asyncio

# 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from langgraph.graph import StateGraph, START, END

from core.state import VictimRecoveryState, create_initial_recovery_state
from services.enhanced_info_extractor import EnhancedInfoExtractor
from core.improved_graph_nodes import ImprovedInfoCollectionNode

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
        self.info_extractor = EnhancedInfoExtractor()
        self.info_collector = ImprovedInfoCollectionNode(self.info_extractor)
        
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
    
    def _initial_assessment_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """초기 상황 평가"""
        
        last_message = self._get_last_user_message(state)
        
        # 긴급 키워드 체크
        emergency_keywords = ["돈", "송금", "보냈", "이체", "계좌", "사기"]
        is_emergency = any(keyword in last_message.lower() for keyword in emergency_keywords)
        
        if is_emergency:
            state["is_emergency"] = True
            state["urgency_level"] = 8
            
            response = """긴급 상황으로 판단됩니다. 빠른 조치를 위해 몇 가지 정보가 필요합니다."""
        else:
            state["is_emergency"] = False
            state["urgency_level"] = 3
            
            response = """상황을 파악했습니다. 정확한 도움을 위해 몇 가지 질문을 드리겠습니다."""
        
        state["messages"].append({
            "role": "assistant", 
            "content": response,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "assessment_complete"
        
        if self.debug:
            print(f"✅ 초기 평가 완료 - 긴급도: {state['urgency_level']}")
        
        return state
    
    def _collect_info_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """강화된 정보 수집 노드"""
        
        # 강화된 정보 추출기 사용
        if not hasattr(self, 'info_extractor'):
            from services.enhanced_info_extractor import EnhancedInfoExtractor
            self.info_extractor = EnhancedInfoExtractor()
            
            # question_types 매핑도 추가
            self.question_types = {
                "victim": "yes_no",
                "loss_amount": "amount", 
                "time_context": "time",
                "account_frozen": "yes_no",
                "reported_to_police": "yes_no"
            }
        
        current_index = state.get("current_question_index", 0)
        
        # 이전 답변 처리 (첫 번째 질문이 아닌 경우)
        if current_index > 0:
            last_user_message = self._get_last_user_message(state)
            prev_question = self.question_flow[current_index - 1]
            
            # 🔧 강화된 정보 추출 사용
            question_type = self.question_types.get(prev_question["field"], "text")
            extraction_result = self.info_extractor.extract_all_info(last_user_message, question_type)
            
            # 신뢰도 기반 처리
            if extraction_result.get('confidence', 0) >= 0.7:
                # 높은 신뢰도 - 바로 저장
                if prev_question["field"] == "loss_amount":
                    state[prev_question["field"]] = extraction_result.get('formatted')
                    # 긴급도 업데이트
                    amount = extraction_result.get('amount')
                    if amount and amount > 50000000:  # 5천만원 이상
                        state['urgency_level'] = 9
                        state['is_emergency'] = True
                else:
                    state[prev_question["field"]] = extraction_result.get('answer', extraction_result.get('normalized'))
                
                confirmation = self._generate_smart_confirmation(prev_question["field"], extraction_result)
            else:
                # 낮은 신뢰도 - 재확인 필요
                state[prev_question["field"]] = f"{extraction_result.get('raw_text')} (재확인 필요)"
                confirmation = f"다시 한 번 확인해주세요: {prev_question['question']}"
            
            if self.debug:
                print(f"✅ 수집: {prev_question['field']} = {state[prev_question['field']]}")
        
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
            emergency_actions.append("즉시 일일이에 전화하여 '보이스피싱 지급정지 신청'을 요청하세요.")
        
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
앞으로도 의심스러운 연락에 주의하시고, 문제가 발생하면 즉시 1566-1188로 연락하세요."""

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
    
    def _route_after_greeting(self, state: VictimRecoveryState) -> Literal["initial_assessment", "complete"]:
        """인사 후 라우팅"""
        # 변경: 사용자 입력이 있으면 평가로, 없으면 대기
        messages = state.get("messages", [])
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        
        if len(user_messages) > 0:
            return "initial_assessment"  # 사용자 입력이 있으면 평가 시작
        else:
            return "complete"  # 아직 입력 없으면 대기
    
    def _route_after_initial(self, state: VictimRecoveryState) -> Literal["collect_info", "complete"]:
        """초기 평가 후 라우팅"""
        return "collect_info"
    
    def _route_after_collect(self, state: VictimRecoveryState) -> Literal["collect_info", "emergency_action", "complete"]:
        """정보 수집 후 라우팅"""
        
        if state.get("info_collection_complete", False):
            # 긴급 상황이면 긴급 조치로
            if state.get("is_emergency", False):
                return "emergency_action"
            else:
                return "complete"
        else:
            # 다음 질문으로
            return "collect_info"
    
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
            config = {"recursion_limit": 3}
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
            # 현재 상태에 따라 다음 노드 결정
            current_step = state.get("current_step", "greeting_complete")
            
            if current_step == "greeting_complete":
                # 초기 평가로
                state = self._initial_assessment_node(state)
                state = self._collect_info_node(state)  # 첫 번째 질문 시작
                
            elif current_step == "collecting_info":
                # 정보 수집 계속
                if not state.get("info_collection_complete", False):
                    state = self._collect_info_node(state)
                else:
                    # 수집 완료, 긴급 조치 또는 완료로
                    if state.get("is_emergency", False):
                        state = self._emergency_action_node(state)
                    else:
                        state = self._complete_node(state)
                        
            elif current_step == "emergency_complete":
                # 완료로
                state = self._complete_node(state)
            
            if self.debug:
                print(f"✅ 구조화된 처리: 턴 {state['conversation_turns']}")
            
            return state
            
        except Exception as e:
            if self.debug:
                print(f"❌ 구조화된 처리 실패: {e}")
            
            state["messages"].append({
                "role": "assistant",
                "content": "처리 중 문제가 발생했습니다. 긴급한 경우 일일이로 연락하세요.",
                "timestamp": datetime.now()
            })
            return state
    
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