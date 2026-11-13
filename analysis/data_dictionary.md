# 데이터 사전

수다백단 10일 분석 과제(`docs/데이터분석과제.md`)에서 쓰는 표의 컬럼 설명.

- 원본: `data/` (앱이 저장하는 JSON, git 제외)
- 만드는 방법: `python -m analysis.prep` → `python -m analysis.metrics`
- 결과 위치: `analysis/out/` (대화 원문이 들어 있어 git 제외)
- 모든 CSV는 UTF-8(BOM)이라 엑셀에서 바로 열린다. 참/거짓은 `True` / `False`, 값이 없으면 빈칸.

## 공통 컬럼

| 컬럼 | 형식 | 뜻 | 예 |
|---|---|---|---|
| `session_id` | 문자 | 대화 1회의 ID. 시작 시각 `YYYYMMDD-HHMMSS` | `20261106-140559` |
| `date` | 날짜 | 대화한 날 | `2026-11-06` |
| `day_n` | 정수 | 11/4부터 센 달력 날짜. 11/4 = 0, 11/5 = 1, …, 11/18 = 14 | `2` |
| `work_day` | 정수 | 근무 일차 1~10. 주말·기간 밖은 빈칸 | `2` |
| `mode` | 문자 | 대화 모드: `daily` 일상, `business` 비즈니스, `verb` 동사 집중, `pattern` 표현·문형 | `daily` |
| `prompt_version` | 문자 | 앱 기록 방식 버전. 11/4는 빈칸(개선 전), 11/5부터 `2026-11-05` | `2026-11-05` |

## sessions.csv — 대화 1회 = 1행

| 컬럼 | 형식 | 뜻 | 계산 |
|---|---|---|---|
| `started` | 시각 | 대화 시작 시각 | 원본 그대로 |
| `style` | 문자 | 그날 AI 대화 방식 (하루 하나로 고정). `ai_story` AI가 자기 이야기, `ai_disagree` 살짝 반대, `ai_secret` 비밀 숨기기, `role_swap` 역할 바꾸기, `user_first` 내가 이끌기, `goal_roleplay` 목표 달성 역할극 | 원본 그대로 |
| `topic` | 문자 | 대화 주제 | 원본 그대로 |
| `minutes` | 실수 | 대화 시간(분) | 초 ÷ 60, 소수 1자리 |
| `finished` | 참/거짓 | 대화를 정상 종료했는지 | 원본 그대로 |
| `model` | 문자 | 판정한 Gemini 모델. 11/4는 빈칸 | 원본 그대로 |
| `n_user_msgs` | 정수 | 내 메시지 수 | |
| `voice_ratio` | 비율 | 내 메시지 중 음성 입력 비율 | 음성 메시지 ÷ 내 메시지 |
| `n_turns` | 정수 | AI 판정 개수 (내 메시지마다 1개여야 정상) | |
| `turns_match` | 참/거짓 | `n_user_msgs == n_turns` | 거짓이면 경고 |

## messages.csv — 내 메시지 1개 = 1행

| 컬럼 | 형식 | 뜻 | 계산 |
|---|---|---|---|
| `msg_idx` | 정수 | 대화 안에서 내 메시지 순번 (1부터) | |
| `ts` | 시각 | 보낸 시각 | |
| `text` | 문자 | 내가 보낸 문장 원문 | |
| `via_voice` | 참/거짓 | 마이크로 말해서 보냈는지 | |
| `n_words` | 정수 | 영어 단어 수 | 정규식 `[A-Za-z]+('[A-Za-z]+)*`. don't = 1단어, 숫자·한글은 세지 않음 |
| `has_korean` | 참/거짓 | 한글이 한 글자라도 섞였는지 | `[가-힣]` 포함 여부 |
| `asked_help_ko` | 참/거짓 | 한국어 도움 카드가 붙었는지 (한국어로 물어봄) | `help_ko` 존재 |
| `corrected` | 참/거짓 | 교정 카드가 붙었는지 | `correction` 존재. **AI 판정** |
| `user_asked_question` | 참/거짓 | 내가 영어로 질문했는지 | **AI 판정**. 짝 판정이 없으면 빈칸 |
| `user_led` | 참/거짓 | 묻지 않았는데 새 화제를 꺼내거나 이야기를 했는지 | **AI 판정**. 짝 판정이 없으면 빈칸 |
| `n_mistakes` | 정수 | 이 메시지에서 AI가 기록한 실수 수 (품질 점검 전) | **AI 판정** |

## mistakes.csv — AI가 기록한 실수 1건 = 1행

