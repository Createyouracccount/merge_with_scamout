import logging
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)

class ImprovedInfoCollectionNode:
    """개선된 정보 수집 노드"""
    
    def __init__(self, info_extractor):
        self.extractor = info_extractor
        
        # 질문별 추출 타입 매핑
        self.question_types = {
            "victim": "yes_no",
            "loss_amount": "amount", 
            "time_context": "time",
            "account_frozen": "yes_no",
            "reported_to_police": "yes_no"
        }
        
        # 확인 질문 템플릿
        self.confirmation_templates = {
            "victim": "피해자 본인이 맞으시군요.",
            "loss_amount": "송금 금액이 {amount}인 것으로 확인됩니다.",
            "time_context": "송금 시기가 {time}인 것으로 확인됩니다.",
            "account_frozen": "계좌 지급정지 신청을 {status}하신 것으로 확인됩니다.",
            "reported_to_police": "경찰 신고를 {status}하신 것으로 확인됩니다."
        }
        
        # 재질문 템플릿
        self.retry_templates = {
            "victim": "죄송합니다. 피해자가 본인이신지 '네' 또는 '아니요'로 명확히 답변해 주세요.",
            "loss_amount": "송금 금액을 정확히 말씀해 주세요. 예: '300만원', '5천만원'",
            "time_context": "송금한 시간을 말씀해 주세요. 예: '30분 전', '오늘 오후', '어제'",
            "account_frozen": "계좌 지급정지 신청 여부를 '네' 또는 '아니요'로 답변해 주세요.",
            "reported_to_police": "경찰 신고 여부를 '네' 또는 '아니요'로 답변해 주세요."
        }
    
    def collect_info_enhanced(self, state, current_question_key: str, user_input: str):
        """강화된 정보 수집"""
        
        logger.info(f"정보 수집 시작: {current_question_key} - '{user_input}'")
        
        # 1. 정보 추출
        question_type = self.question_types.get(current_question_key, "text")
        extraction_result = self.extractor.extract_all_info(user_input, question_type)
        
        logger.debug(f"추출 결과: {extraction_result}")
        
        # 2. 신뢰도 확인
        confidence = extraction_result.get('confidence', 0.0)
        
        if confidence >= 0.8:  # 높은 신뢰도
            return self._handle_high_confidence(state, current_question_key, extraction_result)
        elif confidence >= 0.5:  # 중간 신뢰도
            return self._handle_medium_confidence(state, current_question_key, extraction_result)
        else:  # 낮은 신뢰도
            return self._handle_low_confidence(state, current_question_key, extraction_result)
    
    def _handle_high_confidence(self, state, question_key: str, result: Dict[str, Any]):
        """높은 신뢰도 처리"""
        
        # 상태에 정보 저장
        if question_key == "loss_amount":
            state[question_key] = result.get('formatted', result.get('raw_text'))
            # 긴급도 업데이트
            amount = result.get('amount')
            if amount and amount > 10000000:  # 천만원 이상
                state['urgency_level'] = 9
                state['is_emergency'] = True
        else:
            state[question_key] = result.get('answer', result.get('normalized', result.get('raw_text')))
        
        # 확인 메시지 생성
        confirmation = self._generate_confirmation_message(question_key, result)
        
        return {
            'success': True,
            'confirmation': confirmation,
            'proceed_to_next': True,
            'extracted_value': state[question_key]
        }
    
    def _handle_medium_confidence(self, state, question_key: str, result: Dict[str, Any]):
        """중간 신뢰도 처리 - 확인 질문"""
        
        extracted_value = result.get('answer', result.get('formatted', result.get('normalized')))
        
        # 확인 질문 생성
        if question_key == "loss_amount":
            confirmation_question = f"송금 금액이 {extracted_value}이 맞나요? 맞으면 '네', 틀리면 정확한 금액을 다시 말씀해 주세요."
        elif question_key == "time_context":
            confirmation_question = f"송금 시기가 {extracted_value}이 맞나요? 맞으면 '네', 틀리면 정확한 시간을 다시 말씀해 주세요."
        else:
            confirmation_question = f"{extracted_value}이 맞나요? '네' 또는 '아니요'로 답해주세요."
        
        # 임시 저장
        state[f"{question_key}_temp"] = extracted_value
        
        return {
            'success': False,
            'confirmation_needed': True,
            'confirmation_question': confirmation_question,
            'temp_value': extracted_value
        }
    
    def _handle_low_confidence(self, state, question_key: str, result: Dict[str, Any]):
        """낮은 신뢰도 처리 - 재질문"""
        
        # 재시도 횟수 체크
        retry_count = state.get(f"{question_key}_retry_count", 0)
        
        if retry_count < 2:  # 최대 2번 재시도
            state[f"{question_key}_retry_count"] = retry_count + 1
            retry_message = self.retry_templates.get(question_key, "다시 명확히 말씀해 주세요.")
            
            return {
                'success': False,
                'retry_needed': True,
                'retry_message': retry_message,
                'retry_count': retry_count + 1
            }
        else:
            # 최대 재시도 후에도 실패하면 기본값으로 진행
            logger.warning(f"최대 재시도 초과: {question_key}")
            state[question_key] = "확인 필요"
            
            return {
                'success': True,
                'confirmation': f"{question_key} 정보 확인이 필요합니다.",
                'proceed_to_next': True,
                'extracted_value': "확인 필요"
            }
    
    def _generate_confirmation_message(self, question_key: str, result: Dict[str, Any]) -> str:
        """확인 메시지 생성"""
        
        template = self.confirmation_templates.get(question_key, "정보가 확인되었습니다.")
        
        if question_key == "loss_amount":
            amount = result.get('formatted', result.get('raw_text'))
            return template.format(amount=amount)
        elif question_key == "time_context":
            time = result.get('normalized', result.get('raw_text'))
            return template.format(time=time)
        elif question_key in ["account_frozen", "reported_to_police"]:
            answer = result.get('answer', '미확인')
            status = "완료" if answer == "네" else "미완료"
            return template.format(status=status)
        else:
            return template
    
    def process_conversation_turn(self, state, question_flow, current_index: int, user_input: str):
        """대화 턴 처리"""
        
        if current_index >= len(question_flow):
            return self._finalize_collection(state)
        
        current_question = question_flow[current_index]
        question_key = current_question['key']
        
        # 확인 질문 응답 처리
        if state.get(f"{question_key}_confirmation_pending"):
            return self._handle_confirmation_response(state, question_key, user_input)
        
        # 일반 정보 수집
        collection_result = self.collect_info_enhanced(state, question_key, user_input)
        
        if collection_result['success']:
            # 성공 - 다음 질문으로
            state['current_question_index'] = current_index + 1
            
            response = collection_result['confirmation']
            
            # 다음 질문 추가
            if current_index + 1 < len(question_flow):
                next_question = question_flow[current_index + 1]['question']
                response += f"\n\n{next_question}"
            else:
                response += "\n\n정보 수집이 완료되었습니다."
                state['info_collection_complete'] = True
            
            return response
            
        elif collection_result.get('confirmation_needed'):
            # 확인 필요
            state[f"{question_key}_confirmation_pending"] = True
            return collection_result['confirmation_question']
            
        elif collection_result.get('retry_needed'):
            # 재시도 필요
            return collection_result['retry_message']
        
        return "처리 중 오류가 발생했습니다. 다시 시도해 주세요."
    
    def _handle_confirmation_response(self, state, question_key: str, user_input: str):
        """확인 질문 응답 처리"""
        
        yes_no_result = self.extractor.extract_yes_no(user_input)
        
        if yes_no_result['answer'] == '네':
            # 확인됨 - 임시값을 정식으로 저장
            temp_value = state.get(f"{question_key}_temp")
            state[question_key] = temp_value
            state[f"{question_key}_confirmation_pending"] = False
            
            # 다음 질문으로 진행
            current_index = state.get('current_question_index', 0)
            state['current_question_index'] = current_index + 1
            
            return f"확인되었습니다. {temp_value}"
            
        else:
            # 재입력 요청
            state[f"{question_key}_confirmation_pending"] = False
            retry_message = self.retry_templates.get(question_key, "다시 정확히 말씀해 주세요.")
            return retry_message
    
    def _finalize_collection(self, state):
        """정보 수집 완료 처리"""
        
        state['info_collection_complete'] = True
        
        # 수집된 정보 요약
        summary_parts = []
        
        field_names = {
            "victim": "피해자",
            "loss_amount": "손실 금액",
            "time_context": "발생 시기",
            "account_frozen": "지급정지 신청",
            "reported_to_police": "경찰 신고"
        }
        
        for field, name in field_names.items():
            value = state.get(field, "미확인")
            if value != "미확인":
                summary_parts.append(f"• {name}: {value}")
        
        summary = "\n".join(summary_parts) if summary_parts else "• 정보 수집 미완료"
        
        return f"""정보 수집이 완료되었습니다.

📋 수집된 정보:
{summary}

상황 분석을 시작하겠습니다."""

# 사용 예제
if __name__ == "__main__":
    from services.enhanced_info_extractor import EnhancedInfoExtractor
    
    extractor = EnhancedInfoExtractor()
    collector = ImprovedInfoCollectionNode(extractor)
    
    # 테스트 상태
    test_state = {
        'current_question_index': 1,
        'urgency_level': 5
    }
    
    # 테스트 케이스
    result = collector.collect_info_enhanced(test_state, "loss_amount", "15억")
    print("테스트 결과:", result)
    print("상태 업데이트:", test_state)