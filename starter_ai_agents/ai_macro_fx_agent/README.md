## 🌐 AI Macro & FX Research Agent

A Streamlit app with an Agno agent that answers macro and currency questions from official economic releases instead of from the model's memory. Ask "What's priced in for the next Fed meeting, and how has US CPI trended?" and the agent looks up the next rate decision in the release calendar, pulls the current fed funds range, the effective rate and short bill yields, reads the last few CPI prints, and then reasons over those numbers.

Data comes from the [FXMacroData](https://fxmacrodata.com/?utm_source=github&utm_medium=referral&utm_campaign=awesome-llm-apps&utm_content=readme) REST API. USD works without a data key.

### Features

- Indicator history: CPI, PCE, payrolls, unemployment, GDP, policy rates, Treasury yields and more, with release dates and prior values
- Release calendar: upcoming central bank decisions and data releases, so the agent can tell you what is due before an answer goes stale
- Indicator catalogue lookup, so the agent finds the right series instead of guessing names
- FX spot rates for any supported pair when a data key is set
- A "Data calls" panel under each answer showing exactly which series were fetched

### What works without a data key

| | No key | With `FXMACRODATA_API_KEY` |
|---|---|---|
| Currencies | USD only | 22 currencies (EUR, GBP, JPY, AUD, ...) |
| History | last 90 days | full history |
| New releases | visible 15 minutes after publication | real time |
| FX rates | no | yes |

Without a key the agent tells you when a newer release exists but is still inside the 15-minute delay, and when a question needs more than 90 days of history.

### How to get Started?

1. Clone the GitHub repository

```bash
git clone https://github.com/Shubhamsaboo/awesome-llm-apps.git
cd awesome-llm-apps/starter_ai_agents/ai_macro_fx_agent
```

2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

3. Get your OpenAI API Key

- Sign up for an [OpenAI account](https://platform.openai.com/) and obtain your API key.
- Paste it into the sidebar, or export it before starting the app:
```bash
export OPENAI_API_KEY='your-api-key-here'
```

4. (Optional) Set an FXMacroData key for non-USD currencies, full history and FX rates. You can also paste it into the sidebar.
```bash
export FXMACRODATA_API_KEY='your-fxmacrodata-key'
```

5. Run the Streamlit App
```bash
streamlit run macro_fx_agent.py
```

### How it works

The agent has four plain Python tools, each a thin wrapper over one endpoint of `https://api.fxmacrodata.com/v1`:

- `get_indicator_catalogue(currency)` calls `/data_catalogue/{currency}`
- `get_indicator_history(currency, indicator, ...)` calls `/announcements/{currency}/{indicator}`
- `get_release_calendar(currency, ...)` calls `/calendar/{currency}`
- `get_fx_rates(base, quote)` calls `/forex/{base}/{quote}` and is only given to the agent when a data key is set

The key, when present, goes in the `X-API-Key` header. Responses are trimmed to the fields the agent needs (value, prior value, change, release time) but field names are left as the API returns them.

The "priced in" answer is a rough read: if 3- and 6-month bill yields sit well below the effective fed funds rate, the market expects cuts. The agent says so rather than presenting it as futures-implied probabilities.

The tool functions don't depend on Streamlit, so you can call them directly:

```python
from macro_fx_agent import get_indicator_history, get_release_calendar

print(get_indicator_history("USD", "inflation", limit=6))
print(get_release_calendar("USD", indicator="policy_rate"))
```