| 컬럼 | 형식 | 뜻 | 계산 |
|---|---|---|---|
| `style` | 문자 | 그날 대화 방식 | sessions와 같음 |
| `msg_idx` | 정수 | 실수가 기록된 내 메시지 순번 | |
| `user_text` | 문자 | 그 메시지 원문 | |
| `key` | 문자 | AI가 붙인 실수 이름표. **넓게 묶이는 문제가 있어 분석에 쓰지 않음** (비교용) | 원본 그대로 |
| `area` | 문자 | AI가 붙인 실수 종류. 11/5부터 `grammar` / `vocabulary` / `expression` / `spelling` | 원본 그대로. 11/4는 표기가 섞임 |
| `original` | 문자 | AI가 적은 "틀린 말" | |
| `native` | 문자 | AI가 적은 "맞는 말" | |
| `voice_sensitive` | 참/거짓 | 음성 인식 탓일 수 있는 실수 | AI 판정 |
| `not_in_text` | 참/거짓 | **말하지 않은 실수 기록**: `original`의 단어 80% 이상이 `user_text`에 없음 | 소문자·문장부호 제거 후 비교 |
| `dup_in_msg` | 참/거짓 | **한 메시지 안 중복**: 같은 `original`이 이 메시지에서 이미 기록됨 | |
| `no_change` | 참/거짓 | **고칠 것 없는 기록**: `original`과 `native`가 같음 (대소문자·문장부호 무시). 매핑표에 넣지 않음 | 6일차 추가 |
| `valid` | 참/거짓 | 분석에 쓰는 기록인지 | `not_in_text`, `dup_in_msg`, `no_change`가 모두 거짓 |
| `mistake_id` | 문자 | **사람이 붙인 실수 ID**. 같은 학습 포인트면 같은 ID | `mistake_map.csv`에서 (`original`, `native`)로 찾음. 없으면 빈칸 |
| `occurrence_n` | 정수 | 이 ID가 몇 번째로 나왔는지 (1 = 처음) | 유효하고 ID가 있는 기록만, 날짜·대화·메시지 순 |
| `repeat` | 참/거짓 | **재발**: 같은 ID가 이전 날짜에 나온 적 있는지 | 같은 날 여러 번은 재발로 세지 않음 |

## practice.csv — 숨은 연습 대상 × 날짜 = 1행

앱은 날마다 자주 틀린 실수 최대 3개를 골라, 대화에서 은근히 다시 쓰게 유도한다(숨은 연습).

| 컬럼 | 형식 | 뜻 | 계산 |
|---|---|---|---|
| `key` | 문자 | 그날 연습 대상 (**AI 이름표** 기준) | `data/plans/{date}.json`의 `targets` |
| `n_sessions` | 정수 | 그날 대화 수 | |
| `used_correctly` | 참/거짓 | 그날 대화에서 AI가 "맞게 썼다"고 판정했는지 | `targets_used_correctly`에 포함 |
| `mistaken_again` | 참/거짓 | 그날 같은 이름표로 또 틀렸는지 | |

## mistake_map.csv — 사람이 고치는 매핑표 (`analysis/`, git 제외)

| 컬럼 | 뜻 |
|---|---|
| `mistake_id` | 사람이 붙이는 ID. 빈칸이면 아직 안 붙인 것 |
| `original`, `native` | AI가 적은 틀린 말 / 맞는 말. 둘을 묶어 찾는다 (대소문자·문장부호 무시) |
| `first_date` | 이 (틀린 말, 맞는 말)이 처음 나온 날 |

**ID 붙이는 기준**
- 같은 학습 포인트면 같은 ID. 영어 snake_case.
- 문법은 규칙 이름: `past_irregular_verb`(heared, drinked), `question_word_order`, `present_for_habit`("i usually watched").
- 표현은 맞는 표현 이름: `get_much_sleep`, `need_time`, `send_an_email`.
- `prep.py`가 처음 보는 실수를 빈칸으로 덧붙이므로 근무일마다 빈칸만 채운다. 이미 있는 ID를 먼저 찾아보고, 없을 때만 새로 만든다.

## daily_metrics.csv — 날짜 1개 = 1행

| 컬럼 | 뜻 | 계산 | 갈래 |
|---|---|---|---|
| `n_sessions`, `minutes` | 대화 수, 총 시간(분) | | 공통 |
| `n_msgs` | 내 메시지 수 | | 공통 |
| `avg_words`, `median_words` | 메시지당 영어 단어 수 평균, 중앙값 | `n_words` | B1 |
| `ttr150` | 어휘 다양성 | 그날 내 메시지를 이어 붙인 앞 150단어 중 서로 다른 단어 비율. 150단어 미만이면 빈칸 | B1 |
| `korean_rate` | 한국어 섞임률 | `has_korean` 비율 | B2 |
| `help_rate` | 한국어 도움 요청률 | `asked_help_ko` 비율 | B2 |
| `corrected_rate` | 교정받은 비율 | `corrected` 비율 | B |
| `mistakes_per_msg` | 메시지당 실수 수 | 유효한 실수 ÷ 메시지 | B |
| `lead_rate` | 주도율 | `user_led` 또는 `user_asked_question`이 참인 비율 | B3 |
| `question_rate` | 질문 비율 | `user_asked_question` 비율 | B3 |
| `voice_rate` | 음성 입력 비율 | `via_voice` 비율 | C1 |
| `n_mistakes` | 유효한 실수 수 | `valid` 참 | A |
| `n_repeat`, `repeat_rate` | 재발한 실수 수, 비율 | `repeat` 참인 수 ÷ ID 있는 유효한 실수 | A1 |

