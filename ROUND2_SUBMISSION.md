# KnowFlow AI – Round 2: The Build

## 1. Project Information

**Project Name:** KnowFlow AI  
**Hackathon:** CodersInPune  
**Team Name:** Code Gods

### Team Members

1. Poojasri I S
2. Aadarshini S S
3. Surya Prakash M

### Team Leader

Poojasri I S

---

## 2. Project Overview

KnowFlow AI is an AI-assisted project knowledge handover and verification platform designed to prevent critical technical knowledge from being lost when employees leave an organisation or move to another team.

In software development teams, important information about architecture, code ownership, configurations, decisions, dependencies and unresolved tasks is often scattered across repositories and documents.

When an experienced developer leaves, the remaining team may struggle to understand the system, identify responsibilities and continue development efficiently.

KnowFlow AI addresses this problem by organising project knowledge into verifiable claims, presenting supporting evidence and helping project managers review missing or conflicting information.

The platform aims to make knowledge handover more structured, transparent and reliable.

---

## 3. Live Product and Source Code

**Live Application:**

https://knowflow-ai-btyv.onrender.com

**GitHub Repository:**

https://github.com/poojasrichezhian/KnowFlow-AI

**Deployment Platform:** Render

**Application Type:** Full-stack web application

---

## 4. Problem Statement

Software teams depend on the knowledge and experience of individual developers.

When an important developer leaves a project, several problems can occur:

- Critical technical knowledge may disappear.
- Project documentation may be incomplete or outdated.
- Code ownership and responsibilities may be unclear.
- Important architectural decisions may not be recorded.
- Conflicting information may exist across different sources.
- Remaining developers may waste time understanding unfamiliar systems.
- Project continuity and productivity may be affected.

Traditional handover processes depend heavily on manually written documents and personal explanations.

There is a need for a structured platform that can organise project knowledge, identify information gaps, provide supporting evidence and help teams verify handover readiness.

---

## 5. Our Solution

KnowFlow AI provides a centralised knowledge handover workspace.

It organises project information into individual knowledge claims and classifies them into four categories:

1. **Verified:** Information supported by available evidence.
2. **Uncertain:** Information that requires additional confirmation.
3. **Conflicting:** Information that contains inconsistencies requiring review.
4. **Missing:** Important information that has not been adequately documented.

Project managers can inspect supporting evidence, review claims, resolve conflicts and track the project's knowledge readiness.

The goal is to help teams understand what is known, what is uncertain, what is conflicting and what still needs attention before a developer leaves.

---

## 6. Features Implemented

The current implementation focuses on the following core capabilities:

### 6.1 Project Handover Dashboard

- Centralised project handover dashboard.
- Project knowledge overview.
- Knowledge claim statistics.
- Review progress tracking.
- Project readiness percentage.

### 6.2 Knowledge Claim Classification

- Classification of knowledge claims into Verified, Uncertain, Conflicting and Missing.
- Structured presentation of project knowledge.
- Identification of claims that require human review.

### 6.3 Evidence Review

- Evidence viewer for examining supporting information.
- Display of available documentation references.
- Presentation of supporting code or repository references where available.
- Evidence-based claim review.

### 6.4 Human Review and Conflict Resolution

- Review of conflicting knowledge claims.
- Ability to record explanations during conflict resolution.
- Claim approval workflow.
- Updated review statistics after resolution.

### 6.5 Readiness Tracking

- Knowledge review progress.
- Verified and unresolved claim counts.
- Project readiness percentage.
- Dashboard updates following review actions.

---

## 7. Demonstration Scenario

The application includes a demonstration project named **Payments Service**.

The demonstration scenario represents a senior backend developer, Arjun Sharma, leaving the project on 14 November 2026.

The dashboard presents project knowledge and handover readiness information.

The demonstration data includes:

- 46 total knowledge claims.
- 25 initially verified claims.
- 7 conflicting claims.
- 9 missing claims.
- 5 uncertain claims.
- Initial readiness score of 58%.

A project manager can inspect a conflicting claim, examine its available evidence, enter an explanation and approve the claim.

