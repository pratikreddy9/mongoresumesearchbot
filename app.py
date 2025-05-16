import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import os, json, re
from datetime import datetime
from typing import List, Optional, Dict, Any

import streamlit as st
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
import openai

# ── CONFIG ───────────────────────────────────────
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
SMTP_USER, SMTP_PASS = st.secrets["SMTP_USER"], st.secrets["SMTP_PASS"]
MONGO_CFG = {
    "host": "notify.pesuacademy.com",
    "port": 27017,
    "username": "admin",
    "password": st.secrets["MONGO_PASS"],
    "authSource": "admin",
}
MODEL_NAME = "gpt-4o"
EVAL_MODEL_NAME = "gpt-4o"
TOP_K_DEFAULT = 50
DB_NAME = "resumes_database"
COLL_NAME = "resumes"

# Country variants
COUNTRY_EQUIV = {
    "united states": ["united states", "usa", "us", "america", "united states of america"],
    "united kingdom": ["united kingdom", "uk", "england", "britain", "great britain"],
    "india": ["india", "bharat", "hindustan"],
    "germany": ["germany", "deutschland"],
    "canada": ["canada"],
    "australia": ["australia"],
    "singapore": ["singapore"],
    "indonesia": ["indonesia"],
    "vietnam": ["vietnam", "viet nam"],
    "uae": ["uae", "united arab emirates"],
}

# ── MONGO HELPERS ────────────────────────────────
def get_mongo_client() -> MongoClient:
    return MongoClient(**MONGO_CFG)

def normalize_lower(value):
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, list):
        return [v.strip().lower() for v in value if isinstance(v, str)]
    return value

def get_equiv_countries(country: Optional[str]) -> List[str]:
    if not country:
        return []
    c_low = country.strip().lower()
    return COUNTRY_EQUIV.get(c_low, [c_low])

