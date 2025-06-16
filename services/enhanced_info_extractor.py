import re
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class EnhancedInfoExtractor:
    """강화된 정보 추출 클래스"""
    
    def __init__(self):
        # 금액 단위 매핑
        self.amount_units = {
            '원': 1,
            '천원': 1000,
            '만원': 10000,
            '십만원': 100000,
            '백만원': 1000000,
            '천만원': 10000000,
            '억': 100000000,
            '억원': 100000000,
            '십억': 1000000000,
            '백억': 10000000000,
            '천억': 100000000000,
            '조': 1000000000000
        }
        
        # 시간 표현 패턴
        self.time_patterns = [
            (r'(\d+)분\s*전', r'\1분 전'),
            (r'(\d+)시간\s*전', r'\1시간 전'),
            (r'(\d+)일\s*전', r'\1일 전'),
            (r'오늘', '오늘'),
            (r'어제', '어제'),
            (r'그제', '그제'),
            (r'(\d+)월\s*(\d+)일', r'\1월 \2일'),
        ]
        
        # 긍정/부정 표현
        self.yes_patterns = [
            '네', '예', '맞아', '맞아요', '맞습니다', '그래요', '응', '엉', 
            '웅', '맞', '맛아', '맛', '그럼', '당연', 'yes', '했어', '했습니다',
            '신청했', '했다', '완료', '마쳤'
        ]
        
        self.no_patterns = [
            '아니', '아니요', '아뇨', '안했', '못했', '안함', '안해', 
            '아직', 'no', '땡', '아닌', '아님', '모름', '몰라'
        ]
        
    def extract_amount(self, text: str) -> Dict[str, Any]:
        """금액 추출 및 정규화"""
        
        text = text.strip().lower()
        logger.debug(f"금액 추출 시도: '{text}'")
        
        result = {
            'raw_text': text,
            'amount': None,
            'formatted': '미확인',
            'confidence': 0.0
        }
        
        try:
            # 1. 명시적 단위가 있는 경우
            for unit, multiplier in sorted(self.amount_units.items(), 
                                         key=lambda x: len(x[0]), reverse=True):
                pattern = rf'(\d+(?:\.\d+)?)\s*{re.escape(unit)}'
                match = re.search(pattern, text)
                
                if match:
                    number = float(match.group(1))
                    total_amount = int(number * multiplier)
                    
                    result.update({
                        'amount': total_amount,
                        'formatted': f"{total_amount:,}원",
                        'confidence': 0.9,
                        'unit_detected': unit
                    })
                    
                    logger.info(f"금액 추출 성공: {text} → {total_amount:,}원")
                    return result
            
            # 2. 숫자만 있는 경우 - 단위 추정
            number_match = re.search(r'(\d+(?:,\d{3})*(?:\.\d+)?)', text)
            if number_match:
                number_str = number_match.group(1).replace(',', '')
                number = float(number_str)
                
                # 크기에 따른 단위 추정
                if number >= 1000000:  # 100만 이상이면 원 단위로 추정
                    estimated_amount = int(number)
                    confidence = 0.7
                elif number >= 1000:   # 1000 이상이면 만원 단위로 추정
                    estimated_amount = int(number * 10000)
                    confidence = 0.6
                elif number >= 10:     # 10 이상이면 억 단위로 추정
                    estimated_amount = int(number * 100000000)
                    confidence = 0.8
                else:                  # 작은 숫자면 원 단위
                    estimated_amount = int(number)
                    confidence = 0.3
                
                result.update({
                    'amount': estimated_amount,
                    'formatted': f"{estimated_amount:,}원 (추정)",
                    'confidence': confidence,
                    'estimated': True
                })
                
                logger.info(f"금액 추정: {text} → {estimated_amount:,}원 (신뢰도: {confidence})")
                return result
            
            # 3. 한글 숫자 처리
            hangul_amount = self._parse_hangul_number(text)
            if hangul_amount:
                result.update({
                    'amount': hangul_amount,
                    'formatted': f"{hangul_amount:,}원",
                    'confidence': 0.8,
                    'hangul_detected': True
                })
                return result
                
        except Exception as e:
            logger.error(f"금액 추출 오류: {e}")
        
        logger.warning(f"금액 추출 실패: '{text}'")
        return result
    
    def extract_time(self, text: str) -> Dict[str, Any]:
        """시간 표현 추출 및 정규화"""
        
        text = text.strip()
        logger.debug(f"시간 추출 시도: '{text}'")
        
        result = {
            'raw_text': text,
            'normalized': text,
            'confidence': 0.0
        }
        
        try:
            # 패턴 매칭
            for pattern, replacement in self.time_patterns:
                match = re.search(pattern, text)
                if match:
                    if r'\1' in replacement:
                        normalized = re.sub(pattern, replacement, text)
                    else:
                        normalized = replacement
                    
                    result.update({
                        'normalized': normalized,
                        'confidence': 0.9,
                        'pattern_matched': pattern
                    })
                    
                    logger.info(f"시간 추출 성공: {text} → {normalized}")
                    return result
            
            # 불완전한 표현 처리 ("25분 전에 다" → "25분 전")
            if '분' in text and '전' in text:
                cleaned = re.sub(r'에?\s*다$', '', text).strip()
                if cleaned != text:
                    result.update({
                        'normalized': cleaned,
                        'confidence': 0.7,
                        'cleaned': True
                    })
                    return result
            
        except Exception as e:
            logger.error(f"시간 추출 오류: {e}")
        
        return result
    
    def extract_yes_no(self, text: str) -> Dict[str, Any]:
        """예/아니오 추출 및 정규화"""
        
        text = text.strip().lower()
        logger.debug(f"예/아니오 추출 시도: '{text}'")
        
        result = {
            'raw_text': text,
            'answer': '미확인',
            'confidence': 0.0
        }
        
        try:
            # 긍정 표현 확인
            for yes_word in self.yes_patterns:
                if yes_word in text:
                    result.update({
                        'answer': '네',
                        'confidence': 0.9,
                        'matched_word': yes_word
                    })
                    logger.info(f"긍정 응답 감지: {text} → 네")
                    return result
            
            # 부정 표현 확인
            for no_word in self.no_patterns:
                if no_word in text:
                    result.update({
                        'answer': '아니요',
                        'confidence': 0.9,
                        'matched_word': no_word
                    })
                    logger.info(f"부정 응답 감지: {text} → 아니요")
                    return result
            
            # 불완전한 응답 처리
            if len(text) <= 3 and any(char in text for char in ['예', '네', '응']):
                result.update({
                    'answer': '네',
                    'confidence': 0.6,
                    'partial_match': True
                })
                return result
            
        except Exception as e:
            logger.error(f"예/아니오 추출 오류: {e}")
        
        return result
    
    def _parse_hangul_number(self, text: str) -> Optional[int]:
        """한글 숫자 파싱"""
        
        hangul_numbers = {
            '일': 1, '이': 2, '삼': 3, '사': 4, '오': 5,
            '육': 6, '칠': 7, '팔': 8, '구': 9, '십': 10,
            '백': 100, '천': 1000, '만': 10000,
            '억': 100000000, '조': 1000000000000
        }
        
        # 간단한 한글 숫자 파싱 (예: "십오억")
        if any(char in text for char in hangul_numbers.keys()):
            # 복잡한 파싱 로직 구현 필요
            # 여기서는 기본적인 경우만 처리
            if '십오억' in text:
                return 1500000000
            elif '이십억' in text:
                return 2000000000
        
        return None
    
    def extract_all_info(self, text: str, question_type: str) -> Dict[str, Any]:
        """통합 정보 추출"""
        
        if question_type == "amount":
            return self.extract_amount(text)
        elif question_type == "time":
            return self.extract_time(text)
        elif question_type == "yes_no":
            return self.extract_yes_no(text)
        else:
            return {
                'raw_text': text,
                'processed': text.strip(),
                'confidence': 0.5
            }

# 사용 예제
if __name__ == "__main__":
    extractor = EnhancedInfoExtractor()
    
    # 테스트 케이스
    test_cases = [
        ("15억", "amount"),
        ("25분 전에 다", "time"),
        ("예 만", "yes_no"),
        ("내가", "yes_no"),
        ("천만원", "amount"),
        ("오늘 오후", "time"),
        ("했습니다", "yes_no")
    ]
    
    for text, q_type in test_cases:
        result = extractor.extract_all_info(text, q_type)
        print(f"입력: '{text}' ({q_type})")
        print(f"결과: {result}")
        print("-" * 40)