import json
import os
from datetime import date, timedelta
from typing import Optional

import requests
import streamlit as st
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.run.agent import RunOutput

FXMACRODATA_BASE_URL = "https://api.fxmacrodata.com/v1"

# Optional. Without a key only USD is available, history is limited to the last
# 90 days, and new releases show up 15 minutes after they are published.
FXMACRODATA_API_KEY = os.getenv("FXMACRODATA_API_KEY", "")

# The API returns a lot of metadata per row. These are the fields the agent
# actually reasons over; names are kept exactly as the API returns them.
HISTORY_FIELDS = (
    "currency", "indicator", "name", "source", "latest_available_date",
    "cb_target", "freemium_window", "freemium_delay",
)
ROW_FIELDS = (
    "date", "val", "previous_value", "change_from_previous", "val_mom",
    "announcement_datetime_local",
)
CALENDAR_FIELDS = (
    "release", "name", "announcement_datetime_utc", "announcement_datetime_local",
    "event_importance", "release_date_confirmed",
)
FOREX_FIELDS = ("date", "val", "open", "high", "low", "close")


def set_fxmacrodata_key(key: str) -> None:
    global FXMACRODATA_API_KEY
    FXMACRODATA_API_KEY = key.strip()


def _get(path: str, params: Optional[dict] = None) -> dict:
    headers = {"Accept": "application/json"}
    if FXMACRODATA_API_KEY:
        headers["X-API-Key"] = FXMACRODATA_API_KEY
    params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    resp = requests.get(f"{FXMACRODATA_BASE_URL}{path}", params=params, headers=headers, timeout=30)
    try:
        body = resp.json()
    except ValueError:
        body = {"detail": resp.text[:300]}
    if resp.status_code != 200:
        # 401 here means "needs a data key" (any non-USD currency, FX rates).
        # Pass the API's own error through so the agent can say so plainly.
        return {"status_code": resp.status_code, **body}
    return body


def _pick(record: dict, fields: tuple) -> dict:
    return {k: record[k] for k in fields if record.get(k) is not None}


def get_indicator_catalogue(currency: str) -> str:
    """List the macro indicators available for a currency.

    Use this first when you are not sure of an indicator's slug, e.g. whether
    US core CPI is `core_inflation` or something else.

    Args:
        currency: 3-letter currency code, e.g. USD, EUR, GBP, JPY, AUD.

    Returns:
        JSON keyed by indicator slug, with name, unit, frequency and whether a
        data key is needed to read it.
    """
    body = _get(f"/data_catalogue/{currency.upper()}")
    if "status_code" in body:
        return json.dumps(body)
    catalogue = {}
    for slug, meta in body.items():
        if not isinstance(meta, dict):
            continue
        entry = _pick(meta, ("name", "unit", "frequency"))
        coverage = meta.get("coverage") or {}
        if "requires_api_key" in coverage:
            entry["requires_api_key"] = coverage["requires_api_key"]
        catalogue[slug] = entry
    return json.dumps(catalogue)


def get_indicator_history(
    currency: str,
    indicator: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 24,
) -> str:
    """Get released values for one macro indicator, most recent first.

    Each row has the release value (`val`), the prior value, the change, and
    when it was announced. Useful slugs for USD include inflation,
    core_inflation, pce, core_pce, policy_rate, policy_rate_target_lower,
    effr, risk_free_rate, gov_bond_3m, gov_bond_6m, gov_bond_2y, gov_bond_10y,
    unemployment, non_farm_payrolls, gdp and retail_sales.

    Args:
        currency: 3-letter currency code, e.g. USD.
        indicator: Indicator slug from get_indicator_catalogue.
        start_date: Optional YYYY-MM-DD lower bound.
        end_date: Optional YYYY-MM-DD upper bound.
        limit: Maximum number of rows to return (default 24).

    Returns:
        JSON with indicator metadata and a `data` list of releases. If
        `freemium_delay` or `freemium_window` is present, the response was
        served without a data key.
    """
    body = _get(
        f"/announcements/{currency.upper()}/{indicator}",
        {"start_date": start_date, "end_date": end_date, "limit": limit},
    )
    if "status_code" in body:
        return json.dumps(body)
    result = _pick(body, HISTORY_FIELDS)
    result["data"] = [_pick(row, ROW_FIELDS) for row in body.get("data", [])]
    return json.dumps(result)


