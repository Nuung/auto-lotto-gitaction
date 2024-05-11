import re
import sys
import time
from datetime import datetime

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

# 구매 개수를 설정
COUNT = sys.argv[5]


class BalanceError(Exception):
    def __init__(self, message="An error occurred", code=None):
        self.message = message
        self.code = code
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message} - Code: {self.code}" if self.code else self.message


def get_now() -> datetime:
    # 한국 시간대 객체 생성
    korea_tz = pytz.timezone("Asia/Seoul")
    korea_time = datetime.now(pytz.utc).astimezone(korea_tz)
    return korea_time


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


def hook_slack_btn() -> Response:
    korea_time_str = get_now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "channel": SLACK_CHANNEL,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"> {korea_time_str} *로또 자동 구매 봇 알림* \n예치금이 부족합니다! 충전을 해주세요!",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "충전하러 가기",  # 버튼에 표시될 텍스트
                            "emoji": True,
                        },
                        "url": "https://dhlottery.co.kr/payment.do?method=payment",  # 사용자를 리디렉션할 URL
                        "action_id": "button_action",
                    }
                ],
            },
        ],
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

        # 로그인 이후 기본 정보 체크 & 예치금 알림
        page.goto("https://dhlottery.co.kr/common.do?method=main")
        money_info = page.query_selector("ul.information").inner_text()
        money_info: str = money_info.split("\n")
        user_name = money_info[0]
        money_info: int = int(money_info[2].replace(",", "").replace("원", ""))
        hook_slack(f"로그인 사용자: {user_name}, 예치금: {money_info}")

        # 예치금 잔액 부족 미리 exception
        if 1000 * int(COUNT) > money_info:
            raise BalanceError()

        # ================================================================ #
        # 구매하기
        # ================================================================ #

        page.goto(url="https://ol.dhlottery.co.kr/olotto/game/game645.do")
        # "비정상적인 방법으로 접속하였습니다. 정상적인 PC 환경에서 접속하여 주시기 바랍니다." 우회하기
        page.locator("#popupLayerAlert").get_by_role("button", name="확인").click()
        page.click("text=자동번호발급")

        # 구매할 개수를 선택
        page.select_option("select", str(COUNT))  # Select 1
        page.click("text=확인")
        page.click('input:has-text("구매하기")')  # Click input:has-text("구매하기")
        time.sleep(2)
        page.click(
            'text=확인 취소 >> input[type="button"]'
        )  # Click text=확인 취소 >> input[type="button"]
        page.click('input[name="closeLayer"]')
        # assert page.url == "https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40"

        hook_slack(
            f"{COUNT}개 복권 구매 성공! \n자세하게 확인하기: https://dhlottery.co.kr/myPage.do?method=notScratchListView"
        )

        # ================================================================ #
        # 오늘 구매한 복권 번호 확인하기
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
            result_msg += ", ".join(result.inner_text().split("\n")) + "\n"
        hook_slack(f"이번주 나의 행운의 번호는?!\n{result_msg}")
    except BalanceError:
        hook_slack_btn()
    except Exception as exc:
        hook_slack(exc)
    finally:
        # End of Selenium
        context.close()
        browser.close()


with sync_playwright() as playwright:
    run(playwright)
