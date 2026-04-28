from __future__ import annotations


class IDS:
    # Stores
    BARS_STORE = "bars_store"
    BARS1_STORE = "bars1_store"
    META_STORE = "meta_store"
    INDEX_STORE = "index_store"
    ACTION_STORE = "action_store"
    LOADED_STORE = "loaded_store"
    SHOW_VOLUME_STORE = "show_volume_store"
    SHOW_DECISION_STORE = "show_decision_store"
    VIEW_REV_STORE = "view_rev_store"
    VIEW_LOCK_STORE = "view_lock_store"
    VIEWPORT_STORE = "viewport_store"
    PLAY_STORE = "play_store"
    SPEED_STORE = "speed_store"
    PHASE_STORE = "phase_store"
    SHOW_OR_STORE = "show_or_store"
    SIM_STORE = "sim_store"
    INTERACT_STORE = "interact_store"

    # Components
    KEY_EVENT = "key_event"
    PLAY_TIMER = "play_timer"
    MAIN_GRID = "main_grid"

    SYMBOL = "symbol"
    DATE_ET = "date_et"

    BTN_LOAD = "btn_load"
    BTN_RESET = "btn_reset"
    BTN_PLAY = "btn_play"
    SPEED = "speed"
    BTN_PREV1 = "btn_prev1"
    BTN_PREV5 = "btn_prev5"
    BTN_NEXT1 = "btn_next1"
    BTN_NEXT5 = "btn_next5"
    BTN_AUTOSCALE = "btn_autoscale"
    BTN_TOGGLE_VOLUME = "btn_toggle_volume"
    BTN_TOGGLE_DECISION = "btn_toggle_decision"
    BTN_TOGGLE_OR = "btn_toggle_or"
    BTN_ALL = "btn_all"

    CHART = "chart"
    REPLAY_INFO = "replay_info"
    HOVER_READOUT = "hover_readout"
    STATUS_LEFT = "status_left"
    STATUS_RIGHT = "status_right"

    PHASE_TABS = "phase_tabs"
    INP_SETUP = "inp_setup"
    INP_CONF = "inp_conf"
    INP_QUALITY = "inp_quality"
    INP_ENTRY = "inp_entry"
    INP_STOP = "inp_stop"
    INP_TARGET = "inp_target"
    INP_PASS_REASON = "inp_pass_reason"
    INP_NOTES = "inp_notes"

    BTN_LONG = "btn_long"
    BTN_SHORT = "btn_short"
    BTN_PASS = "btn_pass"
    BTN_SAVE = "btn_save"

    DECISION_PANEL = "decision_panel"
    DECISIONS_LIST = "decisions_list"

    RIGHT_TABS = "right_tabs"
    JOURNAL_TAB = "journal_tab"
    SIM_TAB = "sim_tab"

    # Sim UI
    SIM_SIDE = "sim_side"
    SIM_ORDER_TYPE = "sim_order_type"
    SIM_QTY = "sim_qty"
    SIM_LIMIT = "sim_limit"
    SIM_STOP = "sim_stop"
    SIM_STOP_LOSS = "sim_stop_loss"
    SIM_TAKE_PROFIT = "sim_take_profit"
    BTN_SIM_PLACE = "btn_sim_place"
    SIM_CLICK_MODE = "sim_click_mode"
    SIM_VALIDATION = "sim_validation"
    SIM_TICKET_SUMMARY = "sim_ticket_summary"
    SIM_CHART_TOOLS_HINT = "sim_chart_tools_hint"

    SIM_CANCEL_ORDER_ID = "sim_cancel_order_id"
    BTN_SIM_CANCEL = "btn_sim_cancel"
    BTN_SIM_FLATTEN = "btn_sim_flatten"

    SIM_STATUS = "sim_status"
    SIM_SESSION_SUMMARY = "sim_session_summary"
    SIM_POS_SUMMARY = "sim_pos_summary"
    SIM_PNL_SUMMARY = "sim_pnl_summary"
    SIM_ACTIVE_ORDERS = "sim_active_orders"
    SIM_FILLS = "sim_fills"
    SIM_SELECTED_ORDER = "sim_selected_order"

    @staticmethod
    def del_decision(decision_id: str) -> dict:
        return {"type": "del_decision", "id": decision_id}

