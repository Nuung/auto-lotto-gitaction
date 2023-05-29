[![Lotto Buy Bot (로또 구매봇)](https://github.com/Nuung/auto-lotto-gitaction/actions/workflows/action.yml/badge.svg?branch=main)](https://github.com/Nuung/auto-lotto-gitaction/actions/workflows/action.yml)

# Buying Lottery by Github Actions
> ***매주 토요일 KST 08:50 에 동행 복권 로또 구매***
- https://dhlottery.co.kr/ 동행복권 홈페이지
- https://velog.io/@king/githubactions-lotto 참고한 벨로그
- public 으로 공유할 수 있게 모든 민감 정보 action secrets 값으로 관리
- 예치금 필요함!
- slack bot을 통해 slack noti (hook) 전달함


## STACK
- python
    - selenium (chrome driver)
    - requests
    - playwright
- lint: flask8 and black
- github action (action.yml)