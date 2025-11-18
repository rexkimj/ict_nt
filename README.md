# ICT Trading Strategy with NautilusTrader

**기관의 기회 포착을 위한 ICT 트레이딩 전략** - Inner Circle Trader 개념을 구현한 알고리즘 트레이딩 시스템

## 📋 목차

- [개요](#개요)
- [ICT 트레이딩 원칙](#ict-트레이딩-원칙)
- [설치 방법](#설치-방법)
- [사용 방법](#사용-방법)
- [전략 구조](#전략-구조)
- [설정](#설정)
- [백테스팅](#백테스팅)
- [라이브 트레이딩](#라이브-트레이딩)

## 개요

이 프로젝트는 ICT(Inner Circle Trader) 트레이딩 전략을 NautilusTrader를 사용하여 구현한 알고리즘 트레이딩 시스템입니다. Bybit 거래소에서 암호화폐 선물 거래를 지원합니다.

### 주요 기능

- ✅ **Order Block 감지**: 기관의 매매 관심 구간 자동 식별
- ✅ **FVG/Imbalance 감지**: 가격 공백 및 불균형 감지
- ✅ **유동성 레벨 추적**: PDH/PDL, Swing High/Low, Equal Highs/Lows
- ✅ **Market Structure 분석**: BOS/CHoCH 감지 및 추세 판단
- ✅ **다중 타임프레임 분석**: HTF 추세 + LTF 진입점
- ✅ **리스크 관리**: 1-2% 리스크 원칙, RR 비율 검증
- ✅ **Bybit 연동**: 테스트넷 및 메인넷 지원

## ICT 트레이딩 원칙

### 진입 원칙

1. **Higher TimeFrame(HTF) 추세 확인**
   - 큰 타임프레임에서 전체 시장 방향 파악
   - Market Structure (BOS/CHoCH) 분석

2. **7가지 필수 요소 확인**
   - 유동성 (Liquidity)
   - 시장 구조 (Market Structure)
   - 오더 블록 (Order Block)
   - FVG/인밸런스 (Fair Value Gap)
   - 디스카운트/프리미엄 존
   - 타임프레임 일치
   - 시간대 (Kill Zone)

3. **유동성 수집 후 진입**
   - Liquidity Grab 확인
   - POI(Order Block, FVG) 테스트
   - Lower TimeFrame에서 진입 확인

### 청산 원칙

1. **Take Profit**: 유동성 레벨(PDH, PDL 등) 목표
2. **Stop Loss**: 유동성 수집 지점 뒤에 배치
3. **Risk-Reward**: 최소 1:2 비율 유지
4. **포지션 사이징**: 계좌의 1-2%만 리스크

## 설치 방법

### 1. 저장소 클론

```bash
git clone <repository-url>
cd ict_nt
```

### 2. Python 가상환경 생성

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 Bybit API 키를 입력:

```env
BYBIT_API_KEY=your_api_key_here
BYBIT_API_SECRET=your_api_secret_here
BYBIT_TESTNET=true
```

## 사용 방법

### 백테스팅

```bash
python backtest.py
```

### 라이브 트레이딩 (테스트넷)

```bash
# .env에서 BYBIT_TESTNET=true 확인
python live_trade.py
```

### 라이브 트레이딩 (메인넷)

```bash
# .env에서 BYBIT_TESTNET=false 설정
python live_trade.py
# "YES" 입력하여 확인
```

## 전략 구조

```
ict_nt/
├── config/
│   ├── bybit_config.json      # Bybit 거래소 설정
│   └── strategy_config.json   # 전략 파라미터 설정
├── indicators/
│   ├── order_block.py         # Order Block 감지기
│   ├── fvg.py                 # FVG/Imbalance 감지기
│   ├── liquidity.py           # 유동성 레벨 감지기
│   └── market_structure.py    # Market Structure 분석기
├── strategies/
│   └── ict_strategy.py        # 메인 ICT 전략
├── utils/
│   └── risk_manager.py        # 리스크 관리자
├── backtest.py                # 백테스팅 스크립트
├── live_trade.py              # 라이브 트레이딩 스크립트
└── README.md
```

## 설정

### 전략 설정 (config/strategy_config.json)

```json
{
  "instrument_id": "BTCUSDT-PERP.BYBIT",
  "htf_bar_type": "BTCUSDT-PERP.BYBIT-1-HOUR-LAST-EXTERNAL",
  "ltf_bar_type": "BTCUSDT-PERP.BYBIT-5-MINUTE-LAST-EXTERNAL",
  "risk_management": {
    "risk_per_trade_pct": 1.0,
    "min_rr_ratio": 2.0,
    "leverage": 5
  }
}
```

#### 주요 파라미터

- `instrument_id`: 거래할 상품 (예: BTCUSDT-PERP.BYBIT)
- `htf_bar_type`: Higher TimeFrame (추세 분석용)
- `ltf_bar_type`: Lower TimeFrame (진입점 포착용)
- `risk_per_trade_pct`: 거래당 리스크 비율 (기본 1%)
- `min_rr_ratio`: 최소 Risk-Reward 비율 (기본 2.0)
- `leverage`: 레버리지 (기본 5x)

### Order Block 설정

```json
"order_block_params": {
  "min_impulse_bars": 3,      // 임펄스 최소 캔들 수
  "min_impulse_size": 0.5,    // 임펄스 최소 크기 (%)
  "lookback_period": 50       // 탐색 기간
}
```

### FVG 설정

```json
"fvg_params": {
  "min_gap_size": 0.1,        // 최소 갭 크기 (%)
  "fill_threshold": 0.5,      // 채워짐 임계값
  "lookback_period": 100      // 탐색 기간
}
```

### 유동성 설정

```json
"liquidity_params": {
  "swing_lookback": 5,        // 스윙 포인트 lookback
  "equal_threshold": 0.1      // Equal High/Low 임계값 (%)
}
```

## 백테스팅

### 백테스트 실행

```bash
python backtest.py
```

### 백테스트 결과

백테스트는 다음 정보를 제공합니다:

- 초기/최종 잔고
- 총 PnL 및 수익률
- 거래 통계 (승률, 평균 수익/손실)
- Profit Factor
- 최대 Drawdown

### 백테스트 데이터

백테스트를 위해서는 historical data가 필요합니다. NautilusTrader의 데이터 카탈로그를 사용하거나 Bybit에서 데이터를 다운로드할 수 있습니다.

## 라이브 트레이딩

### ⚠️ 주의사항

1. **반드시 테스트넷에서 먼저 테스트하세요**
2. **작은 금액으로 시작하세요**
3. **리스크 관리 설정을 확인하세요**
4. **API 키를 안전하게 보관하세요**

### Bybit API 키 생성

1. [Bybit](https://www.bybit.com) 계정 생성
2. API Management에서 API 키 생성
3. 권한 설정:
   - Read: ✓
   - Trade: ✓
   - Wallet: ✓ (필요시)
4. IP 화이트리스트 설정 (권장)

### 테스트넷 사용

1. [Bybit Testnet](https://testnet.bybit.com) 계정 생성
2. 테스트넷 자금 받기
3. 테스트넷 API 키 생성
4. `.env`에서 `BYBIT_TESTNET=true` 설정

### 라이브 트레이딩 실행

```bash
python live_trade.py
```

프로그램은 다음을 수행합니다:

1. 설정 검증
2. Bybit 연결
3. 실시간 데이터 스트리밍
4. 진입/청산 시그널 감지
5. 자동 주문 실행

### 중지 방법

- `Enter` 키 입력 또는
- `Ctrl+C` (KeyboardInterrupt)

## ICT 전략 로직

### 롱 진입 조건

1. HTF가 **상승 추세** (Bullish Market Structure)
2. 가격이 **Discount 존** (레인지의 0.5 이하)
3. **Sell Side 유동성 수집** (Liquidity Grab)
4. **Bullish Order Block** 또는 **Bullish FVG** 존재
5. 가격이 POI 근처 (1% 이내)

### 숏 진입 조건

1. HTF가 **하락 추세** (Bearish Market Structure)
2. 가격이 **Premium 존** (레인지의 0.5 이상)
3. **Buy Side 유동성 수집** (Liquidity Grab)
4. **Bearish Order Block** 또는 **Bearish FVG** 존재
5. 가격이 POI 근처 (1% 이내)

### Stop Loss 배치

- 유동성 수집된 레벨 뒤에 배치
- 0.1% 버퍼 추가
- Order Block이 있으면 그 뒤에 배치

### Take Profit 목표

1. 우선: 가까운 유동성 레벨 (PDH, PDL, Swing High/Low)
2. 차선: Risk-Reward 비율 기반 (최소 2:1)

## 성능 최적화

### 메모리 관리

- 최대 500개 바 저장
- 오래된 데이터 자동 삭제

### 계산 효율성

- numpy 배열 사용
- 중복 계산 최소화
- 필요한 인디케이터만 계산

## 문제 해결

### API 연결 오류

```
ERROR: Failed to connect to Bybit
```

**해결:**
- API 키 확인
- 인터넷 연결 확인
- 테스트넷/메인넷 URL 확인

### 데이터 부족 오류

```
ERROR: Not enough bars for analysis
```

**해결:**
- 더 오래 실행하여 데이터 수집
- lookback_period 줄이기

### 주문 실패

```
ERROR: Order rejected
```

**해결:**
- 계좌 잔고 확인
- 레버리지 설정 확인
- 최소 주문 크기 확인

## 리스크 고지

⚠️ **경고**: 암호화폐 트레이딩은 높은 리스크를 수반합니다.

- 투자 원금 전액을 잃을 수 있습니다
- 과거 성과가 미래 성과를 보장하지 않습니다
- 레버리지는 손실을 증폭시킬 수 있습니다
- 투자 책임은 본인에게 있습니다

## 라이선스

MIT License

## 기여

기여는 환영합니다! Pull Request를 제출해주세요.

## 참고 자료

- [NautilusTrader 문서](http://nautilustrader.io/)
- [NautilusTrader GitHub](https://github.com/nautechsystems/nautilus_trader)
- [Bybit API 문서](https://bybit-exchange.github.io/docs/)
- ICT (Inner Circle Trader) 개념

## 지원

문제가 있으시면 GitHub Issues에 등록해주세요.

---

**Happy Trading! 📈**
