# **Strategic Quantitative Architecture and Regulatory Framework for the claudey-tr Algorithmic Trading System in the Indian Currency Derivatives Market**

The transformation of the Indian financial landscape between 2024 and 2026 has been defined by a decisive shift from an unregulated open API era to a structured, traceable, and institutionalized algorithmic ecosystem.1 For the development of the claudey-tr bot, a system designed to navigate the nuances of the Exchange-Traded Currency Derivatives (ETCD) segment via Angel One’s SmartAPI, this evolution necessitates a dual-focus architecture. The system must not only achieve alpha through sophisticated quantitative strategies—such as Statistical Arbitrage and Mean Reversion—but also maintain a robust compliance posture that aligns with the Securities and Exchange Board of India (SEBI) 2026 mandate.3 This report provides a comprehensive analysis of the regulatory requirements, technical integration protocols, market microstructure characteristics, and strategic quantitative designs required to deploy a top-tier algorithmic bot in this new regime.

## **Regulatory Architecture and the 2026 Compliance Mandate**

The SEBI framework for retail algorithmic trading, fully enforceable by April 1, 2026, represents a fundamental shift in the liability and traceability of automated orders.2 The core objective is the elimination of grey-box or unmonitored API usage, replaced by a system where every automated instruction is categorized, tagged, and logged.5 Under the new framework, the traditional independence of third-party algo providers has been curtailed in favor of a broker-centric accountability model where brokers are recognized as the principals for all activity originating from their APIs, while algo developers or SaaS platforms act as agents.5 This structural change implies that the claudey-tr bot, if offered to third parties, would require the developer to be formally empanelled with the broker and the exchange.7

The regulatory framework introduces a clear implementation timeline, often referred to as the glide path, which began in late 2024 and culminates in full mandatory compliance on April 1, 2026\.2 This timeline was designed to allow market participants, specifically retail-focused brokers like Angel One, to upgrade their technical infrastructure to support mandatory static IP whitelisting, OAuth-based two-factor authentication (2FA), and unique strategy identification.3

| Milestone | Deadline | Requirement |
| :---- | :---- | :---- |
| Optional Go-Live | October 1, 2025 | Compliant brokers may begin registering retail algo products.8 |
| Milestone 1 | October 31, 2025 | Mandatory application for registration of at least one retail algo product.8 |
| Milestone 2 | November 30, 2025 | Completion of registration for all existing retail algorithmic strategies.8 |
| Milestone 3 | January 3, 2026 | Participation in full-scale mock trading sessions for all algo-enabled platforms.8 |
| Restriction Window | January 5, 2026 | Non-compliant brokers barred from onboarding new retail API clients.2 |
| Full Mandatory Enforcement | April 1, 2026 | Every algorithmic order must carry an exchange-assigned ID.2 |

### **Strategy Identification and the NNF Tagging Protocol**

A critical component of the 2026 regulations is the assignment of a unique Exchange-assigned Algo-ID to every automated strategy.3 Previously, retail API orders were often indistinguishable from manual orders unless the broker voluntarily tagged them. Post-2026, the 13th digit of the Neat-to-Neat (NNF) packet is standardized to identify the origin of the order.6 This level of traceability allows regulators to audit exactly which algorithm generated a specific set of orders if unusual market activity is detected, effectively creating a license plate for every trade.5

For claudey-tr, the classification depends on the Threshold Order Per Second (TOPS), which is initially set at 10 orders per second (OPS) per exchange/segment.4 Strategies falling below this threshold are classified as regular API usage and do not require individual registration of the logic with the exchange, instead utilizing a generic ID provided by the broker.4 However, any strategy exceeding this 10 OPS limit—typically associated with high-frequency scalping or market-making—is subject to mandatory registration, rigorous pre-live testing, and specific risk-management audits.4

### **Access Security and Static IP Whitelisting**

To prevent unauthorized access and the sharing of API keys, SEBI mandates that all API orders originate from a registered primary static IP address.3 For tech-savvy investors who maintain their own trading logic, like the claudey-tr bot, the client is responsible for providing this static IP to the broker.4 Angel One allows for the registration of a secondary static IP for redundancy, ensuring that connectivity is maintained if the primary server fails.4 A static IP can only be mapped to a single client, with the only exception being family accounts (self, spouse, and dependent children) where formal written consent and 2FA validation are provided.4

Furthermore, the framework necessitates a daily 2FA process. The historical practice of using persistent refresh tokens to keep a bot running for weeks is no longer permitted.8 All API sessions are subject to a mandatory daily logout before the next trading session begins, typically at midnight, requiring claudey-tr to re-authenticate every morning before the 09:00 AM market open.6

## **Technical Integration and SmartAPI Infrastructure**

Integration with Angel One's SmartAPI requires a sophisticated middleware layer to manage rate limits, handle session re-authentication, and implement regulatory-compliant risk checks.4 The SmartAPI ecosystem provides diverse endpoints, ranging from historical data to real-time order execution, each governed by specific constraints.15

| API Endpoint | Category | Rate Limit (Sec/Min/Hour) | Strategic Utility |
| :---- | :---- | :---- | :---- |
| /rest/auth/.../loginByPassword | Auth | 1 / NA / NA | Morning initialization.15 |
| /rest/secure/.../placeOrder | Trading | 20 / 500 / 1000 | Core execution.15 |
| /rest/secure/.../modifyOrder | Trading | 20 / 500 / 1000 | Dynamic limit adjustments.15 |
| /rest/secure/.../getLtpData | Market Data | 10 / 500 / 5000 | Signal generation.15 |
| /rest/secure/.../getCandleData | Historical | 3 / 180 / 5000 | Regime detection.15 |
| /rest/secure/.../createRule | GTT | 10 / 500 / 5000 | Long-term stop losses.15 |

### **Rate Limiting and Traffic Shaping**

While the SEBI 10 OPS threshold is a regulatory ceiling, Angel One’s broker-level rate limits are slightly higher in some categories to accommodate bursts of activity.9 To avoid being throttled or blocked, claudey-tr must implement a local rate-limiting mechanism such as a Leaky Bucket or Token Bucket algorithm.16 The Leaky Bucket algorithm is particularly suitable for API management as it smooths out bursts of requests, processing them at a steady, fixed rate regardless of how quickly they enter the queue.16

If the claudey-tr logic generates 15 signals in a single second, the local leaky bucket would buffer these requests, releasing them at a constant rate (e.g., 9 OPS) to stay safely below the regulatory 10 OPS limit while ensuring the broker's system is not overwhelmed.16 This queuing behavior is essential because exceeding the threshold without proper registration results in immediate order rejection by the broker’s Risk Management System (RMS).4

### **Order Type Constraints and MPP Implementation**

Perhaps the most disruptive change for intraday algorithmic traders is the strict prohibition of Market Orders and Immediate-or-Cancel (IOC) orders in the ETCD segment.4 These orders were traditionally used to ensure instant execution, but they often led to significant slippage during periods of low liquidity.4

In the 2026 framework, any market order instruction is automatically converted by the broker into a Market Price Protection (MPP) order.13 An MPP order functions similarly to a market order but incorporates a price protection band, typically around 1-2% from the last traded price (LTP).13 If the market moves too rapidly and the order cannot be filled within this band, the remainder is either cancelled or converted into a limit order at the protection price.13 For claudey-tr, this necessitates a shift to Smart Limit orders, where the bot continuously polls the best bid and ask and places limit orders exactly at the opposite side's best price, adjusting them every few seconds if they remain unfilled.20

## **Market Microstructure of Indian Currency Derivatives**

