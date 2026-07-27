import sys
import os
sys.path.insert(0, "/app")
from app.styles import inject_styles, tier_badge, stat_card

import streamlit as st # type: ignore
import requests
import plotly.graph_objects as go

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")

# ------------------------------------------------------------------
# Tier config
# ------------------------------------------------------------------

TIER_CONFIG = {
    1: {"label": "Ad Hoc",     "color": "#e74c3c", "bg": "#fdecea"},
    2: {"label": "Developing", "color": "#e67e22", "bg": "#fef3e2"},
    3: {"label": "Defined",    "color": "#f1c40f", "bg": "#fefde2"},
    4: {"label": "Managed",    "color": "#2980b9", "bg": "#e8f4fb"},
    5: {"label": "Optimizing", "color": "#27ae60", "bg": "#e9f7ef"},
}

EFFORT_COLORS = {
    "Low":    "#27ae60",
    "Medium": "#e67e22",
    "High":   "#e74c3c",
}

IMPACT_COLORS = {
    "Low":    "#95a5a6",
    "Medium": "#2980b9",
    "High":   "#8e44ad",
}

ROLE_LABELS = {
    "super_admin":  "Super Admin",
    "client_admin": "Client Admin",
    "assessor":     "Assessor",
    "viewer":       "Viewer",
}


# ------------------------------------------------------------------
# API helpers
# ------------------------------------------------------------------

def api_post(endpoint: str, data: dict = None, form: dict = None, timeout: int = 10) -> dict:
    token = st.session_state.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        if form:
            r = requests.post(f"{FASTAPI_BASE_URL}{endpoint}", data=form, headers=headers, timeout=timeout)
        else:
            r = requests.post(f"{FASTAPI_BASE_URL}{endpoint}", json=data, headers=headers, timeout=timeout)
        return {"ok": r.status_code < 300, "status": r.status_code, "data": r.json()}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "status": 0, "data": {"detail": "Cannot connect to backend"}}
    except requests.exceptions.ReadTimeout:
        return {"ok": False, "status": 0, "data": {"detail": "Request timed out. Please try again."}}


def api_get(endpoint: str) -> dict:
    token = st.session_state.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.get(f"{FASTAPI_BASE_URL}{endpoint}", headers=headers, timeout=10)
        return {"ok": r.status_code < 300, "status": r.status_code, "data": r.json()}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "status": 0, "data": {"detail": "Cannot connect to backend"}}


def api_patch(endpoint: str, data: dict = None) -> dict:
    token = st.session_state.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.patch(f"{FASTAPI_BASE_URL}{endpoint}", json=data, headers=headers, timeout=10)
        return {"ok": r.status_code < 300, "status": r.status_code, "data": r.json()}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "status": 0, "data": {"detail": "Cannot connect to backend"}}


def api_delete(endpoint: str) -> dict:
    token = st.session_state.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.delete(f"{FASTAPI_BASE_URL}{endpoint}", headers=headers, timeout=10)
        return {"ok": r.status_code < 300, "status": r.status_code, "data": {}}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "status": 0, "data": {"detail": "Cannot connect to backend"}}


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------

def do_login(email: str, password: str) -> bool:
    result = api_post("/auth/login", form={"username": email, "password": password})
    if result["ok"]:
        d = result["data"]
        st.session_state["token"] = d["access_token"]
        st.session_state["role"] = d["role"]
        st.session_state["full_name"] = d["full_name"]
        st.session_state["org_id"] = d["org_id"]
        return True
    return False


def do_logout():
    for key in ["token", "role", "full_name", "org_id", "assessment_id",
                "current_dimension_index", "scorecard_assessment_id",
                "ai_analysis", "ai_roadmap"]:
        st.session_state.pop(key, None)


# ------------------------------------------------------------------
# RBAC page guard
# ------------------------------------------------------------------

def require_page_role(*roles: str) -> bool:
    """
    Call at the top of any restricted page.
    Stops rendering and shows error if user role is not permitted.
    """
    role = st.session_state.get("role", "")
    if role not in roles:
        st.error("Access denied. You do not have permission to view this page.")
        st.stop()
    return True


# ------------------------------------------------------------------
# Sidebar — filtered by role
# ------------------------------------------------------------------

def render_sidebar():
    name = st.session_state.get("full_name", "User")
    role = st.session_state.get("role", "")
    with st.sidebar:
        st.title("AI Maturity Tool")
        st.caption(f"Signed in as {name}")
        st.caption(f"Role: `{ROLE_LABELS.get(role, role)}`")
        st.divider()

        # All roles
        if st.button("Dashboard", use_container_width=True):
            st.session_state["page"] = "dashboard"
            st.rerun()

        if st.button("History", use_container_width=True):
            st.session_state["page"] = "history"
            st.rerun()

        # Admin roles only
        if role in ("super_admin", "client_admin"):
            if st.button("Admin Panel", use_container_width=True):
                st.session_state["page"] = "admin"
                st.rerun()

        st.divider()
        if st.button("Sign Out", use_container_width=True):
            do_logout()
            st.rerun()