After resolving one conflict in the local demonstration, the dashboard updated to show:

- 26 reviewed claims.
- 26 verified claims.
- 6 conflicting claims.
- Readiness score increased to 60%.

This demonstrates the human review and readiness tracking workflow.

*Note: Demonstration figures describe the sample project and are not real organisational data.*

---

## 8. Technology Stack

### Frontend

- React 18
- Vite
- JavaScript
- HTML5
- CSS3

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy

### Database

- SQLite as the default database.
- PostgreSQL support through database configuration.

### Authentication and Security

- JWT-based authentication implementation.
- Password hashing using PBKDF2.
- Environment-based configuration for sensitive credentials.

### Document Processing

- PyMuPDF for PDF processing.
- python-docx for Word document processing.

### External Integration

- GitHub REST API for repository information.
- Optional LLM integration through an OpenAI-compatible API configuration.

### Testing

- Pytest.
- 17 automated backend tests passed locally.

### Deployment and Development Tools

- Git and GitHub.
- Docker.
- Render.
- Visual Studio Code.

---

## 9. System Architecture

KnowFlow AI follows a full-stack application architecture.

### Frontend Layer

The React application provides the user interface for:

- Accessing the handover workspace.
- Viewing project information.
- Inspecting knowledge claims.
- Reviewing evidence.
- Resolving conflicts.
- Tracking readiness.

### Backend Layer

The FastAPI backend handles:

- Application API requests.
- Knowledge claim processing.
- Verification logic.
- Evidence handling.
- Review operations.
- Data persistence.

### Verification Engine

The verification engine processes knowledge claims and applies rule-based and text-matching checks to classify information.

It supports the four claim statuses:

- Verified
- Uncertain
- Conflicting
- Missing

### Data Layer

SQLAlchemy manages database operations. SQLite is used by default, with PostgreSQL support through configuration.

### External Services

GitHub integration is designed to retrieve repository information. Optional LLM functionality can be enabled through environment configuration.

### Deployment

The application is packaged using Docker and deployed on Render.

---

## 10. Technical Implementation

One of the main technical challenges was connecting project knowledge, evidence, verification and human review into one workflow.

The backend contains a verification engine that evaluates claims using rule-based and text-matching techniques.

The system organises the results into structured claim statuses so that project managers can understand which information is supported, uncertain, conflicting or missing.

Evidence is presented alongside claims to support human verification rather than treating every automatically generated result as unquestionably correct.

The review workflow allows a project manager to record an explanation and approve a claim.

The dashboard then reflects the updated review progress and readiness information.

This approach combines automated checks with human decision-making.

---

## 11. Testing and Validation

The backend was tested locally using Pytest.

**Automated test result:**

17 tests passed successfully.

The local application was also tested through the browser.

The demonstrated workflow included:

1. Opening the application.
2. Accessing the project manager demonstration.
3. Loading the project dashboard.
4. Inspecting a conflicting knowledge claim.
5. Reviewing supporting evidence.
6. Recording an explanation.
7. Approving the claim.
8. Observing updated dashboard statistics.

The deployed backend health endpoint was also checked.

**Health endpoint:**

https://knowflow-ai-btyv.onrender.com/api/health

The backend returned:

`{"ok":true,"llm":false,"github_token":false}`

This confirms that the backend is running. The LLM and authenticated GitHub integrations are not enabled in the current deployment.

---

## 12. Deployment

KnowFlow AI is deployed on Render using Docker.

**Live URL:**

https://knowflow-ai-btyv.onrender.com

**Source Repository:**

https://github.com/poojasrichezhian/KnowFlow-AI

The project source code is maintained in a public GitHub repository.

The deployment uses Render's free hosting plan. As a result, the service may take additional time to respond after a period of inactivity.

---

## 13. Changes from Round 1

The original proposal focused on developing an intelligent knowledge handover platform to prevent the loss of critical project information.

During implementation, we prioritised building a functional full-stack application.

The major implementation changes include:

