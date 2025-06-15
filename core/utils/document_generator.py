from typing import Dict, Any, List, Optional
from core.state import VictimRecoveryState

class DocumentGenerator:
    """필요 서류 생성 및 안내"""
    
    def generate_application_form_guide(self, state: VictimRecoveryState) -> str:
        """피해구제신청서 작성 가이드"""
        
        return f"""📝 **피해구제신청서 작성 가이드**

**기본 정보**
• 성명: (본인 성명)
• 주소: (주민등록상 주소)
• 연락처: (연락 가능한 번호)
• 이메일: (있는 경우)

**피해 정보**
• 피해 발생일: {state.get('damage_date', '미확인')}
• 피해 금액: {self._format_amount(state.get('damage_amount', 0))}
• 사기범 계좌: {state.get('scammer_account', '확인 필요')}
• 이체 방법: {state.get('transfer_method', '확인 필요')}

**피해 경위**
• 사기범이 어떻게 접근했는지
• 어떤 기관을 사칭했는지
• 송금하게 된 경위
• 피해를 알게 된 시점

**첨부 서류**
• 사건사고사실확인원 (경찰서 발급)
• 신분증 사본
• 계좌 이체 내역서
• 통화 녹음 파일 (있는 경우)

**작성 시 주의사항**
• 모든 항목을 정확히 기재
• 허위 기재 시 형사처벌 가능
• 본인 서명 필수

은행 방문 시 창구에서 양식을 받아 작성할 수 있습니다."""
    
    def generate_document_checklist(self, state: VictimRecoveryState) -> str:
        """서류 체크리스트"""
        
        required = [
            "사건사고사실확인원 (경찰서 발급)",
            "신분증 사본", 
            "피해구제신청서 (은행 제공)",
            "계좌이체 내역서"
        ]
        
        optional = [
            "통화 녹음 파일",
            "문자 메시지 캡처",
            "사기범과의 대화 기록",
            "피해 상황 설명서"
        ]
        
        checklist = "📋 **서류 체크리스트**\n\n**필수 서류** ✅\n"
        for i, doc in enumerate(required, 1):
            status = "✅" if doc in state.get('submitted_documents', []) else "⭐"
            checklist += f"{status} {i}. {doc}\n"
        
        checklist += "\n**선택 서류** (도움이 됨)\n"
        for i, doc in enumerate(optional, 1):
            status = "✅" if doc in state.get('submitted_documents', []) else "📝"
            checklist += f"{status} {i}. {doc}\n"
        
        checklist += "\n**제출 방법**\n"
        checklist += "• 은행 지점 방문 (권장)\n"
        checklist += "• 온라인 업로드 (은행별 상이)\n"
        checklist += "• 우편 제출 (사본만 가능)\n"
        
        return checklist
    
    def generate_police_report_guide(self) -> str:
        """경찰서 신고 가이드"""
        
        return """🏛️ **경찰서 신고 완벽 가이드**

**방문 전 준비**
• 신분증 지참
• 피해 상황 정리 (시간순)
• 사기범 연락처/계좌번호
• 이체 내역 출력

**신고 절차**
1. 가까운 경찰서 방문
2. 민원실에서 "보이스피싱 피해 신고" 말씀
3. 수사관과 상담
4. 피해 신고서 작성
5. 사건사고사실확인원 발급 요청

**신고 시 설명할 내용**
• 언제 어떤 방식으로 연락이 왔는지
• 상대방이 어떤 기관을 사칭했는지  
• 어떤 이유로 돈을 보내게 되었는지
• 피해를 알게 된 경위
• 현재까지 취한 조치

**발급받을 서류**
• 사건사고사실확인원 (은행 제출용)
• 사건번호 메모
• 담당 수사관 연락처

**소요 시간**
• 일반적으로 1-2시간
• 복잡한 경우 추가 시간 필요

**주의사항**
• 정확한 사실만 진술
• 추측이나 추정은 별도 표시
• 관련 증거 자료 모두 제출

신고 완료 후 바로 은행에 방문하시면 됩니다."""

    def _format_amount(self, amount: Optional[int]) -> str:
        """금액 포맷팅"""
        if not amount:
            return "확인 필요"
        
        if amount >= 100000000:
            return f"{amount // 100000000}억 {(amount % 100000000) // 10000}만원"
        elif amount >= 10000:
            return f"{amount // 10000}만원"
        else:
            return f"{amount:,}원"