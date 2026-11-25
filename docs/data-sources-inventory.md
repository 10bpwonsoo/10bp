# 수집 대상 · 공급처 목록

`python -m marketpulse.collector inventory --md docs/data-sources-inventory.md` 로 다시 만든다(설정에서 생성 — 손으로 고치지 않는다).

- 계열 213개(묶음 사이에 겹치는 것 포함) · 그중 Yahoo 가 첫 공급처인 계열 175개 = 서로 다른 Yahoo 심볼 136개
- Yahoo 심볼 가운데 설정된 대체 경로가 있는 것 63개 · 없는 것 73개(막히면 결측)
- '공개 시각' 은 그 봉이 기준 시각(07:30 KST)에 쓸 수 있게 되는 때(archive/pit.py). 대체 공급처는 자기 규칙을 따른다.

## base (60)

| 계열 | 첫 공급처 | 심볼 | 시장 | 공개 시각 | 막히면 |
|---|---|---|---|---|---|
| KOSPI | yahoo | `^KS11` | KR | 봉 시각 +7h | stooq:^kospi |
| KOSPI200 | yahoo | `^KS200` | KR | 봉 시각 +7h | 없음(결측) |
| KOSDAQ | yahoo | `^KQ11` | KR | 봉 시각 +7h | 없음(결측) |
| SPX | yahoo | `^GSPC` | US | 봉 시각 +7h | stooq:^spx |
| NDX | yahoo | `^NDX` | US | 봉 시각 +7h | stooq:^ndq |
| RUT | yahoo | `^RUT` | US | 봉 시각 +7h | 없음(결측) |
| HSCEI | yahoo | `^HSCE` | HK | 봉 시각 +7h | 없음(결측) |
| HANGSENG | yahoo | `^HSI` | HK | 봉 시각 +7h | 없음(결측) |
| HSTECH | yahoo | `3033.HK` | HK | 봉 시각 +7h | 없음(결측) |
| SHCOMP | yahoo | `000001.SS` | CN | 봉 시각 +7h | 없음(결측) |
| SZCOMP | yahoo | `399001.SZ` | CN | 봉 시각 +7h | 없음(결측) |
| CSI300_ETF | yahoo | `510300.SS` | CN | 봉 시각 +7h | 없음(결측) |
| CHINEXT | yahoo | `159915.SZ` | CN | 봉 시각 +7h | 없음(결측) |
| NIKKEI | yahoo | `^N225` | JP | 봉 시각 +7h | stooq:^nkx |
| SX5E | yahoo | `^STOXX50E` | EU | 봉 시각 +7h | 없음(결측) |
| XLK | yahoo | `XLK` | US | 봉 시각 +7h | stooq:xlk.us |
| XLE | yahoo | `XLE` | US | 봉 시각 +7h | stooq:xle.us |
| XLF | yahoo | `XLF` | US | 봉 시각 +7h | stooq:xlf.us |
| XLU | yahoo | `XLU` | US | 봉 시각 +7h | stooq:xlu.us |
| XLY | yahoo | `XLY` | US | 봉 시각 +7h | stooq:xly.us |
| SOXX | yahoo | `SOXX` | US | 봉 시각 +7h | stooq:soxx.us |
| ITA | yahoo | `ITA` | US | 봉 시각 +7h | stooq:ita.us |
| JETS | yahoo | `JETS` | US | 봉 시각 +7h | stooq:jets.us |
| KRX_SEMI | krx | `반도체` | OTHER | — | 없음(결측) |
| US2Y | fred | `DGS2` | FRED | 관측일 다음 평일 22:00Z | yahoo:2YY=F |
| US10Y | fred | `DGS10` | FRED | 관측일 다음 평일 22:00Z | yahoo:^TNX |
| US30Y | fred | `DGS30` | FRED | 관측일 다음 평일 22:00Z | yahoo:^TYX |
| KR3Y | krx | `국고채 3년` | OTHER | — | 없음(결측) |
| KR10Y | krx | `국고채 10년` | OTHER | — | 없음(결측) |
| US5Y | fred | `DGS5` | FRED | 관측일 다음 평일 22:00Z | yahoo:^FVX |
| BE10Y | fred | `T10YIE` | FRED | 관측일 다음 평일 22:00Z | 없음(결측) |
| BE5Y | fred | `T5YIE` | FRED | 관측일 다음 평일 22:00Z | 없음(결측) |
| TIPS10Y | fred | `DFII10` | FRED | 관측일 다음 평일 22:00Z | 없음(결측) |
| TIPS5Y | fred | `DFII5` | FRED | 관측일 다음 평일 22:00Z | 없음(결측) |
| USDKRW | yahoo | `KRW=X` | FX | 봉 시각 +24h | github:daily.csv |
| DXY | yahoo | `DX-Y.NYB` | US | 그 거래일 뉴욕 17:00 | stooq:^dxy |
| USDJPY | yahoo | `JPY=X` | FX | 봉 시각 +24h | stooq:usdjpy, github:daily.csv |
| EURUSD | yahoo | `EURUSD=X` | FX | 봉 시각 +24h | stooq:eurusd, github:daily.csv |
| USDCNH | yahoo | `CNY=X` | FX | 봉 시각 +24h | github:daily.csv |
| WTI | yahoo | `CL=F` | US | 그 거래일 뉴욕 17:00 | fred:DCOILWTICO, github:wti-daily.csv |
| BRENT | yahoo | `BZ=F` | US | 그 거래일 뉴욕 17:00 | fred:DCOILBRENTEU, github:brent-daily.csv |
| GOLD | yahoo | `GC=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| COPPER | yahoo | `HG=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| NATGAS | yahoo | `NG=F` | US | 그 거래일 뉴욕 17:00 | fred:DHHNGSP, github:daily.csv |
| VIX | yahoo | `^VIX` | US | 봉 시각 +14h | fred:VIXCLS, github:vix-daily.csv |
| MOVE | yahoo | `^MOVE` | US | 봉 시각 +7h | 없음(결측) |
| VKOSPI | krx | `코스피 200 변동성지수` | OTHER | — | 없음(결측) |
| US_HY_OAS | fred | `BAMLH0A0HYM2` | FRED | 관측일 다음 평일 22:00Z | 없음(결측) |
| KR_FOREIGN_NET | krx | `외국인` | OTHER | — | 없음(결측) |
| KR_INSTITUTION_NET | krx | `기관합계` | OTHER | — | 없음(결측) |
| KR_RETAIL_NET | krx | `개인` | OTHER | — | 없음(결측) |
| KR_TRADING_VALUE | krx | `코스피` | OTHER | — | 없음(결측) |
| KOSPI_ADV_RATIO | — | `—` | — | — | 없음(결측) |
| KOSPI_NHNL | — | `—` | — | — | 없음(결측) |
| SPX_ADV_RATIO | — | `—` | — | — | 없음(결측) |
| CYC_DEF | derived | `ratio(XLY,XLU)` | DERIVED | 재료 계열 중 늦은 쪽 | 없음(결측) |
| CURVE_2S10S | derived | `spread(US10Y,US2Y)` | DERIVED | 재료 계열 중 늦은 쪽 | 없음(결측) |
| COPPER_GOLD | derived | `ratio(COPPER,GOLD)` | DERIVED | 재료 계열 중 늦은 쪽 | 없음(결측) |
| VIX_RV_SPX | derived | `vol_premium(VIX,SPX)` | DERIVED | 재료 계열 중 늦은 쪽 | 없음(결측) |
| VKOSPI_RV_KOSPI | derived | `vol_premium(VKOSPI,KOSPI)` | DERIVED | 재료 계열 중 늦은 쪽 | 없음(결측) |

