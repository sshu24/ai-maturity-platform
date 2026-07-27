import os
import httpx
import json

@router.post("/{assessment_id}/analyse")
def analyse_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calls Claude API to generate AI-powered analysis of the assessment.
    Returns structured narrative, risks, quick wins, and 90-day focus areas.
    """
    import httpx
    import json

    assessment = _get_assessment_or_404(assessment_id, db, current_user)

    if assessment.status != "completed":
        raise HTTPException(status_code=400, detail="Assessment must be completed first")

    result = db.query(Result).filter(
        Result.assessment_id == assessment_id
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    responses = db.query(Response).filter(
        Response.assessment_id == assessment_id
    ).all()

    bank = load_question_bank()

    # Build structured context for Claude
    dimension_context = []
    for dim in bank.dimensions:
        dim_responses = [r for r in responses if r.dimension == dim.id]
        dim_score_data = next(
            (d for d in result.dimension_scores if d["id"] == dim.id), {}
        )
        questions_answered = []
        for q in dim.questions:
            resp = next((r for r in dim_responses if r.question_id == q.id), None)
            if resp:
                questions_answered.append({
                    "question": q.text,
                    "answer": resp.answer_label,
                    "score": resp.answer_value,
                })
        dimension_context.append({
            "dimension": dim.label,
            "score": dim_score_data.get("score", 0),
            "tier": dim_score_data.get("tier_label", ""),
            "responses": questions_answered,
        })

    prompt = f"""You are an expert AI platform maturity consultant. 
You have just completed an assessment of an organisation's AI maturity across 6 dimensions.

Here are the assessment results:

Overall Score: {result.overall_score}/5.0
Maturity Level: {result.maturity_label} (Level {result.maturity_tier})

Dimension Scores and Responses:
{json.dumps(dimension_context, indent=2)}

Based on this assessment data, provide a structured analysis in the following JSON format:
{{
    "executive_narrative": "3 paragraphs of executive-level narrative summarising the organisation's AI maturity, key strengths, and critical gaps. Be specific and reference actual scores and answers.",
    "cross_dimensional_risks": [
        {{
            "risk": "Risk title",
            "description": "2-3 sentence description of the risk and its business impact",
            "dimensions_affected": ["dimension1", "dimension2"]
        }}
    ],
    "quick_wins": [
        {{
            "action": "Specific action title",
            "description": "Why this is high impact and low effort given current maturity",
            "expected_outcome": "What improvement this will drive"
        }}
    ],
    "ninety_day_focus": [
        {{
            "priority": 1,
            "focus_area": "Focus area title",
            "rationale": "Why this should be the priority in the next 90 days",
            "success_metric": "How to measure success"
        }}
    ]
}}

Provide exactly 3 cross_dimensional_risks, 3 quick_wins, and 3 ninety_day_focus items.
Return ONLY valid JSON, no markdown, no preamble."""

    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Claude API error: {response.text}"
            )

        content = response.json()["content"][0]["text"]
        analysis = json.loads(content)
        return analysis

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse Claude response as JSON: {str(e)}"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Claude API timed out. Please try again."
        )