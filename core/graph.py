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
    - 실질적 도움 제공 중심
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
신속한 도움을 위해 몇 가지 질문을 드리겠습니다. 힘드시겠지만, 답변 부탁드립니다."""

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
        
        # 첫 시작일 때는 기본 긴급도 설정
        if not last_message:
            urgency_level = 5  # 기본값
        else:
            # 스마트한 긴급도 판단
            urgency_level = self._assess_urgency_smart(last_message)
        
        state["urgency_level"] = urgency_level
        
        # 첫 시작일 때는 단순 인사, 이후에는 긴급도별 응답
        if not last_message:
            response = """같이 하나씩 해결해보아요. 어디서부터 시작해볼까요?"""
        else:
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
    
    def _emergency_action_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """실질적 도움이 되는 긴급 조치 안내"""
        
        # 수집된 정보 기반 맞춤 조치
        urgency_level = state.get("urgency_level", 5)
        loss_amount = state.get("loss_amount", 0)
        account_frozen = state.get("account_frozen", False)
        reported_to_police = state.get("reported_to_police", False)
        
        # 긴급도별 실질적 조치 안내
        if urgency_level >= 8:
            response = self._generate_high_urgency_guidance(state)
        elif urgency_level >= 6:
            response = self._generate_medium_urgency_guidance(state)
        else:
            response = self._generate_low_urgency_guidance(state)
        
        state["messages"].append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "emergency_complete"
        
        if self.debug:
            print("✅ 실질적 긴급 조치 안내 완료")
        
        return state
    
    def _generate_high_urgency_guidance(self, state: VictimRecoveryState) -> str:
        """고긴급도 실질적 조치 안내"""
        
        loss_amount = state.get("loss_amount", 0)
        account_frozen = state.get("account_frozen", False)
        
        response = """🚨 즉시 실행하세요 (추가 피해 방지가 우선):

1️⃣ **명의도용 확인 & 차단** (가장 중요!)
   • mSAFER (www.msafer.or.kr) 또는 PASS앱에서
   • 내 명의로 개통된 모든 휴대폰 확인
   • 명의도용 발견시 즉시 해지 + 신규개통 차단

2️⃣ **계좌 명의도용 확인**
   • payinfo.or.kr (금융결제원)에서 확인
   • 내가 모르는 계좌 있으면 '내계좌 일괄지급정지'

3️⃣ **확실한 지원 받기**
   • 보이스피싱제로 (voicephisingzero.co.kr)
     → 생활비 최대 300만원 (중위소득 100% 이하)
     → 무료 법률상담 + 소송지원
   • 대한법률구조공단 132번 무료 상담

4️⃣ **개인정보 보호**
   • pd.fss.or.kr에서 개인정보노출자 등록
   • 신규 계좌개설/카드발급 제한"""

        # 개인 상황별 추가 안내
        if not account_frozen:
            response += "\n\n⚠️ 지급정지 미신청시: 112나 해당 은행 고객센터로 즉시 신청"
        
        if loss_amount and "만원" in str(loss_amount):
            response += "\n\n💰 피해금액이 큰 경우: 보이스피싱제로 지원이 3일 환급보다 확실할 수 있습니다"
        
        response += """\n\n🎯 **핵심**: 3일 환급 성공률은 30-40%이지만, 
보이스피싱제로 생활비 지원은 조건만 맞으면 확실한 300만원입니다!"""
        
        return response
    
    def _generate_medium_urgency_guidance(self, state: VictimRecoveryState) -> str:
        """중긴급도 맞춤 조치 안내"""
        
        response = """📞 **먼저 전문가 상담 받으세요:**

1️⃣ **무료 법률상담** (개인 맞춤 전략 수립)
   • 대한법률구조공단 132번 (무료)
   • 온라인: www.klac.or.kr 사이버상담
   • 상황별 최적 대응법 안내

2️⃣ **지원 가능성 확인**
   • 보이스피싱제로 (1811-0041)
     → 중위소득 100% 이하면 생활비 300만원
     → 심리상담비 200만원, 법률비용 지원
   • 최근 3년 내 피해면 신청 가능

3️⃣ **예방 조치**
   • mSAFER 명의도용 방지 서비스 등록
   • 가족들도 함께 등록 권장