def get_release_calendar(
    currency: str,
    indicator: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Get scheduled release dates for a currency, including central bank
    rate decisions (release `policy_rate`) and data releases such as CPI.

    Args:
        currency: 3-letter currency code, e.g. USD.
        indicator: Optional indicator slug to filter on, e.g. policy_rate or inflation.
        start_date: Optional YYYY-MM-DD lower bound. Defaults to today.
        end_date: Optional YYYY-MM-DD upper bound. Defaults to 60 days from today.

    Returns:
        JSON with a `data` list of upcoming releases in time order.
    """
    today = date.today()
    body = _get(
        f"/calendar/{currency.upper()}",
        {
            "indicator": indicator,
            "start_date": start_date or today.isoformat(),
            "end_date": end_date or (today + timedelta(days=60)).isoformat(),
        },
    )
    if "status_code" in body:
        return json.dumps(body)
    return json.dumps({
        "currency": body.get("currency"),
        "timezone": body.get("timezone"),
        "data": [_pick(row, CALENDAR_FIELDS) for row in body.get("data", [])],
    })


def get_fx_rates(base: str, quote: str, limit: int = 30) -> str:
    """Get daily FX spot rates for a currency pair, most recent first.
    Needs a data key.

    Args:
        base: Base currency code, e.g. EUR.
        quote: Quote currency code, e.g. USD.
        limit: Number of daily rows to return (max 100).

    Returns:
        JSON with a `data` list of daily rates.
    """
    body = _get(f"/forex/{base.upper()}/{quote.upper()}", {"limit": min(limit, 100)})
    if "status_code" in body:
        return json.dumps(body)
    return json.dumps({
        "base": body.get("base"),
        "quote": body.get("quote"),
        "source": body.get("source"),
        "data": [_pick(row, FOREX_FIELDS) for row in body.get("data", [])],
    })


INSTRUCTIONS = [
    "Answer with numbers from the tools, not from memory. Quote the release date next to every figure.",
    "If you are unsure of an indicator slug, call get_indicator_catalogue first.",
    "For questions about an upcoming central bank meeting, find the next `policy_rate` release in the calendar, "
    "then compare the current target range (policy_rate, policy_rate_target_lower) with the effective rate (effr) "
    "and short bill yields (gov_bond_1m, gov_bond_3m, gov_bond_6m). Bills trading well below the effective rate "
    "suggest cuts are expected; at or above suggest a hold or hikes. Say that this is a rough read from bill "
    "yields, not futures pricing.",
    "For trend questions, give the last few releases in a small table and describe the direction and pace.",
    "Mention any release in the calendar over the next two weeks that could change the picture.",
    "If a tool result contains `freemium_delay` with withheld_count above zero, say that a newer release exists "
    "but is not visible without a data key. If `freemium_window` is present, say history is limited to 90 days.",
    "If a tool returns status_code 401, say that currency or endpoint needs an FXMacroData key. Do not describe it as missing data.",
    "Keep answers short. Use tables for numbers.",
]


def build_agent(openai_api_key: str, model_id: str) -> Agent:
    tools = [get_indicator_catalogue, get_indicator_history, get_release_calendar]
    if FXMACRODATA_API_KEY:
        tools.append(get_fx_rates)
    return Agent(
        name="Macro & FX Research Agent",
        model=OpenAIChat(id=model_id, api_key=openai_api_key),
        tools=tools,
        description="You are a macro and FX analyst. You answer questions about central banks, inflation, "
                    "growth, rates and currencies using official economic data.",
        instructions=INSTRUCTIONS,
        add_datetime_to_context=True,
        markdown=True,
    )


def main() -> None:
    st.set_page_config(page_title="AI Macro & FX Research Agent", page_icon="🌐")
    st.title("AI Macro & FX Research Agent 🌐")
    st.caption("Ask about central banks, inflation, yields and currencies. Answers are built from official "
               "releases pulled from FXMacroData.")

    with st.sidebar:
        openai_api_key = st.text_input("OpenAI API Key", type="password", value=os.getenv("OPENAI_API_KEY", ""))
        model_id = st.text_input("Model", value="gpt-5.2")
        fx_key = st.text_input("FXMacroData API Key (optional)", type="password", value=os.getenv("FXMACRODATA_API_KEY", ""))
        set_fxmacrodata_key(fx_key)
        if FXMACRODATA_API_KEY:
            st.success("Data key set: all currencies, full history and FX rates.")
        else:
            st.info("No data key: USD only, the last 90 days of history, and new releases appear "
                    "15 minutes after publication. Other currencies and FX rates need a key.")

    if not openai_api_key:
        st.warning("Enter your OpenAI API key in the sidebar to start.")
        return

    examples = [
        "What's priced in for the next Fed meeting, and how has US CPI trended?",
        "Is the US labour market cooling? Use payrolls, unemployment and jobless claims.",
        "What US releases are due in the next two weeks, and which matter most for the dollar?",
    ]
    if "messages" not in st.session_state:
        st.session_state.messages = []

    cols = st.columns(len(examples))
    clicked = None
    for col, example in zip(cols, examples):
        if col.button(example):
            clicked = example

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask a macro or FX question") or clicked
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Carry the last exchange so follow-ups like "and core?" work.
    history = st.session_state.messages[-3:-1]
    prompt = question
    if history:
        context = "\n\n".join(f"{m['role']}: {m['content']}" for m in history)
        prompt = f"Earlier in this conversation:\n{context}\n\nNew question: {question}"

    agent = build_agent(openai_api_key, model_id)
    with st.chat_message("assistant"):
        with st.spinner("Pulling releases and calendar..."):
            response: RunOutput = agent.run(prompt, stream=False)
        st.markdown(response.content)
        calls = getattr(response, "tools", None) or []
        if calls:
            with st.expander(f"Data calls ({len(calls)})"):
                for call in calls:
                    st.code(f"{call.tool_name}({json.dumps(call.tool_args)})", language="python")
    st.session_state.messages.append({"role": "assistant", "content": response.content})


if __name__ == "__main__":
    main()