# ------------------------------------------------------------------
# Radar chart
# ------------------------------------------------------------------

def build_radar_chart(dimension_scores: list) -> go.Figure:
    labels = [d["label"] for d in dimension_scores]
    scores = [d["score"] for d in dimension_scores]
    labels_closed = labels + [labels[0]]
    scores_closed = scores + [scores[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=scores_closed, theta=labels_closed,
        fill="toself", fillcolor="rgba(41, 128, 185, 0.15)",
        line=dict(color="#2980b9", width=2), name="Your Score",
    ))
    ref = [3.0] * len(labels) + [3.0]
    fig.add_trace(go.Scatterpolar(
        r=ref, theta=labels_closed, fill="none",
        line=dict(color="#95a5a6", width=1, dash="dash"), name="Defined (3.0)",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 5],
                          tickvals=[1,2,3,4,5], gridcolor="#ecf0f1"),
            angularaxis=dict(gridcolor="#ecf0f1"),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15),
        margin=dict(t=40, b=40, l=60, r=60),
        paper_bgcolor="rgba(0,0,0,0)", height=450,
    )
    return fig


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------

def show_login_page():
    inject_styles()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("AI Platform Maturity Assessment")
        st.subheader("Sign in to continue")
        st.divider()
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="you@company.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            if submitted:
                if not email or not password:
                    st.error("Please enter both email and password.")
                    return
                with st.spinner("Signing in..."):
                    success = do_login(email, password)
                if success:
                    st.rerun()
                else:
                    st.error("Invalid email or password.")


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

