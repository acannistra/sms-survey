# **Architecture Brief: Lightweight SMS Survey Engine**

*An LLM wrote this. – Tony*

### **Executive Summary**

We are building a cost-effective, maintainable SMS survey tool to engage public lands advocates. The system is designed to be **serverless** and **stateless**, decoupling the survey content (YAML) from the execution logic (Python). This ensures that non-technical staff can modify survey questions without requiring code deployments.

### **High-Level Architecture**

The system follows an event-driven "webhook" pattern. We do not maintain long-running servers; we only respond to incoming HTTP requests from Twilio.

1. **Trigger:** User sends SMS to our Twilio number.  
2. **Ingest:** Twilio POSTs the message to our **FastAPI** endpoint hosted on **Fly.io**.  
3. **State Lookup:** The app retrieves the user's session (Current Step, Past Answers) from **PostgreSQL**.  
4. **Engine Execution:**  
   * Loads the **Survey Definition (YAML)**.  
   * Validates the input against the current step's rules (Regex/Choice).  
   * Determines the next step (Branching Logic).  
5. **Response:** App updates the DB and returns TwiML to Twilio to send the next question.

### **Core Components**

| Component | Technology | Rationale |
| :---- | :---- | :---- |
| **Runtime** | **Python 3.11+ / FastAPI** | High performance, native async support, excellent developer ergonomics. |
| **Hosting** | **Fly.io** | "Scale-to-zero" capability, built-in Docker support, simple region placement. |
| **Database** | **PostgreSQL (Fly Managed)** | Robust data integrity. We use **Alembic** for schema migrations via Fly's `release_command`. |
| **Config** | **YAML \+ Jinja2** | Surveys are defined as data, not code. Supports templating (`{{ name }}`) and regex validation. |

### **The "Survey as Data" Strategy**

To minimize engineering overhead for content changes, surveys are defined in a readable YAML format.

\- id: q\_zip

  text: "Thanks {{ name }}\! What is your zip code?"

  type: regex

  pattern: "^\\d{5}$"

  store\_as: zip\_code

  next: q\_volunteer

### **Level of Effort (LOE) Assessment**

**Estimated Timeline: 3-5 Days (MVP)**

The complexity of this project is low, primarily consisting of "glue code" between standard libraries.

* **Day 1: Infrastructure & Boilerplate.**  
  * *LLM Acceleration:* High. Copilot can scaffold the entire FastAPI \+ Twilio webhook structure and Dockerfile in minutes.  
* **Day 2: The "Engine" Logic.**  
  * *LLM Acceleration:* Very High. LLMs excel at writing state machine logic ("Write a Python function that parses this YAML and validates input X against step Y").  
* **Day 3: Persistence & Migrations.**  
  * *LLM Acceleration:* Medium. Setting up Alembic and SQLAlchemy models is standard, but requires careful manual review of the migration scripts.  
* **Day 4: Testing & Edge Cases.**  
  * *LLM Acceleration:* High. Generating unit tests for the regex patterns and branching logic.

### **Risks & Mitigations**

* **Risk:** "Double Texting" (Race conditions).  
  * *Mitigation:* Database row locking or optimistic locking on the session state.  
* **Risk:** Twilio Costs.  
  * *Mitigation:* The architecture is efficient, but SMS segments cost money. We will implement a "STOP" handler at the gateway level to prevent runaway loops.

### **Recommendation**

Proceed with the **PostgreSQL \+ Fly.io** approach. It offers the best balance of data ownership and ease of deployment. The YAML-based engine provides the requested maintainability, allowing the engineering team to build the *runner* once, while the advocacy team builds the *surveys* indefinitely.  
