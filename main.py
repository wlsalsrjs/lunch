import calendar
from datetime import datetime
import re
import requests
import streamlit as st

# ==========================================
# 0. 페이지 기본 설정 및 CSS 스타일링
# ==========================================
st.set_page_config(page_title="학교 급식 식단 달력", layout="wide")

st.markdown(
    """
    <style>
    /* 급식 카드 기본 스타일 */
    .meal-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 15px;
        background-color: #ffffff;
        min-height: 260px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* 오늘 날짜 카드 강조 */
    .today-card {
        border: 2px solid #ff4b4b !important;
        background-color: #fff9f9 !important;
    }
    /* 알레르기 주의 카드 강조 */
    .warning-card {
        border: 2px solid #ffa726 !important;
        background-color: #fffde7 !important;
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
    /* 알레르기 메뉴 강조 */
    .allergy-alert {
        color: #d32f2f;
        font-weight: bold;
        background-color: #ffebee;
        padding: 2px 4px;
        border-radius: 3px;
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


# 알레르기 번호를 이름으로 변환하는 함수
def convert_allergy_numbers(menu_text, convert_flag):
    if not convert_flag:
        return menu_text

    def replace_numbers(match):
        numbers = [n for n in match.group(1).split(".") if n]
        names = [ALLERGY_DICT.get(n, n) for n in numbers]
        return " (" + ", ".join(names) + ")"

    cleaned_menu = re.sub(r"\.([0-9\.]+)", replace_numbers, menu_text)
    return cleaned_menu


# 메뉴 항목에 검색 알레르기가 포함되어 있는지 확인하는 함수
def check_allergy_match(menu_text, allergy_targets):
    if not allergy_targets:
        return False

    for target in allergy_targets:
        target_str = str(target).strip()
        target_name = ALLERGY_DICT.get(target_str, target_str)

        # 메뉴명 자체 또는 번호 패턴(.1. 형태로 포함된 경우) 검사
        if (target_name in menu_text) or (
            target_str in ALLERGY_DICT and f".{target_str}." in menu_text
        ):
            return True

    return False


# ==========================================
# 2. API 인증키 및 사이드바 설정
# ==========================================
if "NEIS_KEY" not in st.secrets:
    st.error(
        "⚠️ NEIS_KEY가 설정되지 않았습니다. `.streamlit/secrets.toml` 파일에 `NEIS_KEY = '발급받은키'`를 입력해 주세요."
    )
    st.stop()

NEIS_KEY = st.secrets["NEIS_KEY"]

st.sidebar.title("🏫 학교 및 알레르기 설정")

office_code = st.sidebar.text_input("시도교육청코드", value="B10")
school_code = st.sidebar.text_input("표준학교코드", value="7010537")

convert_allergy = st.sidebar.toggle("알레르기 식품명으로 변환", value=True)

# 🚨 알레르기 주의 음식 검색 필터
st.sidebar.markdown("---")
st.sidebar.subheader("⚠️ 알레르기 음식 검색")

allergy_options = [f"{code}. {name}" for code, name in ALLERGY_DICT.items()]
selected_allergies = st.sidebar.multiselect(
    "주의할 알레르기 항목 선택",
    options=allergy_options,
    help="선택한 항목이 포함된 메뉴를 찾아서 알려드립니다.",
)

custom_allergy = st.sidebar.text_input(
    "기타 주의 키워드 직접 입력",
    placeholder="예: 카레, 치즈",
)

# 대상 알레르기 목록 정제
allergy_targets = []
for item in selected_allergies:
    code = item.split(".")[0]
    allergy_targets.append(code)

if custom_allergy.strip():
    allergy_targets.append(custom_allergy.strip())

with st.sidebar.expander("ℹ️ 알레르기 번호 안내"):
    for code, name in ALLERGY_DICT.items():
        st.write(f"**{code}**: {name}")

# ==========================================
# 3. 상단 설정 바
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
        "월 선택", options=list(range(1, 13)), index=today.month - 1
    )

with col_type:
    meal_type_filter = st.radio(
        "급식 종류",
        options=["전체 보기", "중식만 보기", "석식만 보기"],
        horizontal=True,
    )


# ==========================================
# 4. NEIS API 데이터 호출
# ==========================================
@st.cache_data(ttl=3600)
def fetch_month_meals(year, month, edu_code, sch_code, api_key):
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

        if "mealServiceDietInfo" in data:
            return data["mealServiceDietInfo"][1]["row"], None
        else:
            code = data.get("RESULT", {}).get("CODE", "UNKNOWN")
            if code == "INFO-200":
                return [], None
            return (
                None,
                f"API 응답 오류 ({code}): {data.get('RESULT', {}).get('MESSAGE', '')}",
            )
    except requests.exceptions.RequestException as e:
        return None, f"API 통신 오류가 발생했습니다: {e}"


raw_meals, error_msg = fetch_month_meals(
    selected_year, selected_month, office_code, school_code, NEIS_KEY
)

if error_msg:
    st.error(f"❌ {error_msg}")
    st.stop()

# 날짜별 그룹화
meals_by_date = {}
if raw_meals:
    for meal in raw_meals:
        ymd = meal["MLSV_YMD"]
        if ymd not in meals_by_date:
            meals_by_date[ymd] = []
        meals_by_date[ymd].append(meal)

# ==========================================
# 5. 알레르기 모아보기 요약 박스
# ==========================================
if allergy_targets:
    matched_summary = []

    for ymd, day_meals in sorted(meals_by_date.items()):
        day_num = int(ymd[6:8])
        for meal in day_meals:
            meal_name = meal.get("MTRIL_NM", meal.get("MMEAL_SC_NM", ""))
            menu_raw = meal.get("DDISH_NM", "")
            items = menu_raw.split("<br/>")

            for item in items:
                if check_allergy_match(item, allergy_targets):
                    clean_item = convert_allergy_numbers(item, True)
                    matched_summary.append(
                        f"**{selected_month}/{day_num}일 [{meal_name}]**: {clean_item}"
                    )

    if matched_summary:
        st.warning(
            f"🚨 **선택하신 알레르기 성분이 포함된 메뉴 ({len(matched_summary)}개 발견)**"
        )
        with st.expander("🔍 감지된 메뉴 전체 목록 보기", expanded=True):
            for item in matched_summary:
                st.write(f"- {item}")
    else:
        st.success("✅ 이번 달 선택하신 알레르기 성분이 포함된 메뉴가 없습니다.")

st.markdown("---")

# ==========================================
# 6. 달력 화면 구성
# ==========================================
cal = calendar.monthcalendar(selected_year, selected_month)
weekdays_name = ["월", "화", "수", "목", "금"]

try:
    for week in cal:
        work_days = week[:5]
        if sum(work_days) == 0:
            continue

        cols = st.columns(5)

        for idx, day in enumerate(work_days):
            with cols[idx]:
                if day == 0:
                    st.write("")
                    continue

                current_date_str = (
                    f"{selected_year}{selected_month:02d}{day:02d}"
                )
                is_today = (
                    selected_year == today.year
                    and selected_month == today.month
                    and day == today.day
                )

                day_meals = meals_by_date.get(current_date_str, [])

                # 해당 날짜에 알레르기 식재료가 포함되어 있는지 확인
                has_day_allergy = False
                if allergy_targets and day_meals:
                    for m in day_meals:
                        for item in m.get("DDISH_NM", "").split("<br/>"):
                            if check_allergy_match(item, allergy_targets):
                                has_day_allergy = True
                                break

                # 카드 스타일 설정
                card_class = "meal-card"
                if is_today:
                    card_class += " today-card"
                elif has_day_allergy:
                    card_class += " warning-card"

                today_badge = (
                    '<span class="today-tag">TODAY</span>' if is_today else ""
                )

                html_content = f"""
                <div class="{card_class}">
                    <div class="date-header">{selected_month}/{day} ({weekdays_name[idx]}) {today_badge}</div>
                """

                if not day_meals:
                    html_content += (
                        '<div class="no-meal">급식 없음 (주말/방학)</div>'
                    )
                else:
                    displayed_count = 0

                    for meal in day_meals:
                        meal_name = meal.get(
                            "MTRIL_NM", meal.get("MMEAL_SC_NM", "")
                        )
                        menu_raw = meal.get("DDISH_NM", "")

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
                        processed_menu = convert_allergy_numbers(
                            menu_raw, convert_allergy
                        )
                        items = processed_menu.split("<br/>")

                        if meal_name == "중식":
                            badge_class = "badge-lunch"
                        elif meal_name == "석식":
                            badge_class = "badge-dinner"
                        else:
                            badge_class = "badge-other"

                        html_content += (
                            f'<div class="{badge_class}">[{meal_name}]</div>'
                        )
                        html_content += "<ul style='padding-left: 15px; margin-top: 5px; font-size: 0.85em;'>"

                        for item in items:
                            item_clean = item.strip()
                            if not item_clean:
                                continue

                            # 개별 항목 강조
                            if check_allergy_match(item, allergy_targets):
                                html_content += f"<li><span class='allergy-alert'>⚠️ {item_clean}</span></li>"
                            else:
                                html_content += f"<li>{item_clean}</li>"

                        html_content += "</ul>"

                    if displayed_count == 0:
                        html_content += (
                            '<div class="no-meal">해당 식단 없음</div>'
                        )

                html_content += "</div>"
                st.markdown(html_content, unsafe_allow_html=True)

except Exception as e:
    st.error(f"❌ 화면을 구성하는 중 오류가 발생했습니다: {e}")