# ── EMAIL TOOL ───────────────────────────────────
@tool
def send_email(to: str, subject: str, body: str) -> str:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"], msg["From"], msg["To"] = subject, SMTP_USER, to
        msg.attach(MIMEText(body, "plain"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as srv:
            srv.login(SMTP_USER, SMTP_PASS)
            srv.send_message(msg)
        return "Email sent!"
    except Exception as e:
        return f"Email failed: {e}"

# ── EMAIL BODY FORMATTER ─────────────────────────
def reformat_email_body(llm_output, intro="", conclusion=""):
    lines = []
    if intro:
        lines.append(intro)
    if isinstance(llm_output, list):
        for r in llm_output:
            name = r.get("name", "")
            email = r.get("email", "")
            phone = r.get("contactNo", "")
            location = r.get("location", "")
            experience = ", ".join(r.get("experience", []))
            skills = ", ".join(r.get("skills", []))
            lines.append(
                f"{name}\nEmail: {email}\nContact No: {phone}\nLocation: {location}\nExperience: {experience}\nSkills: {skills}\n"
            )
    else:
        lines.append(str(llm_output))
    if conclusion:
        lines.append(conclusion)
    return "\n".join(lines)

# ── LLM SCORER ───────────────────────────────────
_openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

def score_resumes_balanced(query: str, resumes: List[Dict[str, Any]],
                          country: str, min_exp: int, job_titles: List[str], skills: List[str]) -> List[str]:
    prompt = f"""
You are a strict resume screener. Return ONLY the resumeIds that:
- Have at least one matching job title from: {job_titles}
- Have total experience >= {min_exp}
- Cover all skill groups listed: {skills}
- Country must be '{country}'
Output JSON:
{{"top_resume_ids": [ ... ]}}
"""
    chat = _openai_client.chat.completions.create(
        model=EVAL_MODEL_NAME,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Candidates: {json.dumps(resumes)}"},
        ],
    )
    content = json.loads(chat.choices[0].message.content)
    return content.get("top_resume_ids", [])

# ── MAIN QUERY TOOL ──────────────────────────────
@tool
def query_db(
    query: str,
    country: Optional[str] = None,
    min_experience_years: Optional[int] = None,
    job_titles: Optional[List[str]] = None,
    skills: Optional[List[str]] = None,
    top_k: int = TOP_K_DEFAULT,
) -> Dict[str, Any]:
    debug_data = {}
    try:
        norm_country = normalize_lower(country)
        norm_job_titles = normalize_lower(job_titles) if job_titles else []
        norm_skills = normalize_lower(skills) if skills else []
        min_exp = int(min_experience_years) if min_experience_years else 0

        mongo_q = {}
        and_conditions = []

        if norm_country:
            country_values = get_equiv_countries(norm_country)
            country_cond = {
                "$or": [
                    {"country": {"$in": country_values}},
                    {"country": {"$regex": f"^{re.escape(norm_country)}$", "$options": "i"}}
                ]
            }
            and_conditions.append(country_cond)

        if min_exp > 0:
            and_conditions.append({
                "$expr": {
                    "$gte": [
                        {"$sum": {
                            "$map": {
                                "input": {"$ifNull": ["$jobExperiences", []]},
                                "as": "job",
                                "in": {
                                    "$convert": {
                                        "input": {"$ifNull": ["$$job.duration", "0"]},
                                        "to": "double",
                                        "onError": 0,
                                        "onNull": 0
                                    }
                                }
                            }
                        }},
                        min_exp
                    ]
                }
            })

        if norm_job_titles:
            or_titles = []
            for title in norm_job_titles:
                or_titles.append({
                    "jobExperiences.title": {
                        "$regex": f"\\b{re.escape(title)}\\b", "$options": "i"
                    }
                })
            and_conditions.append({"$or": or_titles})

        sql_terms, py_terms, js_terms, other_terms = [], [], [], []
        for s in norm_skills:
            if "sql" in s or "mysql" in s or "postgresql" in s or "nosql" in s:
                sql_terms.append(s)
            elif "python" in s or "django" in s or "flask" in s:
                py_terms.append(s)
            elif "javascript" in s or "js" in s or "node" in s:
                js_terms.append(s)
            else:
                other_terms.append(s)

        for skill_group in [sql_terms, py_terms, js_terms]:
            if skill_group:
                group_or = []
                for s in skill_group:
                    group_or.append({"skills.skillName": {"$regex": f"\\b{re.escape(s)}\\b", "$options": "i"}})
                    group_or.append({"keywords": {"$regex": f"\\b{re.escape(s)}\\b", "$options": "i"}})
                and_conditions.append({"$or": group_or})

        for s in other_terms:
            and_conditions.append({
                "$or": [
                    {"skills.skillName": {"$regex": f"\\b{re.escape(s)}\\b", "$options": "i"}},
                    {"keywords": {"$regex": f"\\b{re.escape(s)}\\b", "$options": "i"}}
                ]
            })

        if and_conditions:
            mongo_q["$and"] = and_conditions

        debug_data["mongo_query"] = mongo_q

        with get_mongo_client() as client:
            coll = client[DB_NAME][COLL_NAME]
            candidates = list(coll.find(mongo_q, {"_id": 0, "embedding": 0}).limit(top_k))

        debug_data["initial_candidate_count"] = len(candidates)

        if candidates:
            best_ids = score_resumes_balanced(query, candidates, norm_country, min_exp, norm_job_titles, norm_skills)
            best_resumes = [r for r in candidates if r.get("resumeId") in best_ids]
        else:
            best_resumes = []

        debug_data["llm_selected_ids"] = [r.get("resumeId") for r in best_resumes]

        return {
            "message": f"Found {len(best_resumes)} resumes after LLM filtering from {len(candidates)} initial MongoDB matches.",
            "results_count": len(best_resumes),
            "results": best_resumes,
            "mongo_query": mongo_q,
            "debug": debug_data,
            "completed_at": datetime.utcnow().isoformat(),
        }
    except PyMongoError as err:
        return {"error": f"DB error: {str(err)}"}
    except Exception as exc:
        import traceback
        return {
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "debug": debug_data
        }

# ── JOB MATCH COUNT TOOL ─────────────────────────
@tool
def get_job_match_counts(resume_ids: List[str]) -> Dict[str, Any]:
    try:
        if not isinstance(resume_ids, list):
            return {"error": "resume_ids must be a list of strings"}
        results = []
        with get_mongo_client() as client:
            coll = client[DB_NAME]["resume_matches"]
            for rid in resume_ids:
                doc = coll.find_one({"resumeId": rid}, {"_id": 0, "matches.jobId": 1})
                jobs = doc.get("matches", []) if doc else []
                results.append({"resumeId": rid, "jobsMatched": len(jobs)})
        return {
            "message": f"Counts fetched for {len(results)} resumeIds.",
            "results_count": len(results),
            "results": results,
            "completed_at": datetime.utcnow().isoformat(),
        }
    except PyMongoError as err:
        return {"error": f"DB error: {str(err)}"}
    except Exception as exc:
        return {"error": str(exc)}

# ── GET RESUME ID BY NAME TOOL ───────────────────
@tool
def get_resume_id_by_name(name: str) -> Dict[str, Any]:
    try:
        if "resume_ids" not in st.session_state:
            return {"error": "No resume IDs are stored in the current session."}

        name_norm = ' '.join(name.lower().split())
        for k, v in st.session_state.resume_ids.items():
            if name_norm in k.lower():
                return {"found": True, "name": k, "resumeId": v}

        with get_mongo_client() as client:
            coll = client[DB_NAME][COLL_NAME]
            query = {"$or": [
                {"name": {"$regex": name, "$options": "i"}},
                {"fullName": {"$regex": name, "$options": "i"}}
            ]}
            doc = coll.find_one(query, {"_id": 0, "resumeId": 1, "name": 1, "fullName": 1})
            if doc and doc.get("resumeId"):
                display_name = doc.get("name") or doc.get("fullName") or name
                return {"found": True, "name": display_name, "resumeId": doc["resumeId"]}

        return {"found": False, "message": f"No resumeId found for '{name}'"}
    except Exception as e:
        return {"error": str(e)}

# ── EXTRACT HIDDEN RESUME IDS FROM COMMENT ───────
def extract_resume_ids_from_response(response_text):
    meta_pattern = r'<!--RESUME_META:(.*?)-->'
    meta_match = re.search(meta_pattern, response_text)
    if meta_match:
        try:
            meta_data = json.loads(meta_match.group(1))
            return {item.get("name"): item.get("resumeId") for item in meta_data if item.get("resumeId")}
        except:
            return {}
    return {}

# ── PROCESS RAW AI RESPONSE TO STRUCTURED FORMAT ─
def process_response(text):
    if "Here are some" in text and ("Experience:" in text or "experience:" in text) and ("Skills:" in text or "skills:" in text):
        intro_pattern = r'^(.*?)\n\n([A-Z][a-z]+.*?)\n\nEmail:'
        intro_match = re.search(intro_pattern, text, re.DOTALL)
        intro_text = intro_match.group(1).strip() if intro_match else ""

        resume_pattern = r'([A-Z][a-z]+ (?:[A-Z][a-z]+ )?(?:[A-Z][a-z]+)?)\s*\n\s*Email:\s*([^\n]+)\s*\nContact No:\s*([^\n]+)\s*\nLocation:\s*([^\n]+)\s*\nExperience:\s*([^\n]+)\s*\nSkills:\s*([^\n]+)'
        matches = re.findall(resume_pattern, text, re.MULTILINE | re.IGNORECASE)

        conclusion_pattern = r'(These candidates.*?)\s*$'
        conclusion_match = re.search(conclusion_pattern, text, re.DOTALL)
        conclusion_text = conclusion_match.group(1).strip() if conclusion_match else ""

        resumes = []
        for match in matches:
            name, email, contact, location, experience, skills = match
            resumes.append({
                "name": name.strip(),
                "email": email.strip(),
                "contactNo": contact.strip(),
                "location": location.strip(),
                "experience": [e.strip() for e in experience.split(',')],
                "skills": [s.strip() for s in skills.split(',')],
                "keywords": []
            })

        return {
            "is_resume_response": True,
            "intro_text": intro_text,
            "resumes": resumes,
            "conclusion_text": conclusion_text,
            "full_text": text
        }
    return {
        "is_resume_response": False,
        "full_text": text
    }

# ── FILL MISSING RESUME IDs FROM DB ──────────────
def attach_hidden_resume_ids(resume_list: List[Dict[str, Any]]) -> None:
    if not resume_list:
        return
    with get_mongo_client() as client:
        coll = client[DB_NAME][COLL_NAME]
        for res in resume_list:
            email = res.get("email")
            phone = res.get("contactNo")
            if email and phone:
                doc = coll.find_one({"email": email, "contactNo": phone}, {"_id": 0, "resumeId": 1, "keywords": 1})
                if doc:
                    if doc.get("resumeId"):
                        res["resumeId"] = doc["resumeId"]
                    if doc.get("keywords"):
                        res["keywords"] = doc["keywords"]

# ── DISPLAY GRID ─────────────────────────────────
def display_resume_grid(resumes, container=None):
    target = container if container else st
    if not resumes:
        target.warning("No resumes found matching the criteria.")
        return
    target.markdown(\"\"\"
    <style>
    .resume-card {
        border: 1px solid #e1e4e8;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 15px;
        background-color: white;
        box-shadow: 0 3px 8px rgba(0,0,0,0.05);
        height: 100%;
    }
    .resume-name { font-weight: bold; font-size: 18px; margin-bottom: 8px; }
    .resume-location, .resume-contact, .resume-id {
        font-size: 14px;
        color: #444d56;
        margin-bottom: 4px;
    }
    .resume-section-title {
        font-weight: 600; margin-top: 10px; font-size: 15px;
    }
    .skill-tag, .keyword-tag {
        display: inline-block;
        padding: 4px 8px;
        margin: 3px;
        border-radius: 12px;
        font-size: 12px;
    }
    .skill-tag { background-color: #f0f8ff; color: #0366d6; }
    .keyword-tag { background-color: #fff0b3; color: #ff9900; }
    </style>
    \"\"\", unsafe_allow_html=True)

    rows = (len(resumes) + 2) // 3
    for row in range(rows):
        cols = target.columns(3)
        for col in range(3):
            idx = row * 3 + col
            if idx < len(resumes):
                r = resumes[idx]
                with cols[col]:
                    html = f\"\"\"
                    <div class="resume-card">
                        <div class="resume-name">{r.get("name")}</div>
                        <div class="resume-location">📍 {r.get("location")}</div>
                        <div class="resume-contact">📧 {r.get("email")}</div>
                        <div class="resume-contact">📱 {r.get("contactNo")}</div>
                    \"\"\"
                    if r.get("experience"):
                        html += '<div class="resume-section-title">Experience</div><ul>'
                        for e in r["experience"]:
                            html += f"<li>{e}</li>"
                        html += '</ul>'
                    if r.get("skills"):
                        html += '<div class="resume-section-title">Skills</div>'
                        for s in r["skills"]:
                            html += f'<span class="skill-tag">{s}</span>'
                    if r.get("keywords"):
                        html += '<div class="resume-section-title">Keywords</div>'
                        for k in r["keywords"]:
                            html += f'<span class="keyword-tag">{k}</span>'
                    if r.get("resumeId") and st.session_state.get("debug_mode"):
                        html += f"<div class='resume-id'>ID: {r['resumeId']}</div>"
                    html += "</div>"
                    st.markdown(html, unsafe_allow_html=True)
# ── AGENT SETUP ──────────────────────────────────
llm = ChatOpenAI(model=MODEL_NAME, api_key=OPENAI_API_KEY, temperature=0)

agent_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a helpful HR assistant named ZappBot.

# Formatting
Always format each candidate as:

[Full Name]
Email: ...
Contact No: ...
Location: ...
Experience: ...
Skills: ...

Separate each candidate with a blank line. Keep formatting consistent.

# Resume Tools
- Use `get_resume_id_by_name` if the user mentions a name
- Use `get_job_match_counts` with a resumeId to check job matches
- Use `send_email` when asked to send results
- Use `query_db` for fetching matching resumes
"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# ── SESSION STATE INIT ───────────────────────────
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history", return_messages=True
    )

if "resume_ids" not in st.session_state:
    st.session_state.resume_ids = {}

if "processed_responses" not in st.session_state:
    st.session_state.processed_responses = {}

if "job_match_data" not in st.session_state:
    st.session_state.job_match_data = {}

tools = [query_db, send_email, get_job_match_counts, get_resume_id_by_name]

if "agent_executor" not in st.session_state:
    agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(agent=agent, tools=tools, memory=st.session_state.memory, verbose=True)
    st.session_state.agent_upgraded = True
elif not st.session_state.get("agent_upgraded", False):
    upgraded_agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(agent=upgraded_agent, tools=tools, memory=st.session_state.memory, verbose=True)
    st.session_state.agent_upgraded = True

# ── STREAMLIT UI SETUP ───────────────────────────
st.set_page_config(page_title="ZappBot", layout="wide")

st.markdown('<h1 style="font-size:32px;">⚡ ZappBot</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Settings")
    debug_mode = st.checkbox("Debug Mode", value=False)
    st.session_state["debug_mode"] = debug_mode

    default_recipient = st.text_input("Default Email Recipient", "")
    
    if st.button("Clear Chat"):
        st.session_state.memory.clear()
        st.session_state.processed_responses = {}
        st.session_state.job_match_data = {}
        st.session_state.resume_ids = {}
        st.rerun()

chat_container = st.container()

user_input = st.chat_input("Ask ZappBot to find resumes...")
if user_input:
    with st.spinner("Thinking..."):
        try:
            response = st.session_state.agent_executor.invoke({"input": user_input})
            response_text = response["output"]

            resume_ids = extract_resume_ids_from_response(response_text)
            if resume_ids:
                st.session_state.resume_ids.update(resume_ids)

            processed = process_response(response_text)

            if "jobsMatched" in response_text:
                matches_pattern = r'"results":\s*(\\[.*?\\])'
                matches_match = re.search(matches_pattern, response_text)
                if matches_match:
                    match_data = json.loads(matches_match.group(1))
                    for item in match_data:
                        rid = item.get("resumeId")
                        if rid:
                            st.session_state.job_match_data[rid] = item.get("jobsMatched", 0)

            timestamp = datetime.now().isoformat()
            message_key = f"user_{timestamp}"
            st.session_state.processed_responses[message_key] = processed

            st.rerun()
        except Exception as e:
            st.error(f"Error: {str(e)}")
            if debug_mode:
                st.exception(e)

# ── DISPLAY CHAT HISTORY ─────────────────────────
with chat_container:
    resume_responses = []

    for i, msg in enumerate(st.session_state.memory.chat_memory.messages):
        if msg.type == "human":
            st.chat_message("user").write(msg.content)

            if i+1 < len(st.session_state.memory.chat_memory.messages):
                next_msg = st.session_state.memory.chat_memory.messages[i+1]
                if next_msg.type == "ai":
                    ai_msg_key = f"ai_{i+1}"
                    if ai_msg_key not in st.session_state.processed_responses:
                        st.session_state.processed_responses[ai_msg_key] = process_response(next_msg.content)
                    processed_ai = st.session_state.processed_responses[ai_msg_key]
                    if processed_ai["is_resume_response"]:
                        resume_responses.append({
                            "query": msg.content,
                            "processed": processed_ai,
                            "index": i+1
                        })
        else:
            msg_key = f"ai_{i}"
            if msg_key not in st.session_state.processed_responses:
                st.session_state.processed_responses[msg_key] = process_response(msg.content)
            processed = st.session_state.processed_responses[msg_key]
            ai_message = st.chat_message("assistant")
            if processed["is_resume_response"]:
                ai_message.write(processed["intro_text"])
                if processed.get("conclusion_text"):
                    ai_message.write(processed["conclusion_text"])
            else:
                ai_message.write(processed["full_text"])

    if resume_responses:
        st.markdown("---")
        st.subheader("Resume Search Results")
        for i, resp in enumerate(resume_responses):
            with st.expander(f"Search {i+1}: {resp['query']}", expanded=(i == len(resume_responses)-1)):
                st.markdown(f"<div class='resume-query'>{resp['processed']['intro_text']}</div>", unsafe_allow_html=True)
                attach_hidden_resume_ids(resp['processed']['resumes'])
                for resume in resp['processed']['resumes']:
                    if resume.get("resumeId") and resume.get("name"):
                        st.session_state.resume_ids[resume["name"]] = resume["resumeId"]
                    if resume.get("resumeId") in st.session_state.job_match_data:
                        resume["jobsMatched"] = st.session_state.job_match_data[resume["resumeId"]]
                display_resume_grid(resp['processed']['resumes'])

                cols = st.columns([2, 1, 1])
                with cols[1]:
                    if resp['processed']['resumes']:
                        if st.button(f"📧 Email Results", key=f"email_btn_{i}"):
                            try:
                                body = reformat_email_body(
                                    llm_output=resp['processed']['resumes'],
                                    intro=resp['processed']['intro_text'],
                                    conclusion=resp['processed'].get('conclusion_text', '')
                                )
                                recipient = default_recipient
                                if not recipient:
                                    st.error("Please set a default email recipient.")
                                else:
                                    result = send_email(to=recipient, subject=f"ZappBot Results: {resp['query']}", body=body)
                                    st.success(f"Email sent to {recipient}")
                            except Exception as e:
                                st.error(f"Failed to send email: {str(e)}")

                with cols[2]:
                    if resp['processed']['resumes']:
                        if st.button("🔍 Match Jobs", key=f"job_btn_{i}"):
                            try:
                                resume_ids = [r.get("resumeId") for r in resp['processed']['resumes'] if r.get("resumeId")]
                                if resume_ids:
                                    result = get_job_match_counts(resume_ids)
                                    if "results" in result:
                                        for item in result["results"]:
                                            rid = item.get("resumeId")
                                            if rid:
                                                st.session_state.job_match_data[rid] = item.get("jobsMatched", 0)
                                        st.success(f"Job match data updated for {len(resume_ids)} resumes")
                                        st.rerun()
                                    else:
                                        st.error("Failed to get job match data")
                                else:
                                    st.warning("No resume IDs found")
                            except Exception as e:
                                st.error(f"Failed to get job matches: {str(e)}")

                if resp['processed'].get('conclusion_text'):
                    st.write(resp['processed']['conclusion_text'])

# ── DEBUG PANEL ──────────────────────────────────
if debug_mode:
    with st.expander("🔧 Debug Info"):
        st.subheader("Chat Memory")
        st.json({i: msg.content for i, msg in enumerate(st.session_state.memory.chat_memory.messages)})

        st.subheader("Resume IDs")
        st.json(st.session_state.resume_ids)

        st.subheader("Job Match Data")
        st.json(st.session_state.job_match_data)

        st.subheader("Mongo Query")
        for key, val in st.session_state.processed_responses.items():
            if "debug" in val and "mongo_query" in val["debug"]:
                st.code(json.dumps(val["debug"]["mongo_query"], indent=2))
