# API 키·비용 안내 초안

닿는제주 API 키는 프로젝트 폴더의 `.env`에 저장합니다.

확인일 2026-11-07. 키는 센터 담당자 또는 실행자가 자신의 계정으로 발급합니다. 아래 예시는 변수 이름과 공란만 제공하며 실제 키는 코드·문서·로그·캡처·제출물에 넣지 않습니다. 계정별 승인·결제·할당량은 발급 화면에서 최종 확인해야 합니다.

## 공공데이터포털: 단기·중기·관광공사

1. [공공데이터포털](https://www.data.go.kr/)에 로그인합니다.
2. 아래 **세 서비스에 각각 활용신청**합니다. 같은 일반 인증키를 사용하더라도 서비스별 활용 승인 여부는 다릅니다.
3. 사용 목적·개발계정 정보를 입력하고 승인 상태와 트래픽 한도를 확인합니다. 개발계정/운영계정 변경·증설이 필요하면 해당 서비스 안내에 따릅니다. 자동 승인 여부·반영 시간을 고정값으로 보장하지 않습니다.
4. 마이페이지의 일반 인증키 중 **Decoding** 값을 `.env`에 입력합니다. URL 인코딩된 키를 다시 인코딩하면 인증 실패할 수 있습니다. 키가 표시되는 전체 요청 URL을 공유하지 마세요.

| 신청 서비스 | 데이터 번호·공식 링크 | .env 변수 |
|---|---|---|
| 기상청 단기예보 조회서비스 | [15084084](https://www.data.go.kr/data/15084084/openapi.do) | `KMA_SERVICE_KEY` |
| 기상청 중기예보 조회서비스 | [15059468](https://www.data.go.kr/data/15059468/openapi.do) | 위와 같은 키. 중기 별도 활용신청 필요 |
| 한국관광공사 무장애 여행 정보 | [15101897](https://www.data.go.kr/data/15101897/openapi.do), KorWithService2 | `KTO_SERVICE_KEY` |

```dotenv
KMA_SERVICE_KEY=
KTO_SERVICE_KEY=
```

`python cli.py --check`는 설정된 LLM 및 기상청 단기·중기를 실제 호출합니다. 관광공사와 단기 연결만 점검하려면 `python collect_kto.py --check`, 전체 제주 목록·상세 수집은 `python collect_kto.py --interval 0.4`를 실행합니다. 키 값은 출력하지 않습니다.

인증 오류는 서비스 미신청·승인 대기·폐기/잘못된 키·인코딩 중복·반영 지연을 점검합니다. 서버의 오류 코드·문구를 기준으로 확인하며 HTTP 200이어도 업무 오류일 수 있습니다. 중기 이용 권한 오류는 ‘중기예보 활용신청 필요’로 안내합니다. 할당량 초과나 서버 오류는 승인·한도를 확인하고 잠시 후 재시도합니다. 상세 정책은 해당 서비스의 최신 활용가이드를 우선합니다.

## LLM 공통 설정

한 번에 제공자 하나를 선택합니다. 키를 비우거나 `LLM_PROVIDER=none`이면 규칙 모드입니다. API 키는 `.env`에서 읽으며 변경 후 서버 재시작이 필요합니다.

```dotenv
LLM_PROVIDER=none
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT=20
LLM_DAILY_LIMIT=
LLM_USD_KRW=1400
```

`LLM_MODEL`이 공란일 때 현재 기본값은 OpenAI `gpt-6-luna`, Gemini `gemini-3.5-flash-lite`, Claude `claude-haiku-5-5`입니다. 모델 접근 권한·일일 요청 수는 각 계정에 따라 다릅니다.

### OpenAI

[공식 시작 안내](https://developers.openai.com/api/docs/quickstart)에 따라 API 플랫폼 계정·프로젝트를 준비하고 [API 키 관리](https://platform.openai.com/api-keys)에서 키를 생성합니다. 해당 프로젝트의 결제·크레딧·모델 권한을 확인합니다. `.env`에서 `LLM_PROVIDER=openai`, `LLM_API_KEY`에 발급값, 모델은 공란 또는 `gpt-6-luna`로 설정합니다. 키는 발급 직후 안전한 로컬 위치에 보관하고 앱의 명령 인수로 전달하지 않습니다.

### Gemini

[Google AI Studio 키 관리](https://aistudio.google.com/apikey)에서 프로젝트를 선택/생성하고 키를 만듭니다. [공식 키 안내](https://ai.google.dev/gemini-api/docs/api-key)의 현재 인증 방식·API 제한을 확인합니다. `.env`에서 `LLM_PROVIDER=gemini`로 설정하고 키를 입력합니다. 새 auth 키 등 키의 접두어만으로 유효 여부를 판정하지 않습니다. 무료 구간은 모델·프로젝트·지역·할당량에 따라 달라지며 키 발급이 무제한 무료 호출을 의미하지 않습니다. 결제 사용 시 프로젝트의 billing 설정도 확인합니다.

### Claude

[Claude API 공식 안내](https://platform.claude.com/docs/en/api/overview)의 Console에 로그인해 조직/작업공간과 API 키를 준비하고 크레딧·결제를 확인합니다. `.env`에서 `LLM_PROVIDER=claude`, 키를 입력하고 모델은 공란 또는 `claude-haiku-5-5`로 둡니다. 소비자용 채팅 구독과 API 사용 권한·요금은 별도로 확인합니다.

## 예상 비용 — 질문 1건·월 10만 원 참고 시나리오

**실측 청구액이 아닌 예산 계산용 가정**입니다. 질문 하나는 보통 조건 해석+설명으로 LLM 최대 2회이며, 아래 토큰 수는 **두 요청 합계** 입력 6,000·출력 1,000토큰으로 가정했습니다. 질문·근거 길이에 따라 크게 달라지고 캐시 재사용은 새 호출을 줄입니다. 연결 테스트도 호출에 포함될 수 있습니다.

2026-11-07 확인한 일반 텍스트 표준 단가와 앱의 가정 환율 **1 USD=1,400원**을 사용합니다. 할인·배치·제공자 캐시 할인·세금·실제 환율은 반영하지 않았습니다.

| 현재 기본 모델 | 입력 USD/100만 토큰 | 출력 USD/100만 토큰 | 가정 질문 1건 | 월 10만 원으로 계산한 질문 수 |
|---|---:|---:|---:|---:|
| OpenAI gpt-6-luna | 0.10 | 0.50 | 약 1.54원 | 약 64,935건 |
| Gemini 3.5 Flash-Lite 유료 표준 | 0.30 | 2.50 | 약 6.02원 | 약 16,611건 |
| Claude Haiku 5.5, 입력 10만 토큰 이하 | 0.10 | 0.50 | 약 1.54원 | 약 64,935건 |

계산식: `(입력 토큰×입력 단가 + 출력 토큰×출력 단가) / 1,000,000 × 환율`. 질문당 토큰이 10배라면 비용도 약 10배, 같은 예산의 질문 수는 약 1/10입니다. OpenAI는 한 요청 입력 272,000토큰 초과 시 단가가 입력 0.20/출력 0.75로, Claude는 한 요청 입력 100,000토큰 초과 시 0.50/2.50으로 달라집니다. 이 앱의 참고 추정도 해당 구간을 구분합니다.

Gemini 무료 구간 안의 실제 청구는 0원일 수 있으나 앱은 무료 할당을 추적하지 않고 유료 표준 단가로 참고 추정합니다. 제공자가 토큰 사용량을 주지 않는 실패 요청 등은 비용 미산정으로 표시될 수 있습니다. 월 합계는 이 로컬 앱의 기록 범위이며 계정 전체 청구액이 아닙니다. `output/agent_cache.sqlite`를 삭제하면 캐시·사용 기록도 사라집니다.

**월 비용 상한·차단 기능은 없습니다.** 월 10만 원은 위 표의 비교용 예산일 뿐 설정값이 아닙니다. `LLM_DAILY_LIMIT`는 공란 또는 0이면 무제한이며 양수일 때만 일일 호출 상한입니다. 현재 달 호출 수·추정 원화 비용은 화면 상단과 `python cli.py --check`에서 참고합니다.

공식 단가 출처: [OpenAI 모델 가격](https://developers.openai.com/api/docs/models/gpt-6-luna), [Gemini API 가격](https://ai.google.dev/gemini-api/docs/pricing), [Claude Haiku 5.5 가격](https://platform.claude.com/docs/en/models/haiku-5-5/overview). 운영 시작 때 최신 가격·청구 내역을 다시 확인하세요.

## 보안·센터 적용

실제 `.env`는 센터 담당자가 로컬에서 입력하며 제출본은 빈 `.env.example`만 제공합니다. 유출되면 제공자에서 키를 폐기·재발급합니다. 사용자 질문·상위 장소 근거 일부가 선택한 LLM 제공자에게 전송될 수 있으므로 개인정보를 입력하지 않습니다. DLP 정책으로 외부 전송이 허용되지 않으면 `LLM_PROVIDER=none`으로 운영합니다. DB 기반 판정은 로컬에서 가능하며 날씨·지도도 차단 여부에 따라 각각 미확인·표 대체로 동작합니다.


## 브이월드 배경지도(선택)

1. [브이월드](https://www.vworld.kr/) 회원가입·로그인 후 오픈API → 인증키 신청/관리에서 지도의 활용 API(WMTS)를 선택합니다. 서비스명·이용 목적과 실제 접속 서비스 URL을 등록합니다.
2. `.env`의 `VWORLD_API_KEY=` 뒤에 키를 넣고 앱을 재시작합니다. `python setup_keys.py --key VWORLD_API_KEY`로 숨김 입력할 수도 있습니다. 코드·명령행 인수·문서에 키를 넣지 않습니다.
3. 등록 URL과 실제 운영 주소를 확인합니다. `http://localhost:18768`, `http://127.0.0.1:18768`, 폰의 `http://192.168.x.x:18768`은 다른 주소입니다. 운영 URL 변경 시 인증키 관리에서 허용 주소도 점검하세요. 필요한 경우 `VWORLD_SERVICE_URL`에 **등록된 실제 운영 URL**을 설정합니다. 허용되지 않은 주소를 가장하는 용도로 쓰지 않습니다. 센터 PC는 센터의 실제 서비스 주소·네트워크 정책으로 다시 확인해야 합니다.
4. 기본은 일반 백지도(white)이며 지도 위 ‘일반/위성’으로 바꿉니다. 위성은 Satellite+Hybrid(지명) 조합입니다. 키 없음·HTTP 오류·이미지가 아닌 응답·통신/디코딩 실패 시 기존 pydeck 기본 CARTO light 벡터 지도로 자동 전환합니다. CARTO에는 위성 전환이 없습니다. 두 공급자 모두 네트워크가 차단되면 배경 없이 장소 표시·목록을 사용합니다.

키는 Python 서버에만 두며, 브라우저에는 타일 이미지 바이트를 전달합니다. 서버는 등록 실제 서비스 URL(설정이 없으면 접속 origin)을 Referer로 보냅니다. 지도 하단에서 실제 배경 공급자·출처·전환 사유를 확인합니다. 키를 바꾼 뒤에는 서버 재시작이 필요합니다.

공식 WMTS 가이드: https://www.vworld.kr/dev/v4dv_wmtsguide_s001.do . 타일 형식은 `https://api.vworld.kr/req/wmts/1.0.0/{key}/{layer}/{z}/{y}/{x}.{확장자}`입니다. 일반 Base·white·midnight·Hybrid는 png, Satellite는 jpeg. 2026-11-09 공식 가이드와 실제 GetCapabilities에서 `Base/white/midnight/Satellite/Hybrid`를 확인했으며 **gray는 현재 레이어 목록에 없어 사용하지 않습니다**. Base/Satellite/Hybrid는 줌6~19, white/midnight는6~18입니다.



CARTO 검증 보완(2026-11-09, 사용자 지시 반영): Voyager 래스터 타일은 ‘API KEY REQUIRED’를 반환했지만, **기존 pydeck 기본 CARTO light 벡터 스타일은 키 없이 실제 정상 표시**됐습니다. `https://basemaps.cartocdn.com/gl/positron-gl-style/style.json` 및 `tiles.basemaps.cartocdn.com`의 벡터 타일 HTTP200, 브라우저 도로·지명·저작권 표시를 확인했습니다. 앱은 브이월드 → 이 기존 CARTO 벡터 배경 → OpenStreetMap 표준 타일 순으로 자동 대체합니다. CARTO 스타일/타일/글꼴 오류 또는12초 내 데이터 로딩 미확인 시 OSM으로 전환하고 지도 아래 실제 공급자와 출처를 표시합니다. 늦은 네트워크에서도 OSM으로 전환될 수 있습니다.

공식 CARTO 안내는 현재 외부 앱에 무료 키를 요구합니다([공식 안내](https://www.carto.com/basemaps/apikey/index.html)). 현재 벡터 성공이 장래의 키 없는 이용을 보장하지 않습니다. 다른 호스트·키를 이용한 인증 우회는 하지 않습니다. 키 없는 최종 대체는 `https://tile.openstreetmap.org/{z}/{x}/{y}.png`이고 ‘© OpenStreetMap 기여자’를 표시합니다. 브라우저 표준 캐시·Referer를 사용하고, 화면에 필요한 타일만 요청하며 일괄 수집/오프라인 다운로드는 구현하지 않습니다([OSM 타일 이용정책](https://operations.osmfoundation.org/policies/tiles/)). OSM도 외부 연결·사용량 정책에 따라 차단될 수 있으며 운영 보장은 없습니다.

### 장소 위치 검색
- 브이월드 검색 API 2.0: 기존 `VWORLD_API_KEY` 사용. 주소는 `https://api.vworld.kr/req/search`, 등록 도메인이 필요하면 기존 `VWORLD_SERVICE_URL` 설정.
- [한국관광공사 국문 관광정보 서비스](https://www.data.go.kr/data/15101578/openapi.do)는 무장애 여행 정보와 별도로 활용신청. 승인 후 `KTO_SERVICE_KEY`를 사용해 `https://apis.data.go.kr/B551011/KorService2/searchKeyword2`에 제주 지역 코드 39로 조회. 미승인·연결 실패 시 다음 위치 출처로 넘어갑니다.
