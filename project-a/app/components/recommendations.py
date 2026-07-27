"""
Static recommendations per dimension per maturity tier.
Each entry is a list of 3 actionable recommendations.
Keyed by: RECOMMENDATIONS[dimension_id][tier] -> list[str]
"""

RECOMMENDATIONS: dict[str, dict[int, list[str]]] = {

    "data_infrastructure": {
        1: [
            "Establish a centralised data inventory — catalogue all data sources, owners, and formats currently in use across teams.",
            "Implement a basic data lake or warehouse (e.g. AWS S3 + Athena, or Snowflake) to consolidate scattered data assets.",
            "Define and document data ownership policies, including who is responsible for quality, access, and retention.",
        ],
        2: [
            "Introduce a data quality framework with automated validation checks on ingestion pipelines.",
            "Adopt an orchestration tool (e.g. Apache Airflow or Prefect) to replace manual and script-based pipeline execution.",
            "Implement role-based access controls and begin logging data access for audit purposes.",
        ],
        3: [
            "Deploy a feature store (e.g. Feast, Tecton) to enable feature reuse and reduce duplication across ML teams.",
            "Introduce automated data lineage tracking using tools such as OpenLineage or DataHub.",
            "Establish data SLAs with automated alerting when quality thresholds are breached.",
        ],
        4: [
            "Move towards a self-service data platform where teams can discover, access, and use data without central bottlenecks.",
            "Implement real-time data quality monitoring with anomaly detection across all critical pipelines.",
            "Introduce data contracts between producers and consumers to enforce schema and quality agreements.",
        ],
        5: [
            "Explore a data mesh architecture to distribute data ownership while maintaining centralised governance standards.",
            "Implement automated data product management with discoverability, versioning, and SLA reporting.",
            "Continuously benchmark data infrastructure costs and optimise with tiered storage and intelligent archiving.",
        ],
    },

    "model_development": {
        1: [
            "Adopt an experiment tracking tool (e.g. MLflow or Weights & Biases) immediately — every experiment should be logged.",
            "Establish a shared model registry with basic versioning so models are never lost or overwritten.",
            "Introduce containerised development environments (Docker) to eliminate 'works on my machine' issues.",
        ],
        2: [
            "Build a basic CI/CD pipeline for ML that automates testing and deployment of models to a staging environment.",
            "Define a standard model evaluation framework with performance baselines that must be met before deployment.",
            "Introduce peer review for model code and experiment results as part of the development workflow.",
        ],
        3: [
            "Integrate ML CI/CD pipelines with your existing software delivery toolchain for consistent governance.",
            "Implement automated data drift and model performance monitoring in production using tools like Evidently AI.",
            "Establish retraining triggers based on performance degradation thresholds rather than fixed schedules.",
        ],
        4: [
            "Implement shadow mode deployments and A/B testing infrastructure for all new model releases.",
            "Automate hyperparameter optimisation as part of the training pipeline using tools like Optuna or Ray Tune.",
            "Build a model performance dashboard visible to both technical and business stakeholders.",
        ],
        5: [
            "Invest in online learning capabilities for models that need to adapt to real-time data streams.",
            "Implement automated model cards generation as part of every deployment pipeline.",
            "Explore foundation model fine-tuning strategies to accelerate model development across teams.",
        ],
    },

    "platform_infrastructure": {
        1: [
            "Move AI workloads to a managed cloud ML platform (e.g. AWS SageMaker, GCP Vertex AI) to reduce operational overhead.",
            "Implement infrastructure as code (Terraform or AWS CDK) for all AI-related resources from day one.",
            "Define compute budgets and set up basic cloud cost alerts to prevent runaway spending.",
        ],
        2: [
            "Introduce a workflow orchestration tool (e.g. Kubeflow, Airflow) to replace manual job execution.",
            "Implement centralised logging and metrics using a managed observability stack (e.g. Datadog, Grafana + Prometheus).",
            "Containerise all model serving using Docker and deploy behind a managed API gateway.",
        ],
        3: [
            "Implement auto-scaling for both training and inference workloads to handle variable demand cost-effectively.",
            "Introduce GPU spot instance strategies for training workloads to reduce compute costs by 60-80%.",
            "Build a unified serving platform that supports both real-time and batch inference workloads.",
        ],
        4: [
            "Implement multi-region redundancy for production AI systems with defined RTO and RPO targets.",
            "Build AI-specific observability including prediction drift monitoring, feature distribution tracking, and latency SLAs.",
            "Introduce FinOps practices for AI — showback reports, per-team cost allocation, and optimisation reviews.",
        ],
        5: [
            "Evaluate a Kubernetes-based ML platform (e.g. Kubeflow on EKS) for full workload portability and cost optimisation.",
            "Implement chaos engineering practices for AI systems to validate resilience and recovery processes.",
            "Build an internal developer platform that abstracts infrastructure complexity and enables self-service AI deployment.",
        ],
    },

    "governance_risk": {
        1: [
            "Develop and publish a foundational AI ethics policy covering fairness, transparency, accountability, and privacy.",
            "Conduct an immediate audit of all AI systems in production to identify and document potential risk areas.",
            "Assign an AI risk owner — a named individual accountable for governance across all AI initiatives.",
        ],
        2: [
            "Integrate bias assessment into the model development lifecycle for all models that make decisions affecting people.",
            "Begin producing model cards for all new production models documenting purpose, limitations, and training data.",
            "Establish an AI incident response process with clear escalation paths and a defined post-mortem template.",
        ],
        3: [
            "Automate bias and fairness checks as part of the CI/CD pipeline using tools like Fairlearn or IBM AI Fairness 360.",
            "Map all AI systems against applicable regulations (GDPR, EU AI Act, sector-specific rules) and address gaps.",
            "Implement decision audit logging for all AI systems making consequential decisions.",
        ],
        4: [
            "Establish an AI governance committee with cross-functional representation including legal, risk, and product.",
            "Implement real-time explainability for high-stakes models using SHAP or LIME integrated into the serving layer.",
            "Conduct regular third-party audits of high-risk AI systems and publish findings internally.",
        ],
        5: [
            "Build automated regulatory compliance reporting to reduce manual effort and ensure continuous adherence.",
            "Implement a responsible AI maturity programme with measurable targets and executive accountability.",
            "Contribute to industry standards and open-source responsible AI tooling to build reputation and attract talent.",
        ],
    },

    "team_culture": {
        1: [
            "Define an AI talent strategy — identify the roles needed (ML engineers, data engineers, MLOps) and begin hiring or upskilling.",
            "Establish an AI centre of excellence or working group to build internal momentum and share early learnings.",
            "Secure executive sponsorship for AI initiatives with a named C-level champion and dedicated budget.",
        ],
        2: [
            "Create a structured AI learning programme with a dedicated budget and curated learning paths per role.",
            "Introduce regular AI showcases or demo days to build internal awareness and celebrate successes.",
            "Begin embedding ML engineers within product teams rather than keeping them siloed in a central team.",
        ],
        3: [
            "Transition to a federated AI operating model with embedded practitioners supported by a central platform team.",
            "Launch an AI literacy programme for non-technical staff covering AI capabilities, limitations, and ethical implications.",
            "Establish blameless post-mortems for failed AI experiments to build a learning culture.",
        ],
        4: [
            "Build internal AI communities of practice with regular knowledge sharing, mentoring, and external speaker events.",
            "Develop AI career pathways to retain top talent and provide clear progression for ML practitioners.",
            "Measure and report on AI culture metrics — participation in learning, experiment velocity, cross-team collaboration.",
        ],
        5: [
            "Position AI capability as a key employer brand differentiator to attract top-tier talent.",
            "Establish a university or research partnership programme to maintain access to cutting-edge techniques.",
            "Create an internal AI fellows programme to recognise and retain deep technical expertise.",
        ],
    },

    "business_integration": {
        1: [
            "Identify 2-3 high-value, low-risk AI use cases with clear business outcomes and start there — avoid boiling the ocean.",
            "Define success metrics for every AI initiative before development begins, not after.",
            "Establish a cross-functional AI steering group with business and technical representation to align priorities.",
        ],
        2: [
            "Build a formal AI project intake and prioritisation process tied to business OKRs.",
            "Implement basic ROI tracking for all AI projects in production — revenue impact, cost savings, or efficiency gains.",
            "Introduce structured change management for AI rollouts to drive adoption and manage resistance.",
        ],
        3: [
            "Create feedback loops between AI system outputs and model improvement — automate where possible.",
            "Build business-facing dashboards that show the value delivered by AI systems in non-technical terms.",
            "Expand AI use cases into internal operations — finance, HR, supply chain — not just customer-facing products.",
        ],
        4: [
            "Manage AI investments as a portfolio with value-based prioritisation and regular review against strategic goals.",
            "Implement real-time business value monitoring for all production AI systems with automated reporting.",
            "Build AI into product roadmap planning as a first-class capability, not an add-on.",
        ],
        5: [
            "Develop an AI-native product strategy where AI is fundamental to the value proposition, not a feature.",
            "Explore ecosystem partnerships and data sharing arrangements that extend AI capabilities beyond organisational boundaries.",
            "Publish an external AI strategy to build customer trust, attract partners, and differentiate in the market.",
        ],
    },
}


def get_recommendations(
    dimension_id: str,
    tier: int,
) -> list[str]:
    """
    Return recommendations for a given dimension and maturity tier.
    Falls back to tier 1 if not found.
    """
    dim_recs = RECOMMENDATIONS.get(dimension_id, {})
    return dim_recs.get(tier, dim_recs.get(1, [
        "No specific recommendations available for this dimension and tier."
    ]))


def get_all_recommendations(
    dimension_scores: dict[str, int],
) -> dict[str, list[str]]:
    """
    Given a dict of {dimension_id: tier}, return all recommendations.
    """
    return {
        dim_id: get_recommendations(dim_id, tier)
        for dim_id, tier in dimension_scores.items()
    }