4️⃣ **정보 수집**
   • payinfo.or.kr에서 계좌 현황 확인
   • 의심스러운 개설 계좌 없는지 점검

💡 **상담 결과에 따라** 3일 환급 vs 생활비 지원 vs 소송 중 
최적 방법을 선택하세요."""
        
        return response
    
    def _generate_low_urgency_guidance(self, state: VictimRecoveryState) -> str:
        """저긴급도 예방 중심 안내"""
        
        response = """🛡️ **예방과 정보 수집 중심:**

1️⃣ **무료 상담으로 정확한 판단**
   • 대한법률구조공단 132번
   • 실제 피해인지, 대응법은 무엇인지 확인

2️⃣ **명의도용 방지 설정** (매우 중요)
   • mSAFER (www.msafer.or.kr) 가입
   • 휴대폰, 인터넷 등 신규 개통 시 SMS 알림
   • 가족 전체 설정 권장

3️⃣ **지원 조건 미리 확인**
   • 보이스피싱제로 지원 대상인지 확인
   • 중위소득 100% 이하면 향후 지원 가능

4️⃣ **장기적 보안 강화**
   • 모든 금융앱 비밀번호 변경
   • 이상한 링크/앱 설치 주의
   • pd.fss.or.kr 개인정보노출 등록 고려

📚 **정보 수집**: 실제 피해 규모와 회복 가능성을 
전문가 상담으로 정확히 파악하는 것이 우선입니다."""
        
        return response
    
    def _complete_node(self, state: VictimRecoveryState) -> VictimRecoveryState:
        """개선된 상담 완료"""
        
        # 수집된 정보 요약
        summary = self._generate_summary(state)
        urgency_level = state.get("urgency_level", 5)
        
        # 긴급도에 따른 맞춤 완료 메시지
        if urgency_level >= 8:
            completion_message = f"""상담이 완료되었습니다.

📋 수집된 정보 요약:
{summary}

🚨 **우선순위 행동사항:**
1. mSAFER (www.msafer.or.kr)에서 명의도용 차단
2. 보이스피싱제로 (voicephisingzero.co.kr) 생활비 지원 신청
3. 대한법률구조공단 132번 무료 상담

⚠️ 기억하세요: 3일 환급보다 300만원 생활비 지원이 더 확실합니다!

24시간 내 위 조치들을 완료하시고, 추가 문의사항이 있으시면 언제든 연락주세요."""

        elif urgency_level >= 6:
            completion_message = f"""상담이 완료되었습니다.

📋 수집된 정보 요약:
{summary}

📞 **다음 단계:**
1. 대한법률구조공단 132번으로 무료 전문상담
2. 상담 결과에 따라 최적 대응 방법 선택
3. mSAFER 명의도용 방지 서비스 등록

💡 전문가 상담을 통해 개인 상황에 맞는 최적의 해결책을 찾으시기 바랍니다."""

        else:
            completion_message = f"""상담이 완료되었습니다.

📋 수집된 정보 요약:
{summary}

🛡️ **예방 중심 조치:**
1. mSAFER (www.msafer.or.kr) 명의도용 방지 서비스 등록
2. 대한법률구조공단 132번으로 정확한 상황 확인
3. 보이스피싱제로 지원 조건 미리 확인