## 중간 점검 표 (`python -m analysis.interim`)

| 파일 | 1행 | 내용 |
|---|---|---|
| `by_mode.csv`, `by_style.csv` | 모드 / 대화 스타일 1개 | daily_metrics와 같은 지표. **11/5부터만** (AI 판정 기준선과 같은 조건). 3분 미만 대화는 `n_sessions`에서 빼고 메시지는 남김. `dates` = 그 그룹이 나온 날짜 |
| `recurrence.csv` | 날짜 1개 | `n_ids` 그날까지 나온 실수 ID 수, `n_multi_day` 그중 2일 이상 나온 ID 수, `cum_recurrence` 누적 재발률, `daily_repeat`·`daily_n` 그날 재발 비율과 표본 수, `ci_low`~`ci_high` 그날 재발 비율의 95% 구간 (Wilson) |
| `figures/trend.png` | | 핵심 지표 6개 추이 (숫자만 있어 git에 올림) |

## 전반부 실수 ID 목록 (`analysis/first_half_ids.csv`, `python -m analysis.balance`)

A 분석(후반부 재등장 비율)의 분모. 11/12에 **한 번 고정**하고 다시 실행해도 덮어쓰지 않는다 (`--force`로만 다시 만듦). 후반부에 매핑을 고쳐도 분모가 흔들리지 않게 하려는 것. ID·날짜·횟수만 있어 git에 올린다.

| 컬럼 | 뜻 |
|---|---|
| `mistake_id` | 11/4~11/11 유효한 실수의 ID |
| `n_days`, `n_records` | 전반부에 나온 날 수, 기록 수 |
| `first_date`, `last_date` | 전반부에서 처음·마지막으로 나온 날 |

## A 분석 표 (`python -m analysis.mistake_repeat`, 7일차)

| 파일 | 1행 | 내용 |
|---|---|---|
| `reappearance.csv` | 묶음 1개 (`all` / `multi_day` / `single_day`) | 전반부 고정 ID(`n` = 분모) 중 11/12 이후 유효 기록이 있는 ID 수 `k`, 비율 `rate`, 95% 구간 `ci_low`~`ci_high` (Wilson), 다시 나온 `ids`. `multi_day` = 전반부에 2일 이상 나온 ID |
| `repeat_by_type.csv` | 영역 또는 문법 묶음 1개 | `level` = `area`(문법·어휘·표현·철자) / `grammar`(질문 구조·시제·동사 형태·관사·전치사·연결어·기타). `n_ids`, 2일 이상 나온 `n_multi_day`와 `multi_share`, 기록 수 `n_records` |
| `survival.csv` | 실수 ID 1개 | `time` = 처음 나온 근무일부터 다음에 다시 나온 근무일까지 근무일 수 (`event`=1), 다시 안 나왔으면 마지막 근무일까지 (`event`=0, 관측 중단). 마지막 날 처음 나온 ID는 뺌. `area`, `grammar_group` |
| `figures/a_reappearance.png`, `a_by_type.png`, `a_survival.png` | | 재등장 비율, 유형별 2일 이상 비율, Kaplan–Meier 곡선 (숫자만 있어 git에 올림) |

- **영역**: AI가 붙인 `area`를 정규화(`어휘 선택`→어휘, `phrasal_flow`→표현)한 다수결. 이름이 `_spelling`으로 끝나면 철자, `GRAMMAR_GROUP`에 있으면 문법.
- **근무일**: 대화가 있었던 날만 센다 (주말은 건너뜀). 11/4도 포함.

## 품질 경고 (warnings.txt)

| 경고 | 조건 |
|---|---|
| 턴 수 불일치 | `turns_match` 거짓 |
| 3분 미만 대화 | `minutes` < 3 |
| 끝나지 않은 대화 | `finished` 거짓 |
| 말하지 않은 실수 기록 | `not_in_text` 참 |
| 한 메시지 안 중복 실수 | `dup_in_msg` 참 |
| 고칠 것 없는 실수 기록 | `no_change` 참 |
| ID 없는 실수 N건 | `mistake_map.csv`에 빈칸 있음 |
