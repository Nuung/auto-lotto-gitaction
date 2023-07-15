import re
import sys
import time
from datetime import datetime, timedelta
from typing import List

from requests import post, Response
from playwright.sync_api import Playwright, sync_playwright

RUN_FILE_NAME = sys.argv[0]

# 동행복권 아이디와 패스워드를 설정
USER_ID = sys.argv[1]
USER_PW = sys.argv[2]

# SLACK 설정
SLACK_API_URL = "https://slack.com/api/chat.postMessage"
SLACK_BOT_TOKEN = sys.argv[3]
SLACK_CHANNEL = sys.argv[4]


def __get_now() -> datetime:
    now_utc = datetime.utcnow()
    korea_timezone = timedelta(hours=9)
    now_korea = now_utc + korea_timezone
    return now_korea


def __check_lucky_number(lucky_numbers: List[str], my_numbers: List[str]) -> str:
    return_msg = ""
    for my_num in my_numbers:
        if my_num in lucky_numbers:
            return_msg += f" [ {my_num} ] "
            continue
        return_msg += f" {my_num} "
    return return_msg


def hook_slack(message: str) -> Response:
    korea_time_str = __get_now().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "text": f"> {korea_time_str} *로또 자동 구매 봇 알림* \n{message}",
        "channel": SLACK_CHANNEL,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
    }
    res = post(SLACK_API_URL, json=payload, headers=headers)
    return res


def run(playwright: Playwright) -> None:
    try:
        browser = playwright.chromium.launch(headless=True)  # chrome 브라우저를 실행
        context = browser.new_context()

        page = context.new_page()
        page.goto("https://dhlottery.co.kr/user.do?method=login")
        page.click('[placeholder="아이디"]')
        page.fill('[placeholder="아이디"]', USER_ID)
        page.press('[placeholder="아이디"]', "Tab")
        page.fill('[placeholder="비밀번호"]', USER_PW)
        page.press('[placeholder="비밀번호"]', "Tab")

        # Press Enter
        # with page.expect_navigation(url="https://ol.dhlottery.co.kr/olotto/game/game645.do"):
        with page.expect_navigation():
            page.press('form[name="jform"] >> text=로그인', "Enter")
        time.sleep(4)

        # 당첨 결과 및 번호 확인
        page.goto("https://dhlottery.co.kr/common.do?method=main")
        result_info = page.query_selector("#article div.content").inner_text()
        result_info = result_info.split("이전")[0].replace("\n", " ")
        hook_slack(f"로또 결과: {result_info}")

        # 번호 추출하기
        # last index가 보너스 번호
        lucky_number = (
            result_info.split("당첨번호")[-1]
            .split("1등")[0]
            .strip()
            .replace("보너스번호 ", "")
            .replace(" ", ",")
        )
        lucky_number = lucky_number.split(",")

        # 오늘 구매한 복권 결과
        now_date = __get_now().date().strftime("%Y%m%d")
        page.goto(
            url=f"https://dhlottery.co.kr/myPage.do?method=lottoBuyList&searchStartDate={now_date}&searchEndDate={now_date}&lottoId=&nowPage=1"
        )
        a_tag_href = page.query_selector(
            "tbody > tr:nth-child(1) > td:nth-child(4) > a"
        ).get_attribute("href")
        detail_info = re.findall(r"\d+", a_tag_href)
        page.goto(
            url=f"https://dhlottery.co.kr/myPage.do?method=lotto645Detail&orderNo={detail_info[0]}&barcode={detail_info[1]}&issueNo={detail_info[2]}"
        )
        result_msg = ""
        for result in page.query_selector_all("div.selected li"):
            # 0번째 index에 기호와 당첨/낙첨 여부 포함
            my_lucky_number = result.inner_text().split("\n")
            result_msg += (
                my_lucky_number[0]
                + __check_lucky_number(lucky_number, my_lucky_number[1:])
                + "\n"
            )
        hook_slack(f"> 이번주 나의 행운의 번호 결과는?!?!?!\n{result_msg}")

        # End of Selenium
        context.close()
        browser.close()
    except Exception as exc:
        hook_slack(exc)
        context.close()
        browser.close()
        raise exc


with sync_playwright() as playwright:
    run(playwright)