def show_dashboard():
    inject_styles()
    render_sidebar()
    role = st.session_state.get("role", "")
    name = st.session_state.get("full_name", "User")
    st.title(f"Welcome, {name}")
    st.divider()

    result = api_get("/assessments/active")
    active = result["data"] if result["ok"] else None

    if active:
        assessment = active["assessment"]
        completion = active["completion"]
        overall = completion["_overall"]
        st.subheader("Resume Assessment")
        st.info(
            f"Assessment in progress: **{assessment['title']}**  \n"
            f"Progress: {overall['answered']}/{overall['total']} questions ({overall['percent']}%)"
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Resume Assessment", use_container_width=True, type="primary"):
                st.session_state["assessment_id"] = assessment["id"]
                st.session_state["page"] = "assessment"
                st.rerun()
        with col2:
            if st.button("Discard and Start New", use_container_width=True):
                with st.spinner("Discarding..."):
                    api_delete(f"/assessments/{assessment['id']}")
                st.rerun()

        st.subheader("Progress by Dimension")
        for dim_id, dim_status in completion.items():
            if dim_id == "_overall":
                continue
            col1, col2 = st.columns([3, 1])
            with col1:
                st.progress(dim_status["percent"] / 100, text=dim_status["label"])
            with col2:
                st.caption(f"{dim_status['answered']}/{dim_status['total']}")
    else:
        # Viewers cannot start assessments
        if role not in ("viewer",):
            st.subheader("Start New Assessment")
            st.write("No active assessment. Start one to evaluate your AI platform maturity.")
            if st.button("Start Assessment", type="primary"):
                with st.spinner("Creating..."):
                    result = api_post("/assessments", data={"title": "AI Maturity Assessment"})
                if result["ok"]:
                    st.session_state["assessment_id"] = result["data"]["id"]
                    st.session_state["page"] = "assessment"
                    st.rerun()
                else:
                    st.error(f"Error: {result['data'].get('detail', 'Unknown error')}")
        else:
            st.info("You have view-only access. Contact your admin to run an assessment.")

    all_result = api_get("/assessments")
    if all_result["ok"]:
        completed = [a for a in all_result["data"] if a["status"] == "completed"]
        if completed:
            st.divider()
            st.subheader("Completed Assessments")
            for a in completed:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.write(f"**{a['title']}**")
                    st.caption(f"Completed: {a['completed_at'][:10]}")
                with col3:
                    if st.button("View Scorecard", key=f"sc_{a['id']}"):
                        st.session_state["scorecard_assessment_id"] = a["id"]
                        st.session_state["ai_analysis"] = None
                        st.session_state["ai_roadmap"] = None
                        st.session_state["page"] = "scorecard"
                        st.rerun()


# ------------------------------------------------------------------
# Assessment wizard
# ------------------------------------------------------------------

def show_assessment_page():
    inject_styles()
    require_page_role("super_admin", "client_admin", "assessor")

    assessment_id = st.session_state.get("assessment_id")
    if not assessment_id:
        st.session_state["page"] = "dashboard"
        st.rerun()

    result = api_get(f"/assessments/{assessment_id}")
    if not result["ok"]:
        st.error("Could not load assessment.")
        return

    assessment_data = result["data"]
    completion = assessment_data["completion"]
    responses = {r["question_id"]: r for r in assessment_data["responses"]}

    bank_result = api_get("/questions")
    if not bank_result["ok"]:
        st.error("Could not load questions.")
        return

    dimensions = bank_result["data"]["dimensions"]
    dim_ids = [d["id"] for d in dimensions]

    with st.sidebar:
        st.title("Assessment")
        st.divider()
        for dim in dimensions:
            dim_status = completion.get(dim["id"], {})
            pct = dim_status.get("percent", 0)
            icon = "✅" if pct == 100 else ("🔄" if pct > 0 else "⬜")
            if st.button(f"{icon} {dim['label']}", key=f"nav_{dim['id']}",
                        use_container_width=True):
                st.session_state["current_dimension_index"] = dim_ids.index(dim["id"])
                st.rerun()
        st.divider()
        overall = completion.get("_overall", {})
        st.progress(overall.get("percent", 0) / 100,
                   text=f"Overall: {overall.get('percent', 0)}%")
        st.divider()
        if st.button("Back to Dashboard", use_container_width=True):
            st.session_state["page"] = "dashboard"
            st.rerun()

    current_index = st.session_state.get("current_dimension_index", 0)
    dim = dimensions[current_index]
    dim_status = completion.get(dim["id"], {})

    st.title(dim["label"])
    st.caption(dim["description"])
    st.progress(dim_status.get("percent", 0) / 100,
               text=f"{dim_status.get('answered', 0)}/{dim_status.get('total', 0)} answered")
    st.divider()

    for question in dim["questions"]:
        q_id = question["id"]
        existing = responses.get(q_id)
        current_value = existing["answer_value"] if existing else None

        st.markdown(f"**{question['text']}**")
        options = question["options"]
        option_labels = [o["label"] for o in options]
        option_values = [o["value"] for o in options]

        current_index_in_options = None
        if current_value is not None:
            try:
                current_index_in_options = option_values.index(current_value)
            except ValueError:
                current_index_in_options = None

        selected = st.radio(label=q_id, options=option_labels,
                           index=current_index_in_options,
                           key=f"q_{q_id}", label_visibility="collapsed")

        if selected:
            selected_value = option_values[option_labels.index(selected)]
            if current_value != selected_value:
                with st.spinner("Saving..."):
                    api_post(f"/assessments/{assessment_id}/responses", data={
                        "question_id": q_id,
                        "answer_value": selected_value,
                        "answer_label": selected,
                    })
                st.rerun()
        st.divider()

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if current_index > 0:
            if st.button("Previous Dimension", use_container_width=True):
                st.session_state["current_dimension_index"] = current_index - 1
                st.rerun()
    with col3:
        if current_index < len(dimensions) - 1:
            if st.button("Next Dimension", use_container_width=True, type="primary"):
                st.session_state["current_dimension_index"] = current_index + 1
                st.rerun()
        else:
            overall = completion.get("_overall", {})
            if overall.get("complete"):
                if st.button("Submit Assessment", use_container_width=True, type="primary"):
                    with st.spinner("Submitting..."):
                        result = api_post(f"/assessments/{assessment_id}/submit", data={})
                    if result["ok"]:
                        st.session_state["scorecard_assessment_id"] = assessment_id
                        st.session_state["ai_analysis"] = None
                        st.session_state["ai_roadmap"] = None
                        st.session_state["page"] = "scorecard"
                        st.rerun()
                    else:
                        st.error(result["data"].get("detail", "Submission failed."))
            else:
                st.button(f"Submit ({overall.get('percent', 0)}% complete)",
                         disabled=True, use_container_width=True)


# ------------------------------------------------------------------
# Scorecard
# ------------------------------------------------------------------

def show_scorecard_page():
    inject_styles()
    st.sidebar.empty()
    render_sidebar()

    assessment_id = st.session_state.get("scorecard_assessment_id")
    if not assessment_id:
        st.session_state["page"] = "dashboard"
        st.rerun()

    result = api_get(f"/assessments/{assessment_id}/result")
    if not result["ok"]:
        st.error("Could not load scorecard.")
        return

    data = result["data"]
    tier = data["maturity_tier"]
    tier_cfg = TIER_CONFIG.get(tier, TIER_CONFIG[1])
    dim_scores = data["dimension_scores"]
    recommendations = data["recommendations"]

    st.title("AI Maturity Scorecard")
    st.divider()

    st.markdown(
        f"""
        <div style="background-color:{tier_cfg['bg']};border-left:6px solid {tier_cfg['color']};
            padding:20px 24px;border-radius:6px;margin-bottom:24px;">
            <div style="font-size:14px;color:#555;margin-bottom:4px;">Overall Maturity Level</div>
            <div style="font-size:36px;font-weight:700;color:{tier_cfg['color']};">
                Level {tier} — {data['maturity_label']}
            </div>
            <div style="font-size:20px;color:#333;margin-top:4px;">
                Overall Score: <strong>{data['overall_score']:.2f} / 5.00</strong>
            </div>
        </div>
        """, unsafe_allow_html=True
    )

    tab_scorecard, tab_ai, tab_roadmap = st.tabs(["Scorecard", "AI Analysis", "Roadmap"])

    with tab_scorecard:
        col_chart, col_scores = st.columns([3, 2])
        with col_chart:
            st.subheader("Maturity Radar")
            st.plotly_chart(build_radar_chart(dim_scores), use_container_width=True)

        with col_scores:
            st.subheader("Dimension Scores")
            for dim in dim_scores:
                dim_cfg = TIER_CONFIG.get(dim["tier"], TIER_CONFIG[1])
                st.markdown(
                    f"""<div style="border-left:4px solid {dim_cfg['color']};padding:8px 12px;
                        margin-bottom:10px;background:{dim_cfg['bg']};border-radius:4px;">
                        <div style="font-size:13px;font-weight:600;color:#333;">{dim['label']}</div>
                        <div style="font-size:12px;color:#555;">Score: <strong>{dim['score']:.2f}</strong>
                        &nbsp;|&nbsp;<span style="color:{dim_cfg['color']};font-weight:600;">
                        {dim['tier_label']}</span></div></div>""",
                    unsafe_allow_html=True
                )

        st.divider()
        st.subheader("Recommendations by Dimension")
        for dim in dim_scores:
            dim_cfg = TIER_CONFIG.get(dim["tier"], TIER_CONFIG[1])
            recs = recommendations.get(dim["id"], [])
            with st.expander(
                f"{dim['label']} — Level {dim['tier']}: {dim['tier_label']}  |  Score: {dim['score']:.2f}",
                expanded=False
            ):
                for i, rec in enumerate(recs, 1):
                    st.markdown(
                        f"""<div style="display:flex;gap:12px;padding:10px 0;border-bottom:1px solid #f0f0f0;">
                            <div style="min-width:28px;height:28px;border-radius:50%;
                                background:{dim_cfg['color']};color:white;display:flex;
                                align-items:center;justify-content:center;font-weight:700;font-size:13px;">{i}</div>
                            <div style="color:#333;font-size:14px;padding-top:4px;">{rec}</div>
                        </div>""", unsafe_allow_html=True
                    )

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Back to Dashboard", use_container_width=True):
                st.session_state["page"] = "dashboard"
                st.rerun()
        with col2:
            try:
                from app.components.report import generate_pdf_report
                org_id = st.session_state.get("org_id")
                org_name = "Your Organisation"
                if org_id:
                    org_result = api_get(f"/organisations/{org_id}")
                    if org_result["ok"]:
                        org_name = org_result["data"].get("name", org_name)
                completed_at = data.get("created_at", "")[:10]
                with st.spinner("Generating PDF..."):
                    pdf_bytes = generate_pdf_report(
                        org_name=org_name,
                        overall_score=data["overall_score"],
                        maturity_tier=data["maturity_tier"],
                        maturity_label=data["maturity_label"],
                        dimension_scores=data["dimension_scores"],
                        recommendations=data["recommendations"],
                        completed_at=completed_at,
                    )
                st.download_button(
                    label="Download PDF Report", data=pdf_bytes,
                    file_name=f"ai_maturity_report_{completed_at}.pdf",
                    mime="application/pdf", use_container_width=True, type="primary",
                )
            except Exception as e:
                st.error(f"PDF error: {str(e)}")

    with tab_ai:
        st.subheader("AI-Powered Analysis")
        st.caption("Powered by Claude — personalised executive analysis based on your responses.")
        st.divider()

        if st.button("Generate AI Analysis", type="primary", key="gen_analysis"):
            with st.spinner("Claude is analysing your assessment... this may take 15-20 seconds."):
                r = api_post(f"/assessments/{assessment_id}/analyse", data={}, timeout=60)
            if r["ok"]:
                st.session_state["ai_analysis"] = r["data"]
            else:
                st.error(f"Analysis failed: {r['data'].get('detail', 'Unknown error')}")

        analysis = st.session_state.get("ai_analysis")
        if analysis:
            st.subheader("Executive Narrative")
            for key in ["executive_narrative", "executive_narrative_p2", "executive_narrative_p3"]:
                if key in analysis:
                    st.markdown(f"> {analysis[key]}")
                    st.write("")

            risks = analysis.get("cross_dimensional_risks", [])
            if risks:
                st.divider()
                st.subheader("Cross-Dimensional Risks")
                for risk in risks:
                    with st.expander(f"⚠️ {risk.get('risk', 'Risk')}", expanded=True):
                        st.write(risk.get("description", ""))
                        dims = risk.get("dimensions_affected", [])
                        if dims:
                            st.caption(f"Dimensions affected: {', '.join(dims)}")

            wins = analysis.get("quick_wins", [])
            if wins:
                st.divider()
                st.subheader("Quick Wins")
                for i, win in enumerate(wins, 1):
                    col1, col2 = st.columns([1, 10])
                    with col1:
                        st.markdown(
                            f'<div style="width:32px;height:32px;border-radius:50%;background:#27ae60;'
                            f'color:white;display:flex;align-items:center;justify-content:center;'
                            f'font-weight:700;">{i}</div>', unsafe_allow_html=True
                        )
                    with col2:
                        st.markdown(f"**{win.get('action', '')}**")
                        st.write(win.get("description", ""))
                        st.caption(f"Expected outcome: {win.get('expected_outcome', '')}")
                    st.write("")

            focus = analysis.get("ninety_day_focus", [])
            if focus:
                st.divider()
                st.subheader("90-Day Focus Areas")
                for item in sorted(focus, key=lambda x: x.get("priority", 0)):
                    st.markdown(
                        f"""<div style="border-left:4px solid #2980b9;padding:12px 16px;
                            margin-bottom:12px;background:#e8f4fb;border-radius:4px;">
                            <div style="font-size:11px;color:#2980b9;font-weight:600;
                                text-transform:uppercase;margin-bottom:4px;">
                                Priority {item.get('priority', '')}</div>
                            <div style="font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:6px;">
                                {item.get('focus_area', '')}</div>
                            <div style="font-size:13px;color:#333;margin-bottom:6px;">
                                {item.get('rationale', '')}</div>
                            <div style="font-size:12px;color:#555;">
                                <strong>Success metric:</strong> {item.get('success_metric', '')}</div>
                        </div>""", unsafe_allow_html=True
                    )
        else:
            st.info("Click 'Generate AI Analysis' to get a personalised executive analysis.")

    with tab_roadmap:
        st.subheader("AI-Generated 6-Month Roadmap")
        st.caption("Powered by Claude — a prioritised improvement roadmap based on your scores.")
        st.divider()

        if st.button("Generate Roadmap", type="primary", key="gen_roadmap"):
            with st.spinner("Claude is building your roadmap... this may take 15-20 seconds."):
                r = api_post(f"/assessments/{assessment_id}/roadmap", data={}, timeout=60)
            if r["ok"]:
                st.session_state["ai_roadmap"] = r["data"]
            else:
                st.error(f"Roadmap failed: {r['data'].get('detail', 'Unknown error')}")

        roadmap = st.session_state.get("ai_roadmap")
        if roadmap:
            target_score = roadmap.get("target_overall_score", 0)
            target_label = roadmap.get("target_maturity_label", "")
            st.markdown(
                f"""<div style="background:#e9f7ef;border-left:6px solid #27ae60;
                    padding:16px 20px;border-radius:6px;margin-bottom:20px;">
                    <div style="font-size:13px;color:#555;margin-bottom:4px;">Roadmap Target</div>
                    <div style="font-size:24px;font-weight:700;color:#27ae60;">
                        {target_label} — Score {target_score}</div>
                    <div style="font-size:14px;color:#333;margin-top:8px;">
                        {roadmap.get('roadmap_summary', '')}</div>
                </div>""", unsafe_allow_html=True
            )

            phase_colors = {1: "#e67e22", 2: "#2980b9", 3: "#27ae60"}
            for phase in roadmap.get("phases", []):
                phase_num = phase.get("phase", 0)
                phase_color = phase_colors.get(phase_num, "#95a5a6")
                st.markdown(
                 #   f"""<div style="background:{phase_color};color:white;padding:12px 16px;
                 #       border-radius:6px 6px 0 0;margin-top:20px;">
                 #       <div style="font-size:12px;font-weight:600;text-transform:uppercase;opacity:0.85;">
                 #          Phase {phase_num} — {phase.get('months', '')}</div>
                 #       <div style="font-size:18px;font-weight:700;">{phase.get('name', '')}</div>
                 #       <div style="font-size:13px;opacity:0.9;margin-top:4px;">{phase.get('theme', '')}</div>
                 #   </div>""", unsafe_allow_html=True
                    tier_badge(tier, data['maturity_label'], data['overall_score'])
                )
                for init in phase.get("initiatives", []):
                    effort = init.get("effort", "Medium")
                    impact = init.get("impact", "Medium")
                    with st.expander(
                        f"{init.get('title', 'Initiative')} — {init.get('dimension', '')}",
                        expanded=False
                    ):
                        st.write(init.get("description", ""))
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.markdown(
                                f'<span style="background:{EFFORT_COLORS.get(effort,"#95a5a6")};'
                                f'color:white;padding:2px 8px;border-radius:4px;font-size:12px;">'
                                f'Effort: {effort}</span>', unsafe_allow_html=True
                            )
                        with col2:
                            st.markdown(
                                f'<span style="background:{IMPACT_COLORS.get(impact,"#95a5a6")};'
                                f'color:white;padding:2px 8px;border-radius:4px;font-size:12px;">'
                                f'Impact: {impact}</span>', unsafe_allow_html=True
                            )
                        with col3:
                            st.caption(f"Owner: {init.get('owner', '')}")
                        with col4:
                            st.caption(f"Score improvement: +{init.get('score_improvement', 0)}")
                        deps = init.get("dependencies", "None")
                        if deps and deps != "None":
                            st.caption(f"Depends on: {deps}")

                target_scores = phase.get("target_dimension_scores", {})
                if target_scores:
                    cols = st.columns(len(target_scores))
                    for i, (dim_name, score) in enumerate(target_scores.items()):
                        with cols[i]:
                            st.metric(label=dim_name.split("&")[0].strip(), value=f"{score:.2f}")
        else:
            st.info("Click 'Generate Roadmap' to get a personalised 6-month improvement plan.")


# ------------------------------------------------------------------
# Admin panel
# ------------------------------------------------------------------

def show_admin_page():
    inject_styles()
    require_page_role("super_admin", "client_admin")
    render_sidebar()
    role = st.session_state.get("role", "")

    st.title("Admin Panel")
    st.divider()

    # Platform stats — super admin only
    if role == "super_admin":
        stats_result = api_get("/admin/stats")
        if stats_result["ok"]:
            stats = stats_result["data"]
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Organisations", stats["total_orgs"])
            with col2:
                st.metric("Users", stats["total_users"])
            with col3:
                st.metric("Total Assessments", stats["total_assessments"])
            with col4:
                st.metric("Completed", stats["completed_assessments"])
            with col5:
                avg = stats["average_score"]
                st.metric("Avg Score", f"{avg:.2f}" if avg else "N/A")
        st.divider()

    # Tabs based on role
    if role == "super_admin":
        tab_orgs, tab_users, tab_assessments = st.tabs(
            ["Organisations", "Users", "All Assessments"]
        )
    else:
        tab_orgs = None
        tab_users, tab_assessments = st.tabs(["Users", "Assessments"])

    # ------ Organisations tab (super admin only) ------
    if role == "super_admin" and tab_orgs:
        with tab_orgs:
            st.subheader("Organisations")
            col1, col2 = st.columns([3, 1])
            with col2:
                if st.button("+ New Organisation", use_container_width=True, type="primary"):
                    st.session_state["show_new_org_form"] = True

            if st.session_state.get("show_new_org_form"):
                with st.form("new_org_form"):
                    st.subheader("Create Organisation")
                    org_name = st.text_input("Name")
                    org_slug = st.text_input("Slug (URL-friendly, no spaces)")
                    org_industry = st.text_input("Industry (optional)")
                    submitted = st.form_submit_button("Create")
                    if submitted:
                        if not org_name or not org_slug:
                            st.error("Name and slug are required.")
                        else:
                            r = api_post("/admin/organisations", data={
                                "name": org_name,
                                "slug": org_slug.lower().replace(" ", "-"),
                                "industry": org_industry or None,
                            })
                            if r["ok"]:
                                st.success(f"Organisation '{org_name}' created.")
                                st.session_state["show_new_org_form"] = False
                                st.rerun()
                            else:
                                st.error(r["data"].get("detail", "Error creating organisation"))

            orgs_result = api_get("/admin/organisations")
            if orgs_result["ok"]:
                orgs = orgs_result["data"]
                for org in orgs:
                    col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 2, 1])
                    with col1:
                        status = "✅" if org["is_active"] else "❌"
                        st.write(f"{status} **{org['name']}**")
                        st.caption(f"/{org['slug']} · {org.get('industry', 'No industry')}")
                    with col2:
                        st.metric("Users", org["user_count"])
                    with col3:
                        st.metric("Assessments", org["assessment_count"])
                    with col4:
                        if org["latest_score"]:
                            st.write(f"Latest: **{org['latest_score']:.2f}** — {org['latest_tier']}")
                        else:
                            st.caption("No assessments yet")
                    with col5:
                        if org["is_active"]:
                            if st.button("Deactivate", key=f"deact_{org['id']}"):
                                api_patch(f"/admin/organisations/{org['id']}/deactivate")
                                st.rerun()
                    st.markdown("---")

    # ------ Users tab ------
    with tab_users:
        st.subheader("Users")
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("+ New User", use_container_width=True, type="primary"):
                st.session_state["show_new_user_form"] = True

        if st.session_state.get("show_new_user_form"):
            with st.form("new_user_form"):
                st.subheader("Create User")
                u_email = st.text_input("Email")
                u_password = st.text_input("Password", type="password")
                u_name = st.text_input("Full Name")

                if role == "super_admin":
                    u_role = st.selectbox("Role", ["assessor", "viewer", "client_admin", "super_admin"])
                    orgs_result = api_get("/admin/organisations")
                    org_options = {o["name"]: o["id"] for o in orgs_result["data"]} if orgs_result["ok"] else {}
                    org_options["None (Super Admin)"] = None
                    u_org_name = st.selectbox("Organisation", list(org_options.keys()))
                    u_org_id = org_options[u_org_name]
                else:
                    u_role = st.selectbox("Role", ["assessor", "viewer"])
                    u_org_id = st.session_state.get("org_id")

                submitted = st.form_submit_button("Create User")
                if submitted:
                    if not u_email or not u_password:
                        st.error("Email and password are required.")
                    else:
                        r = api_post("/admin/users", data={
                            "email": u_email,
                            "password": u_password,
                            "full_name": u_name or None,
                            "role": u_role,
                            "organisation_id": u_org_id,
                        })
                        if r["ok"]:
                            st.success(f"User '{u_email}' created.")
                            st.session_state["show_new_user_form"] = False
                            st.rerun()
                        else:
                            st.error(r["data"].get("detail", "Error creating user"))

        users_result = api_get("/admin/users")
        if users_result["ok"]:
            users = users_result["data"]
            for u in users:
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                with col1:
                    status = "✅" if u["is_active"] else "❌"
                    st.write(f"{status} **{u['email']}**")
                    st.caption(u.get("full_name") or "No name")
                with col2:
                    st.caption(f"Role: {ROLE_LABELS.get(u['role'], u['role'])}")
                    st.caption(f"Org: {u.get('organisation_name') or 'None'}")
                with col3:
                    last_login = u.get("last_login", "")
                    if last_login:
                        st.caption(f"Last login: {last_login[:10]}")
                    else:
                        st.caption("Never logged in")
                with col4:
                    if u["is_active"]:
                        if st.button("Disable", key=f"dis_{u['id']}"):
                            api_patch(f"/admin/users/{u['id']}", data={"is_active": False})
                            st.rerun()
                    else:
                        if st.button("Enable", key=f"en_{u['id']}"):
                            api_patch(f"/admin/users/{u['id']}", data={"is_active": True})
                            st.rerun()
                st.markdown("---")

    # ------ Assessments tab ------
    with tab_assessments:
        st.subheader("Assessments")

        if role == "super_admin":
            assess_result = api_get("/admin/assessments")
        else:
            assess_result = api_get("/assessments")

        if assess_result["ok"]:
            assessments = assess_result["data"]
            for a in assessments:
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                with col1:
                    st.write(f"**{a.get('title', 'Assessment')}**")
                    if role == "super_admin":
                        st.caption(f"Org: {a.get('organisation', a.get('organisation_id', ''))}")
                with col2:
                    status_colors = {
                        "completed": "#27ae60",
                        "in_progress": "#e67e22",
                        "draft": "#95a5a6"
                    }
                    status = a.get("status", "")
                    color = status_colors.get(status, "#95a5a6")
                    st.markdown(
                        f'<span style="color:{color};font-weight:600;">{status.title()}</span>',
                        unsafe_allow_html=True
                    )
                    date = a.get("completed_at") or a.get("created_at", "")
                    if date:
                        st.caption(date[:10])
                with col3:
                    score = a.get("overall_score")
                    tier = a.get("maturity_label")
                    if score:
                        st.write(f"Score: **{score:.2f}** — {tier}")
                    else:
                        st.caption("Not scored yet")
                with col4:
                    if a.get("status") == "completed":
                        if st.button("View", key=f"adm_sc_{a['id']}"):
                            st.session_state["scorecard_assessment_id"] = a["id"]
                            st.session_state["ai_analysis"] = None
                            st.session_state["ai_roadmap"] = None
                            st.session_state["page"] = "scorecard"
                            st.rerun()
                st.markdown("---")


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

