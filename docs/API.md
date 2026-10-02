# API Reference

The FastAPI backend serves everything the Streamlit UI does, and any other client can call it directly. This page documents API version `0.1.0`.

| Environment | Base URL | Interactive docs |
|-------------|----------|------------------|
| Local (Docker Compose) | `http://localhost:8000` | `http://localhost:8000/docs` |
| AWS | The CloudFront URL from the `CloudFrontUrl` stack output | Disabled (`/docs` is only served when `ENV=development`) |

When the docs are enabled, the full OpenAPI schema is also served at `/openapi.json`.

---

## Conventions

**Authentication.** Every endpoint except `POST /auth/login`, `GET /health` and `GET /questions` needs a JWT bearer token:

```
Authorization: Bearer <access_token>
```

Tokens are HS256-signed with `SECRET_KEY` and expire after `ACCESS_TOKEN_EXPIRE_MINUTES`, which defaults to 480 (8 hours). There are no refresh tokens: once a token expires, log in again. The user is reloaded from the database on every request, so deactivating a user takes effect at once, even if their token hasn't expired.

**Errors.** Errors use FastAPI's standard shape:

```json
{ "detail": "Human-readable message" }
```

Validation failures (422) return `detail` as a list of field errors.

| Status | Meaning |
|--------|---------|
| 400 | The request is valid, but the resource is in the wrong state (for example, the assessment isn't completed yet) |
| 401 | Token is missing, invalid or expired, or the user is inactive |
| 403 | Your role isn't allowed, or the resource belongs to another organisation |
| 404 | Not found |
| 409 | Conflict (duplicate email or slug, or an active assessment already exists) |
| 422 | Request body or parameter validation failed |

**IDs** are UUID strings. **Timestamps** are naive UTC in ISO 8601, except where noted as `YYYY-MM-DD` strings. **Pagination**: none; list endpoints return every row.

---

## Roles and tenancy

| Role | Scope |
|------|-------|
| `super_admin` | Every organisation. Not tied to any org (`organisation_id` is `null`). |
| `client_admin` | Their own organisation: users, assessments, results |
| `assessor` | Their own organisation: can create, answer and submit assessments |
| `viewer` | Their own organisation, read-only, except that it can trigger AI generation (see [Known gaps](#known-gaps)) |

In the endpoint tables below, **Roles** lists who may call the endpoint. "Any" means any authenticated user. The access checks are written into each handler, not applied centrally: if a non-super-admin requests a resource from another organisation, the endpoint returns `403`.

---

## System

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Liveness check. Returns `{"status": "ok", "env": "<ENV>"}`. Used by the ALB health check. |
| GET | `/questions` | None | The full question bank (6 dimensions × 7 questions), loaded from `app/config/questions.yaml`. |

`GET /questions` response (abridged):

```json
{
  "version": "1.0",
  "total_questions": 42,
  "dimensions": [
    {
      "id": "data_infrastructure",
      "label": "Data & Data Infrastructure",
      "description": "...",
      "weight": 1.0,
      "questions": [
        {
          "id": "di_01",
          "text": "How is your training and inference data primarily stored and managed?",
          "type": "multiple_choice",
          "weight": 1.0,
          "options": [{ "label": "Data is scattered across ...", "value": 1 }]
        }
      ]
    }
  ]
}
```

---

## Auth — `/auth`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| POST | `/auth/login` | None | Exchange an email and password for a token |
| GET | `/auth/me` | Any | The current user |

### `POST /auth/login`

The body is **form-encoded** (OAuth2 password flow), not JSON. The email goes in the `username` field.

```bash
curl -X POST http://localhost:8000/auth/login \
  -d 'username=admin@projecta.com' -d 'password=changeme123!'
```

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "role": "super_admin",
  "full_name": "Super Admin",
  "org_id": null
}
```

Returns `401 Incorrect email or password` if the credentials are wrong or the user is inactive. A successful login updates `last_login`.

### `GET /auth/me`

```json
{ "id": "…", "email": "…", "full_name": "…", "role": "assessor", "org_id": "…" }
```

---

## Assessments — `/assessments`

### Lifecycle

```
draft ──(first answer saved)──▶ in_progress ──(POST /submit)──▶ completed
```

An organisation can have only **one** `draft` or `in_progress` assessment at a time. Completed assessments can't be changed or deleted.

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| POST | `/assessments` | super_admin, client_admin, assessor | Create a draft assessment for the caller's org |
| GET | `/assessments` | Any | List assessments (all orgs for super_admin, otherwise the caller's org), newest first |
| GET | `/assessments/active` | Any | The caller's org's open assessment with its answers and progress, or `null` |
| GET | `/assessments/history/all` | Any | Completed assessments with scores, oldest first (for trend charts) |
| GET | `/assessments/{id}` | Any (same org) | The assessment with its answers and progress |
| POST | `/assessments/{id}/responses` | super_admin, client_admin, assessor (same org) | Save an answer (an upsert keyed on question) |
| POST | `/assessments/{id}/submit` | super_admin, client_admin, assessor (same org) | Score the assessment and mark it completed |
| GET | `/assessments/{id}/result` | Any (same org) | The full scorecard and recommendations |
| GET | `/assessments/{id}/result/summary` | Any (same org) | Scores only, or `null` if not scored |
| DELETE | `/assessments/{id}` | super_admin, client_admin (same org) | Delete a draft or in-progress assessment. Returns `204`. |
| POST | `/assessments/{id}/analyse` | Any (same org) | Start the AI executive analysis, or get the cached one |
| GET | `/assessments/{id}/analyse/status` | Any (same org) | Poll the AI analysis job |
| POST | `/assessments/{id}/roadmap` | Any (same org) | Start the AI 6-month roadmap, or get the cached one |
| GET | `/assessments/{id}/roadmap/status` | Any (same org) | Poll the AI roadmap job |

### `POST /assessments`

```json
{ "title": "AI Maturity Assessment" }
```

The `title` field is optional. Returns an `Assessment`. Errors:
- `400`: the caller has no organisation (for example, a super admin).
- `409`: the org already has an open assessment. The message includes its ID.

**Assessment**

```json
{
  "id": "…", "title": "AI Maturity Assessment", "status": "draft",
  "organisation_id": "…", "created_by_id": "…",
  "started_at": null, "completed_at": null, "created_at": "2026-10-01T10:00:00"
}
```

### `GET /assessments/{id}` and `GET /assessments/active`

```json
{
  "assessment": { "...": "Assessment" },
  "responses": [
    { "id": "…", "question_id": "di_01", "dimension": "data_infrastructure",
      "answer_value": 3, "answer_label": "A managed data lake ..." }
  ],
  "completion": {
    "data_infrastructure": { "label": "Data & Data Infrastructure", "total": 7, "answered": 3, "complete": false, "percent": 43 },
    "_overall": { "total": 42, "answered": 3, "complete": false, "percent": 7 }
  }
}
```

### `POST /assessments/{id}/responses`

```json
{ "question_id": "di_01", "answer_value": 3, "answer_label": "A managed data lake ..." }
```

Saving an answer to a question that already has one replaces it. The first saved answer moves the assessment from `draft` to `in_progress` and sets `started_at`. Errors:
- `400`: the assessment is completed, or `answer_value` isn't one of the question's option values.
- `404`: unknown `question_id`.

### `POST /assessments/{id}/submit`

This checks that all 42 questions are answered. It then computes the weighted scores and stores a `Result` with the tier-based recommendations, and marks the assessment `completed`. It returns the updated `Assessment`. Errors:
- `400 Assessment already completed`.
- `400 Incomplete dimensions: Data & Data Infrastructure (5/7), …`.

### `GET /assessments/{id}/result`

```json
{
  "id": "…", "assessment_id": "…",
  "overall_score": 2.43, "maturity_tier": 2, "maturity_label": "Developing",
  "dimension_scores": [
    { "id": "data_infrastructure", "label": "Data & Data Infrastructure", "score": 2.14, "tier": 2, "tier_label": "Developing" }
  ],
  "recommendations": { "data_infrastructure": ["3 static recommendations for this dimension's tier", "…", "…"] },
  "created_at": "2026-10-01T10:30:00"
}
```

Returns `400` if the assessment isn't completed.

**Maturity tiers.** Scores run from 1.0 to 5.0, rounded to 2 decimals.

| Tier | Label | Range |
|------|-------|-------|
| 1 | Ad Hoc | 1.00 – 1.79 |
| 2 | Developing | 1.80 – 2.59 |
| 3 | Defined | 2.60 – 3.39 |
| 4 | Managed | 3.40 – 4.19 |
| 5 | Optimizing | 4.20 – 5.00 |

### `GET /assessments/history/all`

```json
[
  { "assessment_id": "…", "title": "…", "completed_at": "2026-10-01",
    "overall_score": 2.43, "maturity_tier": 2, "maturity_label": "Developing",
    "dimension_scores": [ "...same shape as in the result..." ] }
]
```

### AI analysis and roadmap

Generation typically takes tens of seconds, so it runs as a background job and the client polls for the result.

```
POST /analyse ──▶ {"status":"generating"} ──▶ poll GET /analyse/status every ~5s
                                              ├─ {"status":"complete","data":{…}}
                                              └─ {"status":"failed","error":"…"}
```

**POST `/assessments/{id}/analyse`** or **`/roadmap`**

| Query param | Default | Effect |
|-------------|---------|--------|
| `force` | `false` | `true` regenerates even when a completed result is cached |

These POSTs always return a **JobStatus**:

```json
{ "status": "pending | generating | complete | failed", "data": { } , "error": "…" }
```

- If a completed result is cached and `force` is false, the response is `{"status": "complete", "data": {…}}` and no new job starts.
- If a job is already running, the response is `{"status": "generating"}` and no second job starts. This holds even with `force=true`.
- A job still `generating` after `AI_JOB_STALE_SECONDS` (600 seconds by default), for example because the container restarted, counts as dead and is restarted on the next POST.
- Returns `400` if the assessment isn't completed, and `404` if it has no result.

**GET `/assessments/{id}/analyse/status`** or **`/roadmap/status`** return the same JobStatus. They're cheap and don't start anything. When a job fails, `error` holds a message that is safe to show users, for example:
- "Claude is rate limited right now. Please try again in a minute."
- "The Anthropic API key is invalid."
- "Claude's response was cut off before it finished. Please try again."

A regeneration can fail. When it does, `data` still holds the previous successful output and `status` is `failed`.

**Analysis `data`**

```json
{
  "executive_narrative": "Paragraph 1 …",
  "executive_narrative_p2": "Paragraph 2 …",
  "executive_narrative_p3": "Paragraph 3 …",
  "cross_dimensional_risks": [ { "risk": "…", "description": "…", "dimensions_affected": ["…"] } ],
  "quick_wins": [ { "action": "…", "description": "…", "expected_outcome": "…" } ],
  "ninety_day_focus": [ { "priority": 1, "focus_area": "…", "rationale": "…", "success_metric": "…" } ]
}
```

Each list contains 3 items.

**Roadmap `data`**

```json
{
  "roadmap_summary": "…",
  "target_overall_score": 3.4,
  "target_maturity_label": "Managed",
  "estimated_business_value": "…",
  "phases": [
    {
      "phase": 1, "name": "Foundation", "months": "Months 1-2",
      "theme": "…", "business_objective": "…",
      "initiatives": [
        {
          "title": "…", "description": "…", "dimension": "Data & Data Infrastructure",
          "owner": "Head of Data", "effort": "Low|Medium|High", "impact": "Low|Medium|High",
          "dependencies": "None", "score_improvement": 0.5,
          "business_value": "…", "cost_of_inaction": "…", "roi_signal": "…"
        }
      ],
      "target_dimension_scores": { "Data & Data Infrastructure": 2.8 },
      "phase_business_outcome": "…"
    }
  ]
}
```

There are 3 phases, each with 3–4 initiatives.

---

## Organisations — `/organisations`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| POST | `/organisations` | super_admin | Create an organisation |
| GET | `/organisations` | super_admin | List organisations |
| GET | `/organisations/{org_id}` | Any (own org, or super_admin) | Get an organisation |
| POST | `/organisations/{org_id}/users` | super_admin, client_admin (own org) | Create a user in the org |
| GET | `/organisations/{org_id}/users` | super_admin, client_admin (own org) | List the org's users |

**Create organisation:** `{"name": "Acme", "slug": "acme", "industry": "Retail"}`. Returns `409` if the slug is taken.

**Organisation**

```json
{ "id": "…", "name": "Acme", "slug": "acme", "industry": "Retail", "is_active": true }
```

**Create user:** `{"email": "…", "password": "…", "full_name": "…", "role": "assessor"}`. Errors:
- `409`: the email is already taken.
- `400`: the role is `super_admin`.

---

## Admin — `/admin`

This router backs the Admin Panel in the UI.

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/admin/stats` | super_admin | Platform totals |
| GET | `/admin/organisations` | super_admin | Organisations with user and assessment counts and the latest score |
| POST | `/admin/organisations` | super_admin | Create an organisation (same body as above) |
| PATCH | `/admin/organisations/{org_id}/deactivate` | super_admin | Set `is_active = false`. Returns `{"status": "deactivated", "org_id": "…"}` |
| GET | `/admin/assessments` | super_admin | All assessments with org name and score |
| GET | `/admin/users` | super_admin, client_admin | Users (all for super_admin, otherwise the caller's org) |
| POST | `/admin/users` | super_admin, client_admin | Create a user |
| PATCH | `/admin/users/{user_id}` | super_admin, client_admin | Update a user |

**`GET /admin/stats`**

```json
{ "total_orgs": 4, "total_users": 17, "total_assessments": 9, "completed_assessments": 6, "average_score": 2.71 }
```

**OrgSummary** (`GET` and `POST /admin/organisations`)

```json
{ "id": "…", "name": "…", "slug": "…", "industry": "…", "is_active": true,
  "user_count": 5, "assessment_count": 2, "latest_score": 2.43, "latest_tier": "Developing" }
```

**UserSummary**

```json
{ "id": "…", "email": "…", "full_name": "…", "role": "assessor",
  "organisation_id": "…", "organisation_name": "Acme", "is_active": true, "last_login": null }
```

**`POST /admin/users`**

```json
{ "email": "…", "password": "…", "full_name": "…", "role": "assessor", "organisation_id": "…" }
```

A client admin may only create users in their own org, and only with the `assessor` or `viewer` role. Otherwise the request returns `403`.

**`PATCH /admin/users/{user_id}`**: send only the fields you want to change.

```json
{ "full_name": "…", "role": "viewer", "is_active": false, "organisation_id": "…" }
```

| Rule | Error |
|------|-------|
| A client admin can only edit users in their own org | `403 Access denied` |
| A client admin can't assign `super_admin` or `client_admin` | `403 Cannot assign this role` |
| Only a super admin can change `organisation_id` | `403 Only super admins can change a user's organisation` |

---

## Known gaps

These are current behaviours, recorded here so API clients and future changes don't trip over them:

- **Viewers can trigger AI generation.** The `/analyse` and `/roadmap` POSTs require only an authenticated same-org user. Each regeneration with `force=true` costs Claude API usage.
- **`answer_label` is stored as sent.** It isn't checked against the label of the option the client chose. Scoring uses only `answer_value`, which is validated.
- **The two user-creation endpoints apply different rules.** `POST /organisations/{org_id}/users` lets a client admin create another `client_admin`, but `POST /admin/users` doesn't.
- **Organisations can be created through two endpoints.** `POST /organisations` and `POST /admin/organisations` overlap.
- **Deactivating an org doesn't block its users.** Logins and other requests from that org's users still work.
- **There is no rate limiting, pagination, or refresh token.**