정확한 피해 여부와 대응법은 전문가 상담을 통해 확인하시기 바랍니다."""

        state["messages"].append({
            "role": "assistant",
            "content": completion_message,
            "timestamp": datetime.now()
        })
        
        state["current_step"] = "consultation_complete"
        
        if self.debug:
            print("✅ 개선된 상담 완료")
        
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

    def _route_after_collect(self, state: VictimRecoveryState) -> Literal["collect_info", "emergency_action", "complete"]:
        """정보 수집 후 라우팅 - 수정된 로직"""
        
        # 정보 수집 완료 체크
        current_index = state.get("current_question_index", 0)
        
        if current_index < len(self.question_flow):
            # 아직 질문이 남아있으면 계속 정보 수집
            return "collect_info"
        else:
            # 모든 질문 완료
            state["info_collection_complete"] = True
            
            if state.get("is_emergency", False) or state.get("urgency_level", 0) >= 7:
                return "emergency_action"
            else:
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
    # 메인 인터페이스 - 🔧 무한루프 해결
    # ========================================================================
    
    async def start_conversation(self, session_id: str = None) -> VictimRecoveryState:
        """구조화된 상담 시작 (무한루프 방지)"""
        
        if not session_id:
            session_id = f"struct_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        initial_state = create_initial_recovery_state(session_id)
        
        try:
            # 🔧 수정: 무한루프 방지를 위해 간단한 초기화만
            # 그래프 실행 대신 수동으로 첫 단계만 실행
            initial_state = self._greeting_node(initial_state)
            initial_state = self._initial_assessment_node(initial_state)
            
            if self.debug:
                print(f"✅ 간단한 상담 시작: {initial_state.get('current_step', 'unknown')}")
            
            return initial_state
            
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
        """단계별 대화 처리 - 질문 하나씩"""
        
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
            # 🔧 핵심: 단계별 진행을 위해 구조화된 방식 사용
            current_step = state.get("current_step", "greeting_complete")
            
            if current_step == "greeting_complete" or current_step == "assessment_complete":
                # 첫 질문 시작
                state = self._collect_info_node(state)
                
            elif current_step == "collecting_info":
                # 질문 계속 진행
                state = self._collect_info_node(state)
                
                # 모든 질문 완료 시 긴급 조치
                if state.get("info_collection_complete", False):
                    if state.get("urgency_level", 0) >= 7:
                        state = self._emergency_action_node(state)
                    else:
                        state = self._complete_node(state)
            
            else:
                # 완료된 상태에서는 추가 질문 대응
                response = "추가로 궁금한 점이 있으시면 말씀해 주세요."
                state["messages"].append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now()
                })
            
            # 마지막 AI 메시지 추출해서 TTS용 반환
            last_ai_message = ""
            for msg in reversed(state.get("messages", [])):
                if msg.get("role") == "assistant":
                    last_ai_message = msg.get("content", "")
                    break
            
            if self.debug:
                print(f"✅ 단계별 처리: {state.get('current_step')} (턴 {state['conversation_turns']})")
            
            return state
            
        except Exception as e:
            if self.debug:
                print(f"❌ 대화 처리 실패: {e}")
            
            state["messages"].append({
                "role": "assistant",
                "content": "처리 중 문제가 발생했습니다. 긴급한 경우 대한법률구조공단 132번으로 연락하세요.",
                "timestamp": datetime.now()
            })
            return state
    
    def _simple_rule_based_response(self, user_input: str, state: VictimRecoveryState) -> Dict[str, Any]:
        """간단한 규칙 기반 응답 (Gemini 없을 때)"""
        
        user_lower = user_input.lower()
        urgency = 3
        
        # 긴급도 계산
        if any(word in user_lower for word in ['돈', '송금', '보냈', '이체', '틀렸', '사기', '억', '만원']):
            urgency = 8
        elif any(word in user_lower for word in ['의심', '이상', '피싱']):
            urgency = 6
        
        # 실질적 도움 응답
        if urgency >= 8:
            response = """🚨 즉시 실행하세요:

1️⃣ mSAFER (www.msafer.or.kr)에서 명의도용 차단
2️⃣ 보이스피싱제로 (voicephisingzero.co.kr)에서 300만원 생활비 지원 신청
3️⃣ 대한법률구조공단 132번 무료 상담

💡 3일 환급보다 300만원 지원이 더 확실합니다!"""
        elif urgency >= 6:
            response = """📞 전문가 상담 우선:

1️⃣ 대한법률구조공단 132번 무료 상담
2️⃣ 보이스피싱제로 지원 조건 확인
3️⃣ mSAFER 명의도용 방지 설정

개인 상황에 맞는 최적 전략을 수립하세요."""
        else:
            response = """🛡️ 예방 조치:

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
    
    def _check_gemini_available(self) -> bool:
        """Gemini 사용 가능 여부 확인"""
        
        try:
            # Gemini 어시스턴트 import 시도
            from services.gemini_assistant import gemini_assistant
            return gemini_assistant.is_enabled
        except ImportError:
            if self.debug:
                print("⚠️ Gemini 어시스턴트 없음 - 규칙 기반 모드 사용")
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
            
            # 규칙 기반으로 폴백
            return self._simple_rule_based_response(user_input, state)
    
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