import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from models.company import Company, BusinessType
from engine.timeline import Timeline, N_PERIOD
from engine.finance import initialize_company, advance_quarter_financials, check_cash_crisis, BUSINESS_PARAMS
from engine.roulette import tick_bombs, audit_contract_roulette, roll
from scenario.ipo_knowledge import get_available_events, shareholder_meeting_event
from models.events import Choice
from textual.app import App, ComposeResult
from textual.widgets import Static, RichLog, Input, Header
from textual.containers import Horizontal
print("ALL IMPORTS OK")
print("BUSINESS_PARAMS count:", len(BUSINESS_PARAMS))
