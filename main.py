import calendar
from datetime import datetime
import requests
import streamlit as st

# ==========================================
# 0. 페이지 기본 설정 및 CSS 스타일링
# ==========================================
st.set_page_config(page_title="학교 급식 식단 달력", layout="wide")

# 카드를 깔끔하게 보여주기 위한 기본 CSS
st.markdown(
    """
    <style>
    /* 급식 카드 테두리 및 스타일 */
    .meal-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 15px;
        background-color: #ffffff;
        min-height: 250px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* 오늘 날짜 카드 강조 */
    .today-card {
        border: 2px solid #ff4b4b !important;
        background-color: #fff9f9 !important;
    }
    /* 급식 종류별 배지 스타일 */
    .badge-lunch {
        color: #1e88e5;
        font-weight: bold;
        border-bottom: 2px solid #1e88e5;
        padding-bottom: 2px;
        margin-top: 8px;
    }
    .badge-dinner {
        color: #e53935;
        font-weight: bold;
        border-bottom: 2px solid #e53935;
        padding-bottom: 2px;
        margin-top: 8px;
    }
    .badge-other {
        color: #43a047;
        font-weight: bold;
        border-bottom: 2px solid #43a047;
        padding-bottom: 2px;
        margin-top: 8px;
    }
    /* 날짜 헤더 */
    .date-header {
        font-size: 1.1em;
        font-weight: bold;
        margin-bottom: 8px;
    }
    .today-tag {
        background-color: #ff4b4b;
        color: white;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.8em;
        margin-left: 5px;
    }
    .no-meal {
        color: #888888;
        font-size: 0.9em;
        margin-top: 10px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 1. 알레르기 정보 매핑 사전
# ==========================================
ALLERGY_DICT = {
    "1": "난류",
    "2": "우유",
    "3": "메밀",
    "4": "땅콩",
    "5": "대두",
    "6": "밀",
    "7": "게",
    "8": "새우",
    "9": "돼지고기",
    "10": "복숭아",
    "11": "토마토",
    "12": "아황산류",
    "13": "호두",
    "14": "닭고기",
    "15": "쇠고기",
    "16": "오징어",
    "17": "조개류",
    "18": "계피",
    "19": "잣",
}


# 알레르기 번호를 이름으로 바꿔주는 함수
def convert_allergy_numbers(menu_text, convert_flag):
    if not convert_flag:
        return menu_text

    # 예: "요거트1.2.5." 형태에서 숫자 부분을 찾아 변환
    import re

    def replace_func(match):
        numbers = match.group(0).strip(".").split(".")
        names = [ALLERGY_DICT.get(num, num) for num in numbers if num]
        return f" ({', '.join(names)})"

    # 메뉴 뒤에 붙은 숫자 패턴(예: .1.2.5. 또는 1.2.5.) 찾기
    pattern = r"(\.\d+)+|\b(\d+\.)+"
    # NEIS 식단 텍스트는 보통 "음식명1.2.5." 형태로 들어오므로 괄호 표기 변환
    cleaned_menu = re.sub(
        r"\.([0-9\.]+)",
        lambda m: " ("
        + ", ".join([ALLERGY_DICT.get(n, n) for n in m.group(1).split(".") if n])
        + ")",
        menu_text,
    )
    return cleaned_menu


# ==========================================
# 2. API 인증키 확인 및 사이드바 설정
# ==========================================
# st.secrets에서 키 불러오기
if "NEIS_KEY" not in st.secrets:
    st.error(
        "⚠️ NEIS_KEY가 설정되지 않았습니다. `.streamlit/secrets.toml` 파일에 `NEIS_KEY = '발급받은키'`를 입력해 주세요."
    )
    st.stop()

NEIS_KEY = st.secrets["NEIS_KEY"]

st.sidebar.title("🏫 학교 및 표시 설정")

# 학교 정보 기본값 (예시: 서울특별시교육청 / 서울반포초등학교)
office_code = st.sidebar.text_input(
    "시도교육청코드",
    value="B10",
    help="예: B10 (서울특별시교육청)",
)
school_code = st.sidebar.text_input(
    "표준학교코드",
    value="7010537",
    help="예: 7010537",
)

# 알레르기 변환 토글
convert_allergy = st.sidebar.toggle(
    "알레르기 식품명으로 변환",
    value=False,
)

# 사이드바 알레르기 정보 접은글
with st.sidebar.expander("ℹ️ 알레르기 번호 안내"):
    for code, name in ALLERGY_DICT.items():
        st.write(f"**{code}**: {name}")

# ==========================================
# 3. 상단 날짜 및 급식 필터 선택
# ==========================================
st.title("🍽️ 우리 학교 월간 급식 달력")

today = datetime.now()
col_year, col_month, col_type = st.columns([1, 1, 2])

with col_year:
    selected_year = st.selectbox(
        "연도 선택",
        options=list(range(today.year - 1, today.year + 2)),
        index=1,
    )

with col_month:
    selected_month = st.selectbox(
        "월 선택",
        options=list(range(1, 13)),
        index=today.month - 1,
    )

with col_type:
    meal_type_filter = st.radio(
        "급식 종류",
        options=["전체 보기", "중식만 보기", "석식만 보기"],
        horizontal=True,
    )


# ==========================================
# 4. NEIS API 데이터 호출 함수
# ==========================================
@st.cache_data(ttl=3600)  # 1시간 동안 API 결과 캐싱
def fetch_month_meals(year, month, edu_code, sch_code, api_key):
    # 달의 1일부터 말일까지 구하기
    _, last_day = calendar.monthrange(year, month)
    from_ymd = f"{year}{month:02d}01"
    to_ymd = f"{year}{month:02d}{last_day:02d}"

    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "ATPT_OFCDC_SC_CODE": edu_code,
        "SD_SCHUL_CODE": sch_code,
        "MLSV_FROM_YMD": from_ymd,
        "MLSV_TO_YMD": to_ymd,
    }

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # 정상 데이터 반환 확인
        if "mealServiceDietInfo" in data:
            return data["mealServiceDietInfo"][1]["row"], None
        else:
            # API 내부 결과 코드 확인 (데이터가 없는 경우 등)
            code = data.get("RESULT", {}).get("CODE", "UNKNOWN")
            if code == "INFO-200":
                return [], None  # 해당 월 식단 데이터 없음
            return (
                None,
                f"API 응답 오류 ({code}): {data.get('RESULT', {}).get('MESSAGE', '')}",
            )

    except requests.exceptions.RequestException as e:
        return None, f"API 통신 오류가 발생했습니다: {e}"


# ==========================================
# 5. 데이터 가공 및 화면 구성
# ==========================================
raw_meals, error_msg = fetch_month_meals(
    selected_year, selected_month, office_code, school_code, NEIS_KEY
)

if error_msg:
    st.error(f"❌ {error_msg}")
    st.stop()

# 날짜별 급식 데이터를 딕셔너리로 구조화 { 'YYYYMMDD': [급식목록] }
meals_by_date = {}
if raw_meals:
    for meal in raw_meals:
        ymd = meal["MLSV_YMD"]
        if ymd not in meals_by_date:
            meals_by_date[ymd] = []
        meals_by_date[ymd].append(meal)

# 월~금 평일 달력 구조 가져오기 (주 단위 리스트)
cal = calendar.monthcalendar(selected_year, selected_month)
weekdays_name = ["월", "화", "수", "목", "금"]

st.markdown("---")

# 화면 구성 중 오류 발생 시 예외 처리
try:
    # 각 주차별로 반복
    for week in cal:
        # 월~금(0~4 index) 날짜만 추출
        work_days = week[:5]

        # 해당 주에 평일 날짜가 하루도 없으면 생략
        if sum(work_days) == 0:
            continue

        cols = st.columns(5)

        for idx, day in enumerate(work_days):
            with cols[idx]:
                if day == 0:
                    # 해당 달의 날짜가 아닌 경우 빈 카드
                    st.write("")
                    continue

                # 날짜 및 오늘 여부 판단
                current_date_str = (
                    f"{selected_year}{selected_month:02d}{day:02d}"
                )
                is_today = (
                    selected_year == today.year
                    and selected_month == today.month
                    and day == today.day
                )

                card_class = "meal-card today-card" if is_today else "meal-card"
                today_badge = (
                    '<span class="today-tag">TODAY</span>' if is_today else ""
                )

                # 카드 상단 날짜 및 요일 표시
                html_content = f"""
                <div class="{card_class}">
                    <div class="date-header">{selected_month}/{day} ({weekdays_name[idx]}) {today_badge}</div>
                """

                # 급식 정보 불러오기
                day_meals = meals_by_date.get(current_date_str, [])

                if not day_meals:
                    html_content += (
                        '<div class="no-meal">급식 없음 (주말/방학)</div>'
                    )
                else:
                    displayed_count = 0

                    for meal in day_meals:
                        meal_name = meal.get(
                            "MTRIL_NM", meal.get("MMEAL_SC_NM", "")
                        )  # 식사 구분명 (중식/석식 등)
                        menu_raw = meal.get("DDISH_NM", "")

                        # 필터 적용
                        if (
                            meal_type_filter == "중식만 보기"
                            and meal_name != "중식"
                        ):
                            continue
                        if (
                            meal_type_filter == "석식만 보기"
                            and meal_name != "석식"
                        ):
                            continue

                        displayed_count += 1

                        # 알레르기 이름 변환
                        processed_menu = convert_allergy_numbers(
                            menu_raw, convert_allergy
                        )

                        # HTML 태그 제거 및 줄바꿈 처리 (<br/> 태그 기준)
                        items = processed_menu.split("<br/>")

                        # 급식 종류별 배지 색상 적용
                        if meal_name == "중식":
                            badge_class = "badge-lunch"
                        elif meal_name == "석식":
                            badge_class = "badge-dinner"
                        else:
                            badge_class = "badge-other"

                        html_content += (
                            f'<div class="{badge_class}">[{meal_name}]</div>'
                        )
                        html_content += (
                            "<ul style='padding-left: 15px; margin-top: 5px; font-size: 0.85em;'>"
                        )
                        for item in items:
                            if item.strip():
                                html_content += f"<li>{item.strip()}</li>"
                        html_content += "</ul>"

                    if displayed_count == 0:
                        html_content += (
                            '<div class="no-meal">해당 식단 없음</div>'
                        )

                html_content += "</div>"
                st.markdown(html_content, unsafe_allow_html=True)

except Exception as e:
    st.error(f"❌ 화면을 구성하는 중 오류가 발생했습니다: {e}")
