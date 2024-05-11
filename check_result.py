import re
import sys
import time
from datetime import datetime
from typing import List

import pytz
from requests import post, Response, Session
from playwright.sync_api import Playwright, sync_playwright
from bs4 import BeautifulSoup

RUN_FILE_NAME = sys.argv[0]

# 동행복권 아이디와 패스워드를 설정
USER_ID = sys.argv[1]
USER_PW = sys.argv[2]

# SLACK 설정
SLACK_API_URL = "https://slack.com/api/chat.postMessage"
SLACK_BOT_TOKEN = sys.argv[3]
SLACK_CHANNEL = sys.argv[4]


def get_now() -> datetime:
    # 한국 시간대 객체 생성
    korea_tz = pytz.timezone("Asia/Seoul")
    korea_time = datetime.now(pytz.utc).astimezone(korea_tz)
    return korea_time


def get_check_lucky_number(lucky_numbers: List[str], my_numbers: List[str]) -> str:
    return_msg = ""
    for my_num in my_numbers:
        if my_num in lucky_numbers:
            return_msg += f" [ {my_num} ] "
            continue
        return_msg += f" {my_num} "
    return return_msg


def hook_slack(message: str) -> Response:
    korea_time_str = get_now().strftime("%Y-%m-%d %H:%M:%S")

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

        # ================================================================ #
        # 초기 세팅 및 로그인
        # ================================================================ #

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

        # ================================================================ #
        # 이번주 당첨 번호 파싱하기
        # ================================================================ #

        # 당첨 결과 및 번호 확인, parsing issue 때문에 3중 retry
        page.goto("https://dhlottery.co.kr/common.do?method=main")
        retry_cnt = 0
        result_info = page.query_selector("#article div.content")
        while not result_info and retry_cnt < 3:
            result_info = page.query_selector("#article div.content")
            retry_cnt += 1
        result_info = result_info.inner_text().split("이전")[0].replace("\n", " ")
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

        # ================================================================ #
        # 오늘 구매한 복권 번호 기반 결과 확인하기
        # ================================================================ #

        cookies = page.context.cookies()
        session = Session()
        for cookie in cookies:
            session.cookies.set(
                cookie["name"], cookie["value"], domain=cookie["domain"]
            )
        url = "https://dhlottery.co.kr/myPage.do"
        querystring = {"method": "lottoBuyList"}
        now_date = get_now().date().strftime("%Y%m%d")
        payload = f"searchStartDate={now_date}&searchEndDate={now_date}&winGrade=2"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ko,en;q=0.9,ko-KR;q=0.8,en-US;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://dhlottery.co.kr",
            "Referer": "https://dhlottery.co.kr/myPage.do?method=lottoBuyListView",
            "Sec-Fetch-Dest": "iframe",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "sec-ch-ua-mobile": "?0",
        }
        res = session.post(url, data=payload, headers=headers, params=querystring)
        html = BeautifulSoup(res.content, "lxml")
        a_tag_href = html.select_one(
            "tbody > tr:nth-child(1) > td:nth-child(4) > a"
        ).get("href")
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
                + get_check_lucky_number(lucky_number, my_lucky_number[1:])
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