## universe (101)

| 계열 | 첫 공급처 | 심볼 | 시장 | 공개 시각 | 막히면 |
|---|---|---|---|---|---|
| SAMSUNG | yahoo | `005930.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SKHYNIX | yahoo | `000660.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HANMI_SEMI | yahoo | `042700.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SAMSUNG_EM | yahoo | `009150.KS` | KR | 봉 시각 +7h | 없음(결측) |
| LG_ENSOL | yahoo | `373220.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SAMSUNG_SDI | yahoo | `006400.KS` | KR | 봉 시각 +7h | 없음(결측) |
| LGCHEM | yahoo | `051910.KS` | KR | 봉 시각 +7h | 없음(결측) |
| LOTTE_CHEM | yahoo | `011170.KS` | KR | 봉 시각 +7h | 없음(결측) |
| KUMHO_PETRO | yahoo | `011780.KS` | KR | 봉 시각 +7h | 없음(결측) |
| POSCO | yahoo | `005490.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HYUNDAI_STEEL | yahoo | `004020.KS` | KR | 봉 시각 +7h | 없음(결측) |
| KOREA_ZINC | yahoo | `010130.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HYUNDAI_MOTOR | yahoo | `005380.KS` | KR | 봉 시각 +7h | 없음(결측) |
| KIA | yahoo | `000270.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HYUNDAI_MOBIS | yahoo | `012330.KS` | KR | 봉 시각 +7h | 없음(결측) |
| KOREAN_AIR | yahoo | `003490.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HMM | yahoo | `011200.KS` | KR | 봉 시각 +7h | 없음(결측) |
| PAN_OCEAN | yahoo | `028670.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HD_HHI | yahoo | `329180.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HANWHA_OCEAN | yahoo | `042660.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HANWHA_AERO | yahoo | `012450.KS` | KR | 봉 시각 +7h | 없음(결측) |
| LIG_NEX1 | yahoo | `079550.KS` | KR | 봉 시각 +7h | 없음(결측) |
| LS_ELECTRIC | yahoo | `010120.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HD_ELECTRIC | yahoo | `267260.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HYOSUNG_HEAVY | yahoo | `298040.KS` | KR | 봉 시각 +7h | 없음(결측) |
| DOOSAN_ENER | yahoo | `034020.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SOIL | yahoo | `010950.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SK_INNOVATION | yahoo | `096770.KS` | KR | 봉 시각 +7h | 없음(결측) |
| KEPCO | yahoo | `015760.KS` | KR | 봉 시각 +7h | 없음(결측) |
| NAVER | yahoo | `035420.KS` | KR | 봉 시각 +7h | 없음(결측) |
| KAKAO | yahoo | `035720.KS` | KR | 봉 시각 +7h | 없음(결측) |
| KB | yahoo | `105560.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SHINHAN | yahoo | `055550.KS` | KR | 봉 시각 +7h | 없음(결측) |
| CELLTRION | yahoo | `068270.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SAMSUNG_BIO | yahoo | `207940.KS` | KR | 봉 시각 +7h | 없음(결측) |
| CJ_CJ | yahoo | `097950.KS` | KR | 봉 시각 +7h | 없음(결측) |
| GASOLINE | yahoo | `RB=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| DIESEL_PROXY | yahoo | `HO=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| JET_FUEL_PROXY | yahoo | `HO=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| COAL_PROXY | csv | `COAL_PROXY` | OTHER | — | 없음(결측) |
| URANIUM_ETF | yahoo | `URA` | US | 봉 시각 +7h | 없음(결측) |
| ALUMINUM | yahoo | `ALI=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| SILVER | yahoo | `SI=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| PLATINUM | yahoo | `PL=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| IRON_ORE | yahoo | `TIO=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| STEEL_ETF | yahoo | `SLX` | US | 봉 시각 +7h | 없음(결측) |
| LITHIUM_ETF | yahoo | `LIT` | US | 봉 시각 +7h | 없음(결측) |
| METALS_ETF | yahoo | `PICK` | US | 봉 시각 +7h | 없음(결측) |
| NICKEL_PROXY | csv | `NICKEL_PROXY` | OTHER | — | 없음(결측) |
| ZINC_PROXY | csv | `ZINC_PROXY` | OTHER | — | 없음(결측) |
| NAPHTHA_PROXY | csv | `NAPHTHA_PROXY` | OTHER | — | 없음(결측) |
| CORN | yahoo | `ZC=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| WHEAT | yahoo | `ZW=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| SOYBEAN | yahoo | `ZS=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| SUGAR | yahoo | `SB=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| COFFEE | yahoo | `KC=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| COTTON | yahoo | `CT=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| DRY_BULK_ETF | yahoo | `BDRY` | US | 봉 시각 +7h | 없음(결측) |
| SCFI | csv | `SCFI` | OTHER | — | 없음(결측) |
| DRAM_SPOT | csv | `DRAM_SPOT` | OTHER | — | 없음(결측) |
| DDR5_SPOT | csv | `DDR5_SPOT` | OTHER | — | 없음(결측) |
| NAND_SPOT | csv | `NAND_SPOT` | OTHER | — | 없음(결측) |
| DXI | csv | `DXI` | OTHER | — | 없음(결측) |
| HBM3E_CONTRACT | csv | `HBM3E_CONTRACT` | OTHER | — | 없음(결측) |
| HBM4_CONTRACT | csv | `HBM4_CONTRACT` | OTHER | — | 없음(결측) |
| SOX | yahoo | `^SOX` | US | 봉 시각 +7h | 없음(결측) |
| SMH | yahoo | `SMH` | US | 봉 시각 +7h | 없음(결측) |
| NVDA | yahoo | `NVDA` | US | 봉 시각 +7h | 없음(결측) |
| MU | yahoo | `MU` | US | 봉 시각 +7h | 없음(결측) |
| TSM | yahoo | `TSM` | US | 봉 시각 +7h | 없음(결측) |
| AMD | yahoo | `AMD` | US | 봉 시각 +7h | 없음(결측) |
| AVGO | yahoo | `AVGO` | US | 봉 시각 +7h | 없음(결측) |
| ASML | yahoo | `ASML` | US | 봉 시각 +7h | 없음(결측) |
| AMAT | yahoo | `AMAT` | US | 봉 시각 +7h | 없음(결측) |
| LRCX | yahoo | `LRCX` | US | 봉 시각 +7h | 없음(결측) |
| TEL | yahoo | `8035.T` | JP | 봉 시각 +7h | 없음(결측) |
| CSI300 | yahoo | `000300.SS` | CN | 봉 시각 +7h | yahoo:ASHR |
| HSI | yahoo | `^HSI` | HK | 봉 시각 +7h | 없음(결측) |
| CHINA_PMI | csv | `CHINA_PMI` | OTHER | — | 없음(결측) |
| BRENT | yahoo | `BZ=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| COPPER | yahoo | `HG=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| DXY | yahoo | `DX-Y.NYB` | US | 그 거래일 뉴욕 17:00 | stooq:^dxy |
| GOLD | yahoo | `GC=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| ITA | yahoo | `ITA` | US | 봉 시각 +7h | stooq:ita.us |
| JETS | yahoo | `JETS` | US | 봉 시각 +7h | stooq:jets.us |
| KOSPI | yahoo | `^KS11` | KR | 봉 시각 +7h | stooq:^kospi |
| KR10Y | — | `—` | — | — | 없음(결측) |
| MOVE | yahoo | `^MOVE` | US | 봉 시각 +7h | 없음(결측) |
| NATGAS | yahoo | `NG=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| NDX | yahoo | `^NDX` | US | 봉 시각 +7h | stooq:^ndq |
| SPX | yahoo | `^GSPC` | US | 봉 시각 +7h | stooq:^spx |
| US10Y | yahoo | `^TNX` | US | 봉 시각 +7h | 없음(결측) |
| US2Y | yahoo | `2YY=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| USDCNH | yahoo | `CNY=X` | FX | 봉 시각 +24h | 없음(결측) |
| USDJPY | yahoo | `JPY=X` | FX | 봉 시각 +24h | stooq:usdjpy |
| USDKRW | yahoo | `KRW=X` | FX | 봉 시각 +24h | 없음(결측) |
| VIX | yahoo | `^VIX` | US | 봉 시각 +14h | 없음(결측) |
| WTI | yahoo | `CL=F` | US | 그 거래일 뉴욕 17:00 | 없음(결측) |
| XLE | yahoo | `XLE` | US | 봉 시각 +7h | stooq:xle.us |
| XLF | yahoo | `XLF` | US | 봉 시각 +7h | stooq:xlf.us |
| XLU | yahoo | `XLU` | US | 봉 시각 +7h | stooq:xlu.us |

## basket (52)

| 계열 | 첫 공급처 | 심볼 | 시장 | 공개 시각 | 막히면 |
|---|---|---|---|---|---|
| NVDA | yahoo | `NVDA` | US | 봉 시각 +7h | stooq:nvda.us, twelvedata:NVDA |
| AMD | yahoo | `AMD` | US | 봉 시각 +7h | stooq:amd.us, twelvedata:AMD |
| AVGO | yahoo | `AVGO` | US | 봉 시각 +7h | stooq:avgo.us, twelvedata:AVGO |
| TSM | yahoo | `TSM` | US | 봉 시각 +7h | stooq:tsm.us, twelvedata:TSM |
| MRVL | yahoo | `MRVL` | US | 봉 시각 +7h | stooq:mrvl.us, twelvedata:MRVL |
| ARM | yahoo | `ARM` | US | 봉 시각 +7h | stooq:arm.us, twelvedata:ARM |
| MU | yahoo | `MU` | US | 봉 시각 +7h | stooq:mu.us, twelvedata:MU |
| SNDK | yahoo | `SNDK` | US | 봉 시각 +7h | stooq:sndk.us, twelvedata:SNDK |
| SKHYNIX | yahoo | `000660.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SAMSUNG | yahoo | `005930.KS` | KR | 봉 시각 +7h | 없음(결측) |
| GFS | yahoo | `GFS` | US | 봉 시각 +7h | stooq:gfs.us, twelvedata:GFS |
| UMC | yahoo | `UMC` | US | 봉 시각 +7h | stooq:umc.us, twelvedata:UMC |
| ASML | yahoo | `ASML` | US | 봉 시각 +7h | stooq:asml.us, twelvedata:ASML |
| AMAT | yahoo | `AMAT` | US | 봉 시각 +7h | stooq:amat.us, twelvedata:AMAT |
| LRCX | yahoo | `LRCX` | US | 봉 시각 +7h | stooq:lrcx.us, twelvedata:LRCX |
| KLAC | yahoo | `KLAC` | US | 봉 시각 +7h | stooq:klac.us, twelvedata:KLAC |
| TEL | yahoo | `8035.T` | JP | 봉 시각 +7h | 없음(결측) |
| HANMI_SEMI | yahoo | `042700.KS` | KR | 봉 시각 +7h | 없음(결측) |
| AMKR | yahoo | `AMKR` | US | 봉 시각 +7h | stooq:amkr.us, twelvedata:AMKR |
| BESI | yahoo | `BESI.AS` | EU | 봉 시각 +7h | 없음(결측) |
| ANET | yahoo | `ANET` | US | 봉 시각 +7h | stooq:anet.us, twelvedata:ANET |
| CIEN | yahoo | `CIEN` | US | 봉 시각 +7h | stooq:cien.us, twelvedata:CIEN |
| CRDO | yahoo | `CRDO` | US | 봉 시각 +7h | stooq:crdo.us, twelvedata:CRDO |
| MSFT | yahoo | `MSFT` | US | 봉 시각 +7h | stooq:msft.us, twelvedata:MSFT |
| GOOGL | yahoo | `GOOGL` | US | 봉 시각 +7h | stooq:googl.us, twelvedata:GOOGL |
| AMZN | yahoo | `AMZN` | US | 봉 시각 +7h | stooq:amzn.us, twelvedata:AMZN |
| META | yahoo | `META` | US | 봉 시각 +7h | stooq:meta.us, twelvedata:META |
| ORCL | yahoo | `ORCL` | US | 봉 시각 +7h | stooq:orcl.us, twelvedata:ORCL |
| VRT | yahoo | `VRT` | US | 봉 시각 +7h | stooq:vrt.us, twelvedata:VRT |
| ETN | yahoo | `ETN` | US | 봉 시각 +7h | stooq:etn.us, twelvedata:ETN |
| PWR | yahoo | `PWR` | US | 봉 시각 +7h | stooq:pwr.us, twelvedata:PWR |
| EQIX | yahoo | `EQIX` | US | 봉 시각 +7h | stooq:eqix.us, twelvedata:EQIX |
| DLR | yahoo | `DLR` | US | 봉 시각 +7h | stooq:dlr.us, twelvedata:DLR |
| DELL | yahoo | `DELL` | US | 봉 시각 +7h | stooq:dell.us, twelvedata:DELL |
| SMCI | yahoo | `SMCI` | US | 봉 시각 +7h | stooq:smci.us, twelvedata:SMCI |
| VST | yahoo | `VST` | US | 봉 시각 +7h | stooq:vst.us, twelvedata:VST |
| CEG | yahoo | `CEG` | US | 봉 시각 +7h | stooq:ceg.us, twelvedata:CEG |
| GEV | yahoo | `GEV` | US | 봉 시각 +7h | stooq:gev.us, twelvedata:GEV |
| NRG | yahoo | `NRG` | US | 봉 시각 +7h | stooq:nrg.us, twelvedata:NRG |
| HD_ELECTRIC | yahoo | `267260.KS` | KR | 봉 시각 +7h | 없음(결측) |
| HYOSUNG_HEAVY | yahoo | `298040.KS` | KR | 봉 시각 +7h | 없음(결측) |
| LS_ELECTRIC | yahoo | `010120.KS` | KR | 봉 시각 +7h | 없음(결측) |
| DOOSAN_ENER | yahoo | `034020.KS` | KR | 봉 시각 +7h | 없음(결측) |
| NAVER | yahoo | `035420.KS` | KR | 봉 시각 +7h | 없음(결측) |
| SAMSUNG_EM | yahoo | `009150.KS` | KR | 봉 시각 +7h | 없음(결측) |
| PLTR | yahoo | `PLTR` | US | 봉 시각 +7h | stooq:pltr.us, twelvedata:PLTR |
| NOW | yahoo | `NOW` | US | 봉 시각 +7h | stooq:now.us, twelvedata:NOW |
| CRM | yahoo | `CRM` | US | 봉 시각 +7h | stooq:crm.us, twelvedata:CRM |
| SNOW | yahoo | `SNOW` | US | 봉 시각 +7h | stooq:snow.us, twelvedata:SNOW |
| DDOG | yahoo | `DDOG` | US | 봉 시각 +7h | stooq:ddog.us, twelvedata:DDOG |
| NET | yahoo | `NET` | US | 봉 시각 +7h | stooq:net.us, twelvedata:NET |
| APP | yahoo | `APP` | US | 봉 시각 +7h | stooq:app.us, twelvedata:APP |

## 공급처

- **yahoo** — Yahoo Finance 차트 API(키 없음)
- **stooq** — Stooq CSV(키 없음)
- **fred** — FRED(FRED_API_KEY)
- **twelvedata** — Twelve Data(TWELVEDATA_API_KEY)
- **krx** — KRX 정보데이터시스템(키 없음)
- **github** — 공개 GitHub CSV 미러(1~수 영업일 늦음)
- **csv** — 저장소의 수기 파일