def show_history_page():
    inject_styles()
    render_sidebar()
    st.title("Assessment History")
    st.caption("Track your AI maturity progress over time.")
    st.divider()

    result = api_get("/assessments/history/all")
    if not result["ok"]:
        st.error("Could not load history.")
        return

    history = result["data"]
    if len(history) < 1:
        st.info("No completed assessments yet.")
        return
    if len(history) < 2:
        st.warning("Complete at least 2 assessments to see trend charts.")

    st.subheader("Overall Score Trend")
    dates = [h["completed_at"] for h in history]
    scores = [h["overall_score"] for h in history]

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=dates, y=scores, mode="lines+markers+text",
        text=[f"{s:.2f}" for s in scores], textposition="top center",
        line=dict(color="#2980b9", width=3), marker=dict(size=10, color="#2980b9"),
    ))
    for low, high, color, label in [
        (1.0, 1.79, "#fdecea", "Ad Hoc"), (1.80, 2.59, "#fef3e2", "Developing"),
        (2.60, 3.39, "#fefde2", "Defined"), (3.40, 4.19, "#e8f4fb", "Managed"),
        (4.20, 5.00, "#e9f7ef", "Optimizing"),
    ]:
        fig_trend.add_hrect(y0=low, y1=high, fillcolor=color, opacity=0.4,
                           line_width=0, annotation_text=label,
                           annotation_position="left", annotation_font_size=9)
    fig_trend.update_layout(
        yaxis=dict(range=[0, 5.2], title="Score", gridcolor="#ecf0f1"),
        xaxis=dict(title="Assessment Date", gridcolor="#ecf0f1"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=350, margin=dict(t=20, b=40, l=60, r=120), showlegend=False,
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    if len(history) >= 2:
        st.divider()
        st.subheader("Dimension Score Comparison")
        dim_labels = [d["label"] for d in history[0]["dimension_scores"]]
        dim_ids = [d["id"] for d in history[0]["dimension_scores"]]
        colors_list = ["#95a5a6", "#2980b9", "#27ae60", "#e67e22", "#8e44ad"]

        fig_bar = go.Figure()
        for i, h in enumerate(history):
            dim_score_map = {d["id"]: d["score"] for d in h["dimension_scores"]}
            bar_scores = [dim_score_map.get(did, 0) for did in dim_ids]
            fig_bar.add_trace(go.Bar(
                name=f"{h['completed_at']} ({h['maturity_label']})",
                x=dim_labels, y=bar_scores,
                marker_color=colors_list[i % len(colors_list)],
                text=[f"{s:.2f}" for s in bar_scores], textposition="outside",
            ))
        fig_bar.update_layout(
            barmode="group",
            yaxis=dict(range=[0, 5.5], title="Score", gridcolor="#ecf0f1"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=400, margin=dict(t=20, b=100, l=60, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=-0.35),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()
        st.subheader("Score Changes")
        prev = history[-2]
        curr = history[-1]
        prev_map = {d["id"]: d for d in prev["dimension_scores"]}
        curr_map = {d["id"]: d for d in curr["dimension_scores"]}
        overall_delta = curr["overall_score"] - prev["overall_score"]
        delta_color = "#27ae60" if overall_delta >= 0 else "#e74c3c"
        delta_arrow = "▲" if overall_delta >= 0 else "▼"

        st.markdown(
            f"""<div style="padding:16px 20px;background:#f8f9fa;border-radius:6px;margin-bottom:16px;">
                <span style="font-size:14px;color:#555;">Overall Score Change</span><br>
                <span style="font-size:28px;font-weight:700;color:{delta_color};">
                    {delta_arrow} {abs(overall_delta):.2f}</span>
                <span style="font-size:14px;color:#555;margin-left:8px;">
                    {prev['overall_score']:.2f} → {curr['overall_score']:.2f}
                    &nbsp;|&nbsp; {prev['maturity_label']} → {curr['maturity_label']}</span>
            </div>""", unsafe_allow_html=True
        )
        for dim_id in dim_ids:
            prev_d = prev_map.get(dim_id, {})
            curr_d = curr_map.get(dim_id, {})
            delta = curr_d.get("score", 0) - prev_d.get("score", 0)
            arrow = "▲" if delta >= 0 else "▼"
            color = "#27ae60" if delta >= 0 else "#e74c3c"
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                st.write(curr_d.get("label", dim_id))
            with col2:
                st.write(f"{prev_d.get('score', 0):.2f}")
            with col3:
                st.write(f"{curr_d.get('score', 0):.2f}")
            with col4:
                st.markdown(
                    f'<span style="color:{color};font-weight:700;">{arrow} {abs(delta):.2f}</span>',
                    unsafe_allow_html=True
                )

    st.divider()
    st.subheader("All Assessments")
    col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
    with col1: st.markdown("**Date**")
    with col2: st.markdown("**Score**")
    with col3: st.markdown("**Maturity Level**")
    with col4: st.markdown("**Action**")
    st.markdown("---")

    for h in reversed(history):
        tier_cfg = TIER_CONFIG.get(h["maturity_tier"], TIER_CONFIG[1])
        col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
        with col1: st.write(h["completed_at"])
        with col2: st.write(f"{h['overall_score']:.2f}")
        with col3:
            st.markdown(
                f'<span style="color:{tier_cfg["color"]};font-weight:600;">'
                f'Level {h["maturity_tier"]}: {h["maturity_label"]}</span>',
                unsafe_allow_html=True
            )
        with col4:
            if st.button("Scorecard", key=f"hist_{h['assessment_id']}"):
                st.session_state["scorecard_assessment_id"] = h["assessment_id"]
                st.session_state["ai_analysis"] = None
                st.session_state["ai_roadmap"] = None
                st.session_state["page"] = "scorecard"
                st.rerun()


# ------------------------------------------------------------------
# Router
# ------------------------------------------------------------------

if "token" not in st.session_state:
    show_login_page()
else:
    page = st.session_state.get("page", "dashboard")
    if page == "assessment":
        show_assessment_page()
    elif page == "scorecard":
        show_scorecard_page()
    elif page == "history":
        show_history_page()
    elif page == "admin":
        show_admin_page()
    else:
        show_dashboard()