The Indian ETCD market is characterized by the dominance of the USDINR pair and the heavy involvement of the Reserve Bank of India (RBI) as the primary liquidity provider and stabilizer.22 Understanding this microstructure is vital for the claudey-tr bot to avoid trading against "the invisible hand" of the central bank.24

### **Liquidity Profiles and Contract Specifications**

The National Stock Exchange (NSE) offers four primary INR pairs: USDINR, EURINR, GBPINR, and JPYINR.27 While USDINR accounts for the vast majority of volume, the other pairs offer diverse opportunities for volatility-based strategies.27

| Feature | USDINR | EURINR | GBPINR | JPYINR |
| :---- | :---- | :---- | :---- | :---- |
| Lot Size | $1,000 | €1,000 | £1,000 | ¥100,000 |
| Underlying | 1 USD in INR | 1 EUR in INR | 1 GBP in INR | 100 JPY in INR |
| Tick Size | ₹0.0025 | ₹0.0025 | ₹0.0025 | ₹0.0025 |
| Pip Value | ₹2.50 | ₹2.50 | ₹2.50 | ₹2.50 |
| Margin | \~2.5% | \~2.5% | \~3.0% | \~4.2% |
| Liquidity | Extreme | Moderate | High | Low |

The contract specifications across these pairs are similar, but the margins vary based on the volatility of the underlying.27 USDINR's low margin of approximately 2.5% allows for significant leverage, which claudey-tr can exploit for mean-reversion strategies, provided strict stop-loss protocols are in place.27

### **The RBI Reference Rate and Polling Window**

A unique feature of the Indian currency market is the daily fixing of the RBI Reference Rate.30 Every trading day between 11:30 AM and 12:30 PM, the RBI polls a randomly selected set of contributing banks for their bid-ask quotes on USDINR.31 The resulting simple average becomes the official benchmark used for the final settlement of all currency futures and options.29

For an algorithmic trader, this window is a period of heightened structural risk.31 Research indicates that volatility often spikes during the polling hour as banks and institutions adjust their spot and futures positions to align with the expected benchmark.33 The claudey-tr bot should be programmed to either reduce its position size or pause aggressive entries during this specific one-hour window to avoid being caught in the artificial volatility of the polling process.31

### **Intervention Mechanics and Signal Detection**

The RBI intervenes in the forex market to smooth out disruptive volatility, not necessarily to target a specific level, although they have been observed defending critical zones such as the 83.20 or 90.40 levels in USDINR.22 These interventions typically involve direct dollar sales through state-run banks or operations in the forward and Non-Deliverable Forward (NDF) markets.25

Detection of RBI intervention by claudey-tr can be achieved through three primary quantitative indicators:

1. **Abnormal Volume Spikes:** A sudden surge in volume (typically \>35% above the 5-day moving average) occurring near a multi-month high or low, signaling institutional intervention to cap the move.34  
2. **Order Book Stagnation:** Periods where large "iceberg" orders appear on one side of the book, keeping the price pegged within a 1-2 pip range despite high global dollar volatility.22  
3. **Cross-Market Divergence:** A widening gap between the NSE USDINR futures price and the offshore NDF price, indicating that the RBI is actively suppressing the domestic move while the global market remains bearish.25

## **Quantitative Algorithmic Strategies for the ETCD Market**

To maximize risk-adjusted returns, claudey-tr will utilize three modular strategy engines: Mean Reversion, Statistical Arbitrage, and Grid Trading. Each module is designed to perform in specific market regimes.36

### **Module 1: Mean Reversion (Z-Score Based)**

Mean reversion is the most successful strategy for USDINR due to the RBI's volatility-suppression mandate.25 The strategy assumes that extreme deviations from the historical average are temporary.36 The claudey-tr Mean Reversion module uses a rolling 20-period Z-score to identify entry points.39

The Z-score is mathematically represented as:

![][image1]  
**Operational Logic:**

* **Long Signal:** Triggered when ![][image2], suggesting the currency is oversold relative to its 20-period mean.36  
* **Short Signal:** Triggered when ![][image3], suggesting the currency is overbought.36  
* **Exit Logic:** Positions are closed when the Z-score reverts to ![][image4] (the mean) or hits a time-based exit if the reversion does not occur within ![][image5] periods.36

While mean reversion has a high win rate (typically 60-75%), it carries the risk of "the big loss" during a major structural breakout where the RBI allows the rupee to find a new, significantly different equilibrium.36

### **Module 2: Statistical Arbitrage (Pairs Trading)**

Statistical Arbitrage (StatArb) exploits the breakdown of historical correlations between two assets.37 In the Indian ETCD market, claudey-tr can monitor the spread between highly correlated instruments.37

**Primary Pairs for claudey-tr:**

* **NSE USDINR Near Month vs. BSE USDINR Near Month:** Capturing temporary pricing discrepancies between the two largest exchanges.  
* **GBPINR vs. EURINR:** Exploiting the stable relationship between the two major European currencies as traded in India.

The relationship is modeled using the Spread:

![][image6]  
Where ![][image7] is the hedge ratio calculated via rolling Ordinary Least Squares (OLS) regression.37 The bot enters a long-short position when the spread deviates more than 2 standard deviations from its own mean, profiting as the relationship converges.37

### **Module 3: Grid Trading for Consolidation**

Grid trading is designed for "ranging" markets where the price oscillates within a defined horizontal channel.36 The bot places a series of buy and sell limit orders at pre-set intervals above and below the current price.36

| Grid Parameter | Setting for USDINR | Reasoning |
| :---- | :---- | :---- |
| **Grid Range** | ₹0.40 | RBI often holds the rupee within a 40-50 paise band.25 |
| **Step Size** | ₹0.0050 | Two ticks; captures micro-fluctuations.36 |
| **Position Sizing** | Fixed Lot | Ensures equal weight across the grid.36 |
| **Safety Zone** | 0.5% | Hard stop if range breaks.36 |

The primary advantage of grid trading is that it does not require a directional forecast.36 However, in a strong trending market, the bot will accumulate massive losses on one side of the grid. To mitigate this, claudey-tr incorporates a "Volatility Filter" that disables the grid if the Average True Range (ATR) exceeds a 10-day historical threshold.36

## **Risk Management and Compliance Controls**

Capital preservation is mandated not only by the bot's profitability requirements but by SEBI's regulatory standards.1 The claudey-tr system must incorporate multi-layered risk management protocols.8

### **Position Limits and Exposure Monitoring**

SEBI and NSE enforce strict position limits at the client level to prevent systemic risk.43 The bot must monitor its "Gross Open Position" in real-time to ensure it does not exceed the following thresholds:

| Currency Pair | Retail Position Limit |
| :---- | :---- |
| USDINR | Higher of 6% of Total Open Interest or $20 million.43 |
| EURINR | Higher of 6% of Total Open Interest or €10 million.43 |
| GBPINR | Higher of 6% of Total Open Interest or £10 million.43 |
| JPYINR | Higher of 6% of Total Open Interest or ¥400 million.43 |

Breaching these limits results in immediate intervention by the broker's RMS and can lead to account suspension.12

### **Slippage Modeling and Execution Quality**

Slippage is the difference between the expected price of a trade and the price at which the trade is actually executed.45 In the ETCD market, where claudey-tr is forced to use limit orders, slippage appears as "opportunity cost" (missed trades) or "execution lag".45

The total slippage ![][image8] for claudey-tr is modeled as:

![][image9]  
Where:

* ![][image10] \= The minimum latency-induced slippage.  
* ![][image11] \= Price move caused by the order's size relative to current volume.  
* ![][image12] \= Expected price movement during the execution window.  
* ![][image13] \= The cost of crossing the bid-ask spread.45