- Developed a working React frontend and FastAPI backend.
- Implemented a project handover dashboard.
- Introduced four knowledge claim classifications.
- Added evidence-based claim review.
- Implemented human-assisted conflict resolution.
- Added readiness and review progress tracking.
- Added automated backend testing.
- Containerised and deployed the application using Docker and Render.

We prioritised a functional and demonstrable core product instead of claiming advanced features that were not yet ready.

---

## 14. Current Limitations

The current version is a working prototype with the following limitations:

1. Advanced LLM-based analysis is not enabled in the current deployment because an LLM API key has not been configured.
2. Authenticated GitHub integration is not enabled because a GitHub token has not been configured.
3. The current verification engine primarily uses rule-based and text-matching techniques.
4. Advanced semantic understanding and context-aware verification need further improvement.
5. Scanned PDF documents may not be fully supported.
6. The current implementation has limitations in the types of conflicts it can identify.
7. The deployment uses a free hosting plan, so initial loading after inactivity may be delayed.
8. Database persistence and production scalability require further improvement before real organisational use.

These limitations will guide our next development phase.

---

## 15. Three Major Improvements Planned for Round 3

We commit to delivering the following three substantial improvements.

### Improvement 1: Semantic Knowledge Verification

We will enhance the verification engine using semantic embeddings and LLM-based entailment.

The improved system will compare the meaning of claims with supporting evidence rather than relying mainly on keyword matching.

Expected improvements:

- Better understanding of technical context.
- More accurate knowledge verification.
- Improved contradiction detection.
- More reliable identification of unsupported claims.
- Better evidence-based confidence assessment.

**User Impact:** Project managers will receive more meaningful and context-aware verification results.

### Improvement 2: Continuous Knowledge Monitoring

We will implement continuous GitHub repository monitoring through scheduled synchronisation or webhook integration.

The system will detect relevant changes in project source code and documentation and identify knowledge claims that may have become outdated.

Expected improvements:

- Automated repository synchronisation.
- Detection of changes affecting existing knowledge.
- Identification of outdated claims.
- Notifications for knowledge that needs review.
- Improved handover information freshness.

**User Impact:** Teams will be able to maintain accurate project knowledge as development continues.

### Improvement 3: Ask the Handover – Evidence-Based Question Answering

We will introduce an interactive question-answering capability that allows team members to ask questions about their projects.

The system will generate answers using approved knowledge claims and their supporting evidence.

If reliable information is unavailable, the system will identify the missing knowledge and suggest follow-up questions.

Expected improvements:

- Natural-language project questions.
- Answers supported by approved evidence.
- Source references for generated answers.
- Identification of unanswered questions.
- Suggestions for collecting missing knowledge.

**User Impact:** New developers will be able to understand unfamiliar projects more quickly and find reliable information without manually searching multiple documents.

---

## 16. Future Vision

Our long-term vision is to make KnowFlow AI a reliable knowledge continuity platform for software development teams.

We aim to reduce knowledge loss, improve project transitions and help organisations preserve important technical decisions and responsibilities.

By combining automated knowledge verification, continuous monitoring and evidence-based question answering, KnowFlow AI can make project handovers more transparent and efficient.

---

## 17. Conclusion

KnowFlow AI transforms traditional project handover into a structured and evidence-driven process.

The current build demonstrates a working foundation with a project dashboard, knowledge claim classification, evidence review, human conflict resolution and readiness tracking.

We have developed and deployed the full-stack application, published the source code and tested the backend with 17 passing automated tests.

Our Round 3 commitments focus on semantic verification, continuous knowledge monitoring and evidence-based question answering.

**KnowFlow AI – Preserve Knowledge. Verify Understanding. Ensure Continuity.**

---

## 18. Project Links

| Resource | Link |
|---|---|
| Live Application | https://knowflow-ai-btyv.onrender.com |
| GitHub Repository | https://github.com/poojasrichezhian/KnowFlow-AI |
| Backend Health Check | https://knowflow-ai-btyv.onrender.com/api/health |

**Team Members**

- Poojasri I S
- Aadarshini S S
- Surya Prakash M