By modeling these factors, the claudey-tr execution engine can decide whether to "pay the spread" or wait for a more favorable limit fill based on the current volatility regime.20

### **The "Kill Switch" and Operational Safeguards**

As per NSE circular NSE/INVG/67858, every algorithmic system must have a "kill switch" to immediately halt runaway executions.6 The claudey-tr kill switch is triggered by:

1. **Consecutive Rejections:** If 5 orders are rejected by the broker RMS in a row.  
2. **OPS Violation:** If the local rate limiter detects more than 10 signals per second.4  
3. **Maximum Daily Loss:** If the MTM loss reaches 2% of total capital.  
4. **Heartbeat Loss:** If the connection to Angel One’s websocket is interrupted for more than 5 seconds.42

## **PRD (Product Requirements Document) for claudey-tr v2.0**

This PRD outlines the technical and functional specifications required for the claudey-tr bot to operate successfully in the 2026 Indian currency derivatives market.

### **1\. Functional Requirements**

* **FR1: Automated Authentication:** The system must complete TOTP-based 2FA every morning at 08:50 AM IST to initialize the session for the 09:00 AM market open.6  
* **FR2: Strategy Switching:** The bot must detect market regimes (Trending vs. Ranging) using the ADX indicator. If ADX \< 20, the Grid Trading module is activated; if ADX \> 25, the bot switches to Mean Reversion with a tighter trend-following filter.36  
* **FR3: Smart Limit Execution:** Because market orders are converted to MPP, the bot must implement a "Price Chasing" limit order logic. If a limit order is not filled within 3 seconds, it must be automatically modified to the current best bid/ask, provided it is within the user's maximum slippage tolerance.20  
* **FR4: Historical Replay Engine:** A local matching engine must be maintained for realistic backtesting, simulating slippage and order book depth based on historical L2/L3 data.48

### **2\. Regulatory and Compliance Requirements**

* **RR1: Static IP Binding:** All order placement requests must originate from the registered primary static IP. The bot must perform a self-check of its public IP before sending any order to prevent rejection.4  
* **RR2: Algo-ID Tagging:** Every order sent to the SmartAPI must include the tag parameter corresponding to the exchange-assigned Strategy ID for claudey-tr.5  
* **RR3: Audit Logging:** A 5-year, non-editable audit trail must be maintained in a local database, capturing every heartbeat, order modification, and strategy decision for potential regulatory inspection.3  
* **RR4: Mandatory Daily Logout:** The system must automatically close all open websocket connections and clear local session tokens at 11:59 PM IST daily.8

### **3\. Technical Specifications and Performance Targets**

| Metric | Target Specification | Reasoning |
| :---- | :---- | :---- |
| **Signal Latency** | \< 50ms | Essential for capturing tick deviations.36 |
| **Max OPS** | 9 Orders / Second | Safe buffer below the 10 OPS regulatory limit.4 |
| **System Uptime** | 99.9% (Market Hours) | Prevents "abandoned" positions during outages.47 |
| **Drawdown Limit** | 10% (Strategy Level) | Capital preservation standard.36 |
| **Recovery Factor** | \> 1.5 | Ensures strategy can recover from losses.41 |

## **Conclusion and Strategic Roadmap**

The deployment of the claudey-tr algorithmic bot in the 2026 landscape requires a sophisticated blend of quantitative edge and regulatory vigilance. The transition from an "open" to a "regulated" API environment does not diminish the opportunities for retail alpha; rather, it standardizes the playing field by removing low-quality, high-risk bots that previously caused market instability.1

For the claudey-tr system, the roadmap involves a phased rollout starting with a low-frequency mean reversion module (under 10 OPS) to minimize registration hurdles while scaling capital.4 As the bot proves its resilience and moves into higher frequency scalping or cross-exchange arbitrage, the architecture is already prepared for the more rigorous requirements of HFT registration, including VAPT audits and unique strategy IDs.3

The future of currency derivatives trading in India will be dominated by those who can navigate the "managed volatility" of the RBI while maintaining a perfect compliance record.11 By adhering to the PRD outlined in this report, the claudey-tr bot is positioned to become a benchmark for professional retail algorithmic trading in the Indian forex market.1

#### **Works cited**

1. Algorithmic Trading in India (2026): SEBI Framework and Career ..., accessed on March 27, 2026, [https://www.quantinsti.com/articles/algorithmic-trading-india/](https://www.quantinsti.com/articles/algorithmic-trading-india/)  
2. SEBI Algo Trading Regulations 2026: A Guide for Retail Investors \- Liquide Blog, accessed on March 27, 2026, [https://blog.liquide.life/sebi-algo-trading-regulations-2026/](https://blog.liquide.life/sebi-algo-trading-regulations-2026/)  
3. SEBI Algo Trading Rules April 2026: What Every Retail Trader in India Must Know Before the Deadline \- Fintrens Blog, accessed on March 27, 2026, [https://blogs.fintrens.com/sebi-algo-trading-rules-april-2026-what-every-retail-trader-in-india-must-know-before-the-deadline/](https://blogs.fintrens.com/sebi-algo-trading-rules-april-2026-what-every-retail-trader-in-india-must-know-before-the-deadline/)  
4. What's Changing in Angel One's SmartAPI Access from April 1, 2026, accessed on March 27, 2026, [https://www.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026](https://www.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026)  
5. SEBI Algo Trading Rules 2026: What Every Retail Trader Must Know Before April, accessed on March 27, 2026, [https://www.sahi.com/blogs/sebi-algo-trading-rules-2026-what-every-retail-trader-must-know-before-april](https://www.sahi.com/blogs/sebi-algo-trading-rules-2026-what-every-retail-trader-must-know-before-april)  
6. NSE Retail Algo Trading Guidelines (2025): What Retail Traders Need to Know \- Medium, accessed on March 27, 2026, [https://medium.com/@social\_62250/nse-retail-algo-trading-guidelines-2025-what-retail-traders-need-to-know-06454fe3c118](https://medium.com/@social_62250/nse-retail-algo-trading-guidelines-2025-what-retail-traders-need-to-know-06454fe3c118)  
7. Is SEBI Banning Algo Trading in India in 2026? | AlgoTest Blog, accessed on March 27, 2026, [https://algotest.in/blog/is-sebi-banning-algo-trading-in-india/](https://algotest.in/blog/is-sebi-banning-algo-trading-in-india/)  
8. Understanding SEBI's New Algo Trading Regulations for Retail Investors \- AlgoBulls, accessed on March 27, 2026, [https://algobulls.com/blog/industry-insights-and-updates/sebi-new-algotrading-regulations-for-retail-investors](https://algobulls.com/blog/industry-insights-and-updates/sebi-new-algotrading-regulations-for-retail-investors)  
9. NSE Mandates Retail Algo Strategy Registration in New August 2025 Guidelines, accessed on March 27, 2026, [https://www.angelone.in/news/market-updates/nse-mandates-retail-algo-strategy-registration-in-new-august-2025-guidelines](https://www.angelone.in/news/market-updates/nse-mandates-retail-algo-strategy-registration-in-new-august-2025-guidelines)  
10. NSE Retail Algo Trading Rules \- Rupeezy, accessed on March 27, 2026, [https://rupeezy.in/blog/nse-retail-algo-trading-rules](https://rupeezy.in/blog/nse-retail-algo-trading-rules)  
11. Algorithmic Trading New Rules by SEBI & NSE: Retail Participation with Safety and Structure \- ICICIdirect, accessed on March 27, 2026, [https://www.icicidirect.com/futures-and-options/articles/algorithmic-trading-new-rules-by-sebi-nse-retail-participation-with-safety-and-structure](https://www.icicidirect.com/futures-and-options/articles/algorithmic-trading-new-rules-by-sebi-nse-retail-participation-with-safety-and-structure)  
12. SEBIs New NSE Rules on Retail Algo Trading for Traders, Platforms, and Brokers, accessed on March 27, 2026, [https://www.truedata.in/blog/new-nse-rules-on-retail-algo-trading-what-traders-platforms-and-brokers-need-to-know](https://www.truedata.in/blog/new-nse-rules-on-retail-algo-trading-what-traders-platforms-and-brokers-need-to-know)  
13. SEBI's new algo trading rules kick in on April 1\. Here is what changes for you. \- FYERS, accessed on March 27, 2026, [https://fyers.in/community/blogs-gdppin8d/post/sebi-s-new-algo-trading-rules-kick-in-on-april-1-here-is-what-changes-Yew3vdG4CgoXk1q](https://fyers.in/community/blogs-gdppin8d/post/sebi-s-new-algo-trading-rules-kick-in-on-april-1-here-is-what-changes-Yew3vdG4CgoXk1q)  
14. Static IP based API keys now live \- Old flow still supported temporarily | SmartAPI Forum, accessed on March 27, 2026, [https://smartapi.angelone.in/smartapi/forum/topic/5352/static-ip-based-api-keys-now-live-old-flow-still-supported-temporarily](https://smartapi.angelone.in/smartapi/forum/topic/5352/static-ip-based-api-keys-now-live-old-flow-still-supported-temporarily)  
15. Changes in API Rate Limit | SmartAPI Forum, accessed on March 27, 2026, [https://smartapi.angelone.in/smartapi/forum/topic/4387/changes-in-api-rate-limit](https://smartapi.angelone.in/smartapi/forum/topic/4387/changes-in-api-rate-limit)  
16. Leaky Bucket Algorithm With Implementations in Python and Golang \- Medium, accessed on March 27, 2026, [https://medium.com/@mojimich2015/leaky-bucket-algorithm-with-implementations-in-python-and-golang-ae963b477c43](https://medium.com/@mojimich2015/leaky-bucket-algorithm-with-implementations-in-python-and-golang-ae963b477c43)  
17. Token Bucket vs Leaky Bucket: Pick the Perfect Rate Limiting Algorithm \- API7.ai, accessed on March 27, 2026, [https://api7.ai/blog/token-bucket-vs-leaky-best-rate-limiting-algorithm](https://api7.ai/blog/token-bucket-vs-leaky-best-rate-limiting-algorithm)  
18. Leaky bucket algorithm: Throttling for \#APIs – \#Python Solution \- APILama, accessed on March 27, 2026, [https://apilama.com/2018/05/21/leaky-bucket-algorithm-throttling-apis/](https://apilama.com/2018/05/21/leaky-bucket-algorithm-throttling-apis/)  
19. Order Types \- Documentation, accessed on March 27, 2026, [https://www.ibkrguides.com/traderworkstation/order-types.htm](https://www.ibkrguides.com/traderworkstation/order-types.htm)  
20. Smart Post-Only Orders \- Crypto.com Help Center, accessed on March 27, 2026, [https://help.crypto.com/en/articles/11693040-smart-post-only-orders](https://help.crypto.com/en/articles/11693040-smart-post-only-orders)  
21. Why Limit Orders Sometimes Execute at a Different Price | RMoney Guide, accessed on March 27, 2026, [https://rmoneyindia.com/support/policies-and-compliances/limit-order-execution-different-price/](https://rmoneyindia.com/support/policies-and-compliances/limit-order-execution-different-price/)  
22. USDINR Technical Analysis: RBI's intervention paused the selloff. Key levels in focus now., accessed on March 27, 2026, [https://id.tradingview.com/news/forexlive:b96b3b44d094b:0-usdinr-technical-analysis-rbi-s-intervention-paused-the-selloff-key-levels-in-focus-now/](https://id.tradingview.com/news/forexlive:b96b3b44d094b:0-usdinr-technical-analysis-rbi-s-intervention-paused-the-selloff-key-levels-in-focus-now/)  
23. Intervention in foreign exchange markets: the approach of the Reserve Bank of India, accessed on March 27, 2026, [https://www.bis.org/publ/bppdf/bispap73l.pdf](https://www.bis.org/publ/bppdf/bispap73l.pdf)  
24. RBI Governor: Forex Interventions Will Focus On Smoothening Disruptive Volatility, accessed on March 27, 2026, [https://www.youtube.com/watch?v=TxbjQVVXn9I](https://www.youtube.com/watch?v=TxbjQVVXn9I)  
25. RBI's costly experiments with the currency \- Ideas for India, accessed on March 27, 2026, [https://www.ideasforindia.in/topics/money-finance/rbi-s-costly-experiments-with-the-currency](https://www.ideasforindia.in/topics/money-finance/rbi-s-costly-experiments-with-the-currency)  
26. Due to RBI intervention, the Indian Rupee rises significantly against the US Dollar in trading, accessed on March 27, 2026, [https://www.vtmarkets.com/live-updates/due-to-rbi-intervention-the-indian-rupee-rises-significantly-against-the-us-dollar-in-trading/](https://www.vtmarkets.com/live-updates/due-to-rbi-intervention-the-indian-rupee-rises-significantly-against-the-us-dollar-in-trading/)  
27. Trading EUR INR, GBP INR & JPY INR: Contracts & TA Strategies \- Zerodha, accessed on March 27, 2026, [https://zerodha.com/varsity/chapter/eur-gbp-and-jpy/](https://zerodha.com/varsity/chapter/eur-gbp-and-jpy/)  
28. Currency Derivatives Market Watch & Trading \- NSE India, accessed on March 27, 2026, [https://www.nseindia.com/market-data/currency-derivatives](https://www.nseindia.com/market-data/currency-derivatives)  
29. USD INR Futures & Options Trading: Contract Specs & Mechanics \- Zerodha, accessed on March 27, 2026, [https://zerodha.com/varsity/chapter/the-usd-inr-pair/](https://zerodha.com/varsity/chapter/the-usd-inr-pair/)  
30. RBI Reference Rates Statistics \- NSE India, accessed on March 27, 2026, [https://www.nseindia.com/report-detail/rbi-reference-rate-statistics](https://www.nseindia.com/report-detail/rbi-reference-rate-statistics)  
31. Reference Rates and Impacts of Events | Finschool \- 5paisa, accessed on March 27, 2026, [https://www.5paisa.com/finschool/course/currency-commodity-government-securities-course/reference-rates-and-impacts-of-events/](https://www.5paisa.com/finschool/course/currency-commodity-government-securities-course/reference-rates-and-impacts-of-events/)  
32. Currency Rates & Events: RBI Fixing & Economic Impact on Forex \- Zerodha, accessed on March 27, 2026, [https://zerodha.com/varsity/chapter/reference-rates-impact-of-events/](https://zerodha.com/varsity/chapter/reference-rates-impact-of-events/)  
33. Information transmission in the foreign exchange market: evidence from India, accessed on March 27, 2026, [https://store.ectap.ro/articole/1897.pdf](https://store.ectap.ro/articole/1897.pdf)  
34. USD/INR Exchange Rate Tumbles As Indian Rupee Defends RBI's Strategic Intervention | Bitcoinworld on Binance Square, accessed on March 27, 2026, [https://www.binance.com/en-IN/square/post/298567201568882](https://www.binance.com/en-IN/square/post/298567201568882)  
35. Research Paper on Algorithmic Breakout Detection Via Volume Spike Analysis in Options Trading \- IJRASET, accessed on March 27, 2026, [https://www.ijraset.com/research-paper/algorithmic-breakout-detection-via-volume-spike-analysis-in-options-trading](https://www.ijraset.com/research-paper/algorithmic-breakout-detection-via-volume-spike-analysis-in-options-trading)  
36. Forex Algorithmic Trading Strategies That Actually Work in 2026 \- NYCServers, accessed on March 27, 2026, [https://newyorkcityservers.com/blog/forex-algorithmic-trading-strategies](https://newyorkcityservers.com/blog/forex-algorithmic-trading-strategies)  
37. Best Algo Trading Strategy 2026 \- Rupeezy, accessed on March 27, 2026, [https://rupeezy.in/blog/best-algo-trading-strategy](https://rupeezy.in/blog/best-algo-trading-strategy)  
38. 12 Best Algorithmic Trading Strategies to Know in 2026 \- Snap Innovations, accessed on March 27, 2026, [https://snapinnovations.com/best-algo-trading-strategy/](https://snapinnovations.com/best-algo-trading-strategy/)  
39. Mean Reversion Trading in Forex: Strategy Guide for 2026 \- NYCServers, accessed on March 27, 2026, [https://newyorkcityservers.com/blog/mean-reversion-trading-forex](https://newyorkcityservers.com/blog/mean-reversion-trading-forex)  
40. Algorithmic Trading Strategies: Guide to Automated Trading in 2026 | ThinkMarkets, accessed on March 27, 2026, [https://www.thinkmarkets.com/en/trading-academy/forex/algorithmic-trading-strategies-guide-to-automated-trading-in-2026/](https://www.thinkmarkets.com/en/trading-academy/forex/algorithmic-trading-strategies-guide-to-automated-trading-in-2026/)  
41. Found a simple mean reversion setup with 70% win rate but only invested 20% of the time : r/algotrading \- Reddit, accessed on March 27, 2026, [https://www.reddit.com/r/algotrading/comments/1rjvxjy/found\_a\_simple\_mean\_reversion\_setup\_with\_70\_win/](https://www.reddit.com/r/algotrading/comments/1rjvxjy/found_a_simple_mean_reversion_setup_with_70_win/)  
42. NATIONAL STOCK EXCHANGE OF INDIA LIMITED, accessed on March 27, 2026, [https://nsearchives.nseindia.com/content/circulars/FAOP21794.pdf](https://nsearchives.nseindia.com/content/circulars/FAOP21794.pdf)  
43. Position Limits | NSE Clearing Limited, accessed on March 27, 2026, [https://www.nseclearing.in/risk-management/currency-derivatives/position-limits](https://www.nseclearing.in/risk-management/currency-derivatives/position-limits)  
44. Currency Derivatives \- Position Limits \- NSE India, accessed on March 27, 2026, [https://www.nseindia.com/static/products-services/currency-derivatives-position-limits](https://www.nseindia.com/static/products-services/currency-derivatives-position-limits)  
45. Slippage Modelling \- Stephen Diehl, accessed on March 27, 2026, [https://www.stephendiehl.com/posts/slippage/](https://www.stephendiehl.com/posts/slippage/)  
46. Equity Derivatives, Futures and Options Trading System \- NSE India, accessed on March 27, 2026, [https://www.nseindia.com/static/products-services/equity-derivatives-trading-system](https://www.nseindia.com/static/products-services/equity-derivatives-trading-system)  
47. Common Risks and Regulatory Rules for Retail Algo Traders in India \- Stratzy, accessed on March 27, 2026, [https://stratzy.in/blog/common-risks-and-regulatory-rules-for-retail-algo-traders-in-india/](https://stratzy.in/blog/common-risks-and-regulatory-rules-for-retail-algo-traders-in-india/)  
48. Surbeivol/PythonMatchingEngine: High performance trading Matching Engine / Market Simulator using Level 3 Market Data for realistic simulation of High Frequency Trading Strategies \- GitHub, accessed on March 27, 2026, [https://github.com/Surbeivol/PythonMatchingEngine](https://github.com/Surbeivol/PythonMatchingEngine)  
49. Matching engines \- Jelle Pelgrims, accessed on March 27, 2026, [https://jellepelgrims.com/posts/matching\_engines](https://jellepelgrims.com/posts/matching_engines)  
50. bitcoin-lead-lag-relationship-analysis \- matching-engine \- README.md \- GitLab, accessed on March 27, 2026, [https://gitlab.engr.illinois.edu/sz73/bitcoin-lead-lag-relationship-analysis/-/blob/main/matching-engine/README.md?ref\_type=heads](https://gitlab.engr.illinois.edu/sz73/bitcoin-lead-lag-relationship-analysis/-/blob/main/matching-engine/README.md?ref_type=heads)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAvCAYAAABexpbOAAAG2UlEQVR4Xu3dacilcxjH8UuW7HskI0szlkzGREmMlP0FCmXkha1JCWPJOmoGSZItQiihUZYY2Sa8eFCEKZSYZF4oS7wnJXF9/c895//c55zHOcfMPE/zfD911XPu+z7LzKtf/+X6R0iSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSxrdf1tbtix0HZZ3evriBbJ91UdYO7RuSJEnT6Zqsb7Pez5rI+jhredZ21TPjOC7rw6x1WQ9lbTH5dhya9UXnHkGpsUvWB9E/lO2V9WDWjtW1A7PeiPI9E1H+He9lLayeGcXcrBXti5IkSdPt6egGqp2iBK0ru7fHtk/W6qzPowSr2gVZN7Wu4fisP7Meid6Qtyz6BzlG3b6uXp+T9U3W3tW1UdzaviBJkjSdmP67vHq9W9ZnWXdV18ZFYHsgSmirv4NRtMuif2C7Ouv+6A1c/P1slN/XdkbWV9XrC7N+jhLkxkFobIdFSZKkaUPYWZJ1XtbdUaYXD846NeuA7mNjIbDdGWV0jQB2bJQgRFgjtLUDG0Hp3Kxts96MyaNsjJr1G/kicDIFujLK567Kui4Gr4G7Ksq/7bsovwfPZJ25/oky5XpY9VqSJGlaMZK2Vesagenh6J1SJMQ8mvXEgDqh++i/msBG6CJ88V37Zp3dud8ObLdkLY0SHglg9Sgbz7afB6NohC/C3jDmRRnta6aBCWfvZJ1cPcO1o6rXkiRJ04ZgMtG6xhq227I+irLObMvJt0fSBDYQiL7MuiTr8M61OoAx1XlH1pwo71uU9Ut016wRsvoFtrOiTIfu2b4xACGNsMa0KeZH2ahQv9/AJkmSZoxmdKqNcLWhNh00gY0pUELgc9Ed0asDWDMd2qinRcGU5VPd2+sxavdy9I4SgmlRAuIx1TWC4bvRDWT8Bj7jpOiOEPIMwVGSJKkHAYdWFxOd4u9PYvzF81NhvdfbWX9kHdG6xzovAtT/CS1HRtltyuc/nrVr1g1Zizt/35u1tnONadBfo4yU8T7w+7j/W5S1dEzHMjJGkAPXCHNsLlgTZd1a2x5RNlCwRq2xIOutKAES10fZGMFvaNa98f9tLzZJktQX03tNaCC40B+tHnXaVFhLxkYEpiVnCvrCEdhGDa9M8dY7VJnirfu+gXBW7wolVEqSJPXVTEPuH2XB/Y1he4naKVEa/Y6CnaD9ercNQjCkma8kSVIPghkjPUzVscbKsNaL/w9G/o5u3xiA0TQC26AWH23N58+kkUVJkjQDvRSlRcYwIeO06K5361eHxOaHEMY058awMT9bkiRtJghpNIFtFsSzW3PnKIvn6U22obDg/z7rP+uekCRJ6mAqjvVr9CkDIz03Z50fZbcmuzkfi97zOOkXxs7SQTXMKJ0kSZKGcGLWX1GmMWlB8WPWD1EC2qBTB6YbYZH2HCAYjtpgd9TdnsNiB+hFYVsOSZK0CXGUE9Nzu8fMWF9FOLs9SkNceqVxIPurUQIYuyvpHcfJARNZH0eZVmRat7ZX1oPVa4IpZ5iuy/o0ynv5DKaHF3YfG9rcrBXhCKMkSdpE2DhAOLo0yqjWdGNdXXMOJxj5oxEtU7Dg5IDmd/LMxVFOLGjW5WFZ9LbaIPB9HZOPhOLAd9qbjIOD4mkDIkmSNOtwokD7KChOK+gX2MBzPL+i85qAx6gcxz/VzojeM0E575OTDMbB2j8Oqrc1iiRJmnXoa/Z71itRzvesR87QDmxgtIsjoghpBKknozdIcZ5nPXLHdOaLUTZb9MM06vNRds8el/VCTP4tBMPXYvhD4SVJkjYbBCp2r3L259+d4jzOJmj1C2xc+z7KKBzTnAS4GhsEWK+2MkoAY23cqiijef3WofFdV2WdGuXwekIkCJANfgM97TiDVJIkadZiFGt51k9Z8zvXBgU2NhTwPH9TNdavEbwYfRsG06zzopwR2ozK8Z2sr2vwmtBXr4mTJEmaFWiZUbfk4OzN1dEd3WoHtmYN2yNRghUhqx3YOPS+vX7tv/BZhDXWuYHAWL/fwCZJkmata7Nez3ogyvQlLUdYf0ZAYvPB2ihBiuO1mOak5ccBvLGDKUru01+O6wQ5NhasiTIFus36J7tY//ZM69qCKLtTm3VrTMsuje4UKqHyubAfmyRJmoVoTEuTXAIaa9Ka5rnDYkSOwDZK41z6zzEyV+M38Ftq9UaGxVlXVK8lSZI0AvqjXdO+OAU2FbT7tk2FUEgT3zntG5IkSRoOI2FL2henQGDrt1u0n+azF7VvSJIkaTSjnj06LD53JhzhJUmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJG0c/wBnahHPx09j/QAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFUAAAAYCAYAAACLM7HoAAACAklEQVR4Xu2XTytEURjGj1BEUeRvssJCKRKNECuShaIs7LEhScTKVghbJexY2VFY+Aq+g5WNj8D7zDzv3DN37h3z7zJT51e/mnPv6c7c577nvWeMcTgcjjiVtEVsD7GROrLEhRoBMfohbtMl6/OXuEjLmRnxir6Kt7TBnuSjgq6IF5YYQ5wLZJ2OWsfwRS9013gXLyZ6zV6xk0ZBM70Xu2i1+EAPkzPT6acIv5bWi3e0z5uaigs1nLxCrRKnKT7XUVxkn6LfFgsNckQ8o2g92tejoIk+iRMUHFDcaxi6zP1zMIY4lxE8vUtLjGGhaGBT4gkdMNFUf7ag4h4pVmkYezQsVJzLiAs1nbxD1ZtD79Q+ip6qPaTbm5o1GiR2DOc0sP/kCPqZf7sXpC75sIeGZXtMMxVOXqHiS5fps9hGwTCd5Big4Wu11VjH/ZRqqAt0yyTeIfoeCUO3lWGhrvmOx3GhRhAqbvqd2sscy/6U6nYHotxvaA/n/oYGPGf+t6cOiTu0wyQeMly15iCDMYrfFqPYjqGIVIwhziUZpPi39EbxctIn8CleU/vGN8Rxmg8apL2lwucoA9aqReF8B4hKVDaN9wJDBevL+kict8QYpvRjF2oEoeaKlj2Wbist6ILGCzLqf1TFAL9TH4726oKLQC+GLcgsLeUQygIXqsPhcDj+jB9V5ZCr7vQp8AAAAABJRU5ErkJggg==>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEYAAAAYCAYAAABHqosDAAACBklEQVR4Xu2WvUscQRjG3xAFg4rGwg+USNIEiSISQSwiiK1pTIJFSGWRNFoEIiriBxH0ihCLVCp+VDZCBLHRxipttMlfkCqNf0J8n91nnPHcOW73TgSdH/xg59ibnX1m5p0VCQQCN8BD2qi2eKyn94oQjId++lf9TN861+fqG3rbdKvrdF89pm3uTR461B06pX6n1e5NLp9on/NbndiHTqoPaLE00BeS/r9JVNFNtZeizxzdVStoPo/oltpJwRc6xvY1QjAJoKNBimssK4jlNk1Rf7LyXF2hw2LrWVpMMNvqBwpG6IlaQ/N5Rn+JrZngNd0Tf6gRleqaI9qwXDxVF+l7sTOZFayYH3SV7aSV+ZKeSnIwJ+IPNSIEk4fpELXE1BXUGDPwdntr2cDgluhHmjakVxJvLYjx+sgUDAIZpUdqMwWmyA2wDXDkjdNSwODmadpgzLiWxU4e6qJvxeCIh78lOZhDsTXskhCMJxh8tJ1Rd8vgYd9oq2NObJ0otHyTcGvMO8lWwzDGOfpE4g87OCH25RDSEMU1xgkPJJ5YCMyELLAd0UPPJd5jEAV3h/6T+NyH7izMiD3+iqHcx/VP9X+CG/bWaHX8obg24FifpV0S/wdeqaEhGE8waXlMv6q1tNALmi9fDCxrGDeBOX2aJNtWvgY6gqgPZv+W3OldIAQTCAQCJXIBRfqKGjdsql0AAAAASUVORK5CYII=>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAYCAYAAADDLGwtAAAAdUlEQVR4XmNgGGaAEYozgLgDiudBsTySOgZLKJ7CgNBkDMUzgJgFiolXWATF5SAOFEhC8VYgFoFi4hWCFMAwDMAUHkBiD6RCFyieDlfGwKAPxYuBmAOKiVfIA8UghdZQXAPFvmBtUEC0QhhgBmIxKIZpHp4AAMe7H2WhwLWnAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAXCAYAAAAGAx/kAAAAvElEQVR4Xu3SsQ4BURAF0CdIqDRCRMNnKLZQiujVEh2+Qe0TlBpKGwWJH/AHeqVOoeYOd2TYhFe8bt3kNLPzbvJ217nUpEC1DzrPQ5VkXqGsHLap0xiuNDfzMuxpAT0qymGbYEWaHCxp556LogsDyry2fySiM8xIC7xLJMGK9DpytRUlvo5P2rSBEzXfNjwTpKgFQ5If70gju/QtUqAl9qVO6QAlSqRPMVxoYp43YE032FLH7DwSrOif1OYOfOg0UDp8HgwAAAAASUVORK5CYII=>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAiCAYAAADiWIUQAAAFiUlEQVR4Xu3caahtcxjH8UeGTJkzl0uGDIVkKLMQGRJemN0MIdecSKZIQpTxmscMmUVkKBcvSDK8IlGUKC8o5aV4vp71b6+97z6341zbOfh+6mnvvdY6a6/h1vr1/P/7RkiSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSJEmSZtmKWWtnLdeVZteqowskSdL/1zJZZ2XdkXV81ktZOw1tMTl7ZH2ftWhk+UysnHVr1qdZ70Tt892sc7JWGmw25KSsU6KuwVyxfNQxnZp1XUzv2C7L+jDr66z3os6d1+uzVhtsNuTArEujvk+SJM1xB0c97NfsPh8b/1xgw2Hx9wS25pIY7k4RZggy6/WWzVV0OM+OQUh7LKrzOR1cx2+zNugtOzLrl6zte8skSdK/0KZZ30V1o07oLafD81bWhVk3Z72SdURUmGAdy1/IOrrbfvesh7KezDqq227XqK7X1VmrdNuBbZ/Kuj/rpphcYOMYHo86zq2y7o46vquyHsx6JKoL1bbdq1vPsV0e1X3iuB/Oui1r/W7bSdkt65Co63VL1iZDa5dsXGAjrH6WtWHW61nnZ70cdX/oqN4Tg/uyTdR53p61etT1IPARGrmG3DNJkjSL9s76POv3rIVRQYUi6BBclo0KKx9lHd6t44F/ctY1WTtmvRrVIaJ4v11UQMKCqNCHPbv1hALMj8UDG3Po2C/LxxUhkCHQcQhsBM9jogLZMzEIWvtGhdN9sp6OCiRsgwOiQivHz/ovszbLurNbzz4JM6NDlBtlrTWybKaOiwqWBEe6nNsOr14iAtvPWadHhWgC5ttZW3brP466D1zXE7N2jgpvhFu+h3u7edR57xJ1nx+NutcsfyOqS8n5c40IhutG/duQJEn/IELUT1kHdZ8JMwSBhjlVz0YFqtHlhB2CAsX7tp65UjfEIBjRVWP7ZtJDon2EoBdjsJ7vnuq4QGD7Kuqc2C9Bs79v5sYx549h5VGErnunqK172zVc0zNjeAiUOYWjCL4EsdG5aeM6bH2cd3+ou38t6Ja2+wpe+UxnjXMnrH7Q/Q0Bbf+o7h8dweejgpskSZogOktM/m/onBFOMBrYWM4wKcNo/eWEnRZ8GjoxF0UNufaDEa9t/5gqsK0RFT7GFR2e0U5XM9PAxitDiH3M/fpmZFkfYfSBGL4WM0WnjsDWEJrGBUGGmQ+Nxc9/aQIb14xw1vbJ/eU+9+9TH903cB/YB/dYkiRNEA/6a2PwsGbYrz2QCTEMG6INkbaHeD+k0JGjq9aGObfI2i/qF5ugU8S+eB3t5rD/Rd37hmNpw27jahKBjbBEB639opRhQs6DZeD7mF+2Qvd5najgxPlQS4vQ3N8PwYzznK6lCWyE9k+ihjwJXwyjLoiaz9fuE8Pe87r3zK9jyJl/KwxxS5KkCeNB/2bUBHQewvxwoAUawsxrUT8yYCjvvqjuyxlRc5pYDobJ6KYxX4x5bVdGBZqF3TYEQuZQMeRICGG/vGcd+/81pv9ryKnw9xdnfRF1LvOG1tbn57J+zLqr+8w5/BB1PgQ1hm45z9Oium1t/hZBis8EGxDeCDRsx99M1Yn6K9gX155X9t3mzk0H1/H9rN+iwvAOw6v/vDYMdRO46drNy3qiW3ZF1D09N2pe341RwZvrwTw47iHHdEHU9eDfBscJ/lsU7rskSZowOkY8iHmo053pd64IVgQ6HtJTda362E/rsjVT/R3L+c72/XMFxzR6zJxT/xjpvjFpHwSgFmBmii7WeVHBqV2X2TDuPoxeD+bftfOdH/WLVkmSNEsY0mTCOV03Jt9rcjYO54FJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkiRJkvSf8wcZbeKGun2IEQAAAABJRU5ErkJggg==>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAYCAYAAADOMhxqAAAAu0lEQVR4XtXRvwtBURQH8CNWg1IKk0gmSUpZDMwW5cdqkIw2m9GglP9CRv4/3+N9T+++K+W+7X3rs5x7T/d2jkim0qQ5dCmXuOHlrwYtqDWMKQ8nmtpFS49mXv1IW68e3rCnKlSoDXeqx1dFSrChBTzoCUtKJLihDxNy05D4S0X3QOfdITcDeFG6hgJdJZqCTcKWqAs70CdlusGZ9LUL7STatkrXMKSRc6Ajti99ZUU1/+BXghtapJPKYt7ajSXZf0O0qgAAAABJRU5ErkJggg==>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA0AAAAaCAYAAABsONZfAAAAuUlEQVR4Xu3SvQ4BQRSG4REUEoXKTyEoXARR0lEqRK1xDWz0QqFRiCtQ6N2Qe9BwTry7zrKFnU7iS55ksnO+ZDMzzv1kChiIEUqijsSkKjWwR0uUcRYBYkldyokjerAZij6iFMUFE2TMflvUEMWrpAMb3HETB1Rfo/FoUTUxF1eswqH3fF3SU1Njs7aZYmc/epUqWLvPkv7qFvqkonRxEkt0sBAz2OP3K+WRdc8LVuEl6joxXqV/fPMAI9sqGWlYO4AAAAAASUVORK5CYII=>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAiCAYAAADiWIUQAAAFh0lEQVR4Xu3cSYgkVRDG8RBH0XF3BpdRsNz3cUVUXEpxBb04bqDCgIyKjjuiuIGKiKKCG4iKKzLMRREXRDyICh48eFG8evPoSa8aH1GPepmdlQud2VU9/n8QVFdldvaL1wkZRL4sMwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAS7t4rPfY2WNNaVsf9p287uqxU75hjpRryln5rzZ7WnFedxTlvBblfAEAYG5UqDzg8YrHTR4feHxc2GN5DvJ4x+M+j488XvPYrbDHylMBcJ3HexY5f+hxcWGPxZbPaT6vO4KqvOZ9vgAAMFd7eHzrcXX22cEeD2Xvl+MUj18sjilXeFwy3dy7sccZ5Q8rqCh4OHv/qC1GUXCHRXepTnlOZeh57UNTXqLcVlteAAAMLhVsv1p0nNYVNy+bLsB/eWyzlSmIxta+YPvT43aPDaVt89S2YEtzeq6tzLz2oSkvUW6rLS8AAFaELo6/e/w7iads6Zqhyz2+mxFfeByrnSpoLZxubf3j8bfHeRYX7gMs1o31bWztCrYjPH6yac67FzdXUgEx9Dq3NgVbPqcae5rXJl3mfYhcm/IS5dY1r666zAMAAAtH3bVnPP6w4m2pPuji+L3F+rhDPD61fv6Gis23svjS4tjp/UvTXSvp4q0uW5siT93INvt1cacVx68iUuvq0vt7bPYDIJrTY2w6r01UpGhtYnneVayeOPlZ+3zuMbLIVbckX59sO9qmDwI00djKuQ2VV1d9nn8AAAxOxcpdVuym6SL9o8WTkzl1XHSBq4oDrbobo2Pl64+0ZuxVi7+rC/EQF8yx1RdVylWFxF7ZZxrH8dn7OnXH7kNTh608p5LmtQ0V5OV5P8ljS+kzyXPVvD1iS3+3i7q8pJxbl7y6GPL8AwCgd7otqK5HfjvwZqu+JaqLXLlQayrY9PTl1uz9ux7nWxzrM4/7Pe71uNbioYcXLRb/q9tzvcdmiwv4pRZdsMct1jjVGVt9UbWfxROhGnOiMe3v8YLH2x4nW6yjOt2iaNg0ed3H42yP5yzWwG30+NnjAo/3PT7xuM2ii/W8RU5dxi5NBVt5TjXvaV4v9LjM426LedS49PTvrRadMlHBdpTHLR7PWjxtqpy1jvEaj9M8frD4v2oedetVHTH9H3Tb/GmL7pfmSueO5ip155rU5SV5bnle+fmg+f3N4n/wpMdVFl3JNyzGls/3ORbHUJ762/p/Kn9tV/eOgg0AsCqooPja4paXiiZ1UHTh062/5VLB97LFLUoVDTq+igR9nnc41OnSzyOP4zwetCi6vvG4waKg2G7RAVLRpGKkztjqCzZt+8qi2LjRotum4kxUxOmrTQ7zOMvjSps+Lau5Uh76fY1bF35RgaXPFBqb5k7H1v5PWLexS13BVjWnKkjSvIoKM6370hi1Ta86nn5Wfhr3Bo+LLG59atwaa/7EbOrC5bmWu1Jpro6cvG9jVl6S51bOa2zT82Fvi6/50NhUaKooS+PS3Ofzrduu6Rav9nvT41BbmgsAAAttrcV6odQ9a7s+qQ1daHUB1es6K14cqwq2xywKqDMtOlEji2JJhUnaV8dq+nLYsdUXbPp9dW/SLV6NLRU7elXnSN0ZFW3qOKVCZlbBpq5OKthUbIm2pYKty9ilqWArz2n5SUoVn3raV/OqTl9VwaZOkzqKKnxUHG2yyFMFs45XV7Dp1vHIgrp4mqu2ZuUleW7lvDTWkcX5oFv4swq2/LzScQ6f7KP903ftUbABAID/BRW8J3icau1u8/YtFWwAAACYQR0qrQvbbNVrF4ek9WxaY6fuHgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABgOP8BBx7ZyD0c6iEAAAAASUVORK5CYII=>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACcAAAAYCAYAAAB5j+RNAAABX0lEQVR4Xu3WTytEURgG8BcR5U9SI2UWkpWFf1lIig1JVizIgmIlO0XZUBaSJIoyWYxsrJTyPWx8AWufQTyP+5zOMc1q5M6puU/9FvfMne575pz7njHLUkNpgDFZhiFpgy6pWqIsrkNuYV6aYUXezRedenbkoGS8VS6gU1JP1MXdSxFahOHS0oyuq5Il+YQveQvG6/yt6Sfq4lz4xi7KE3zICGwI3+TUsgrtEqYHXoW9zhW9H97034myONca2HjLtQk23Afh2+uKu4FNmYR64WeHwnHuU+LE1mXNfDeYgD3htvkV1/Ff4FLmzJ8Kj9ArjCsu7IXbljyQ+J2cFGBUzswfg7yelXPIyzV0y0+iLq5JGs03W+4zHu5U2j7K7blwKa9gXO5gSvotmQQ9w5YcW/I84oT4p4MqyoLwKBuQI5gW/tLDUrSkQDqFQdmFPjkxv3pcMXdUVpSoi8uS5S/5BnM5WQVpIqR+AAAAAElFTkSuQmCC>

[image11]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADcAAAAZCAYAAACVfbYAAAABlUlEQVR4Xu3XzSsFURgG8FcoYqHIR5KhKIUSKR8LC6KwIIoUd+ErKVncbHwVO/lIocieLOz9Q/4HG96ned7mzOzuTbfONE/96sydM+fMe+9p5lyRLFm8SbWaonlVR21uJ1+TyuLa6Ul1UKP6pNOoq1+pUK80njg3R5OJz71JqourVV+0qsoI6aIWHnsXFHJNv+qHXlQzeZtUF4fYUgzUHn2rcyomfbRNVfHTpUvqisNTEpadtps1dU/FBA8quCS0S5YmupJ4cfYr3ki0W2lVS9SvJqhH1dCGA8fJ4rrVJuHpu0KBhOPAllqkWQlfTZCTaB7c2zTtqwaKJdXFjdKHOqERdUyYyApFDqhXzRD2onnqdOA4WRzaF4TidmnQ6Xun6ulWwrngUMKNBODL3iH3fmOppHKJBsek1k4GAwEmHSY8JB4J1xoc2zdaSHHWz/raeEcSbuQBRa0TztnmPpZUF1dosAThQaJJEZs058CSHSD7Z4E2bhLG1BvhtTNE6GfL710t0LNEyz9QZ4RrrH+WLFmy/H/+AObiazD1Pq3OAAAAAElFTkSuQmCC>

[image12]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEIAAAAYCAYAAABOQSt5AAACHElEQVR4Xu3XT0uUURTH8SNpFFlRWhkFWW0KpBAXYbaoCNIiIgwqKkpEbFHbkqJVhhshWohEgkmbVq18CS7cuekNtO41iJ0v8zvcOzMtprFNM/cHH3Dm+szc5zz335iVlJT8RXa4Ibnrzste1yNtkbYvxH755MZkl7svPy0VqKXzXF7XvN8tH9wBaemUQigr8sXtFsL0wBW9bvmMy6bbkh/Z+x3pX1s7pRA1Yee4Jd/dLzmb/1ODOSYvXL80GgqPQUs72qh7KNGGPbpmW3kg+yTPUbchnCWaDYVoZOu9KXxvp0zoNY679xJt0d4rd6zJlEJYZSvkAIU/bY10/KsctHTQQgz729nfDNOXctXS8H5mqRB9bkYoUDwA2tblqTstjyxNK274ndAf2nDGzQl9vSiXrdK/6GP0vW6a8+Wr8lGuWzpNfrPKUwAZkAV3SFhIhyU/gzDK4nPyQpxzl+SapRvgrLIi3HAkH015IaIt2mNde6U2csQtS4+lwjGaqlIKoex0XRIHJ76Mi8CwzhPzlkI8kROWbjjvRHQKeSEYpjF9brhFOWypEKesMvSRX1tbCNqiPS8EnwX6Oi0UjClRNy22E57+rFCs2N7eWvq1+sZdkM9uUljoHss9tyYskvNCUVljwLVTwq9htnRw87TFZ48IfWKUgkKclCWrPjH/k5RC/CeJKcxDYEcBu0jbhVEK1qDYMlkH2y6lEM3kN2OclV/5/Mz5AAAAAElFTkSuQmCC>

[image13]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADMAAAAYCAYAAABXysXfAAABuklEQVR4Xu3WzStlcRzH8Z88RB5uUjLNKEuSxCSJDamJRvJQHvJQTMrESkmzmAULSQbNMM1CkY2VKAtla2/jH7D2N4jvx30f59zbtbjN4p57up961b33PH5/53t/v+NcLrlkLPnmM0ZNM8pNFbImkSgmhn+mD8VmHA/OLzL0WcKPpN/LsGsqEfpEqpgTHJsSKGo16eZ7VmQET+YZ94Hf8/xdw59IFeNFM9oAzs0jGoI7ZSgFZhCzSdteM4EKBPPB3EFrTRjiLQ+/kzcokSlG06wWSUk17eqgU2h2894G9Ihn0G++Y9L5Lao3hl4Mm2VogDqwalpQY9ag/YKDq2Pkm1nEH7a9RTd7hX18cf6qf2Y+odRsQwW1Qjd1CE0SU/jp/FE84hhRv++g1hxAU38XNACb0LW9e9OAtiHaxRSZQniLox5nFYLTsT7XQS11iR4X71+vh4MXS9XfGqQN6FrVGHLxthO17l90usTzpzpn2tErzToazQpUzAWazB7azTyuXXxql5jzR103pU6QLTONMXOLry7+iiU65xxuzEeknUgV8168R/5fjz3T0f9NFswv1CfskUWJVDGhygtrI4G/d+e4aAAAAABJRU5ErkJggg==>