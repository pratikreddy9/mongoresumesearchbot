"""
ZappBot: Resume‑filtering chatbot with optimized display + email sender + job match counts
LangChain 0.3.25 • OpenAI 1.78.1 • Streamlit 1.34+
"""

import os, json, re
from datetime import datetime

import streamlit as st
from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain.memory import ConversationBufferMemory

# Import modular components
from prompts import agent_prompt
from design import display_resume_grid
from variants import expand
from utils import (
    get_mongo_client, 
    extract_resume_ids_from_response, 
    process_response, 
    attach_hidden_resume_ids
)
from tools import query_db, send_email, get_job_match_counts, get_resume_id_by_name

# ── CONFIG ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
MODEL_NAME = "gpt-4o"
DB_NAME = "resumes_database"
COLL_NAME = "resumes"

# ── AGENT + MEMORY ─────────────────────────────────────────────────────
llm = ChatOpenAI(model=MODEL_NAME, api_key=OPENAI_API_KEY, temperature=0)

# Initialize session state variables
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

# Initialize or upgrade the agent
tools = [query_db, send_email, get_job_match_counts, get_resume_id_by_name]
if "agent_executor" not in st.session_state:
    agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools,
        memory=st.session_state.memory, 
        verbose=True
    )
    st.session_state.agent_upgraded = True
elif not st.session_state.get("agent_upgraded", False):
    upgraded_agent = create_openai_tools_agent(llm, tools, agent_prompt)
    st.session_state.agent_executor = AgentExecutor(
        agent=upgraded_agent,
        tools=tools,
        memory=st.session_state.memory,
        verbose=True,
    )
    st.session_state.agent_upgraded = True

# ── STREAMLIT UI ───────────────────────────────────────────────────────
st.set_page_config(page_title="⚡ ZappBot", layout="wide", initial_sidebar_state="expanded")

# 🔥 ULTIMATE WOW FACTOR CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    /* Dark theme with glassmorphism */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        font-family: 'Inter', sans-serif;
        max-width: none !important;
    }
    
    /* Glassmorphism container */
    .main-container {
        backdrop-filter: blur(20px);
        background: rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        margin: 20px;
        padding: 30px;
        box-shadow: 0 25px 50px rgba(0, 0, 0, 0.15);
    }
    
    /* Animated header with gradient text */
    .header-container {
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 40px;
        padding: 20px;
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%);
        border-radius: 20px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .header-emoji {
        font-size: 48px;
        margin-right: 20px;
        animation: pulse 2s infinite;
        filter: drop-shadow(0 0 20px rgba(255,215,0,0.5));
    }
    
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.1); }
        100% { transform: scale(1); }
    }
    
    .header-text {
        font-size: 42px;
        font-weight: 800;
        background: linear-gradient(135deg, #FFD700, #FF6B6B, #4ECDC4, #45B7D1);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: gradient-shift 3s ease-in-out infinite;
        text-shadow: 0 0 30px rgba(255,255,255,0.3);
    }
    
    @keyframes gradient-shift {
        0%, 100% { filter: hue-rotate(0deg); }
        50% { filter: hue-rotate(90deg); }
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(135deg, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.5) 100%);
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(255,255,255,0.1);
    }
    
    /* Chat messages with modern styling */
    .stChatMessage {
        background: rgba(255,255,255,0.05) !important;
        backdrop-filter: blur(10px) !important;
        border-radius: 15px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        margin: 10px 0 !important;
        animation: slideIn 0.3s ease-out;
    }
    
    @keyframes slideIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Enhanced buttons with hover effects */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 25px !important;
        padding: 12px 24px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-3px) scale(1.05) !important;
        box-shadow: 0 15px 40px rgba(102, 126, 234, 0.4) !important;
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%) !important;
    }
    
    .stButton > button:active {
        transform: translateY(-1px) scale(1.02) !important;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%) !important;
        backdrop-filter: blur(10px) !important;
        border-radius: 15px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: white !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    
    .streamlit-expanderHeader:hover {
        background: linear-gradient(135deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.1) 100%) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2) !important;
    }
    
    /* Input field styling */
    .stTextInput > div > div > input {
        background: rgba(255,255,255,0.1) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 15px !important;
        color: white !important;
        padding: 15px 20px !important;
        font-size: 16px !important;
    }
    
    .stTextInput > div > div > input::placeholder {
        color: rgba(255,255,255,0.6) !important;
    }
    
    /* Chat input styling */
    .stChatInputContainer {
        background: rgba(0,0,0,0.3) !important;
        backdrop-filter: blur(20px) !important;
        border-radius: 25px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        margin: 20px 0 !important;
    }
    
    /* Resume results section */
    .resume-results-header {
        text-align: center;
        color: white;
        font-size: 28px;
        font-weight: 700;
        margin: 40px 0 30px 0;
        text-shadow: 0 0 20px rgba(255,255,255,0.3);
    }
    
    /* Floating action buttons */
    .floating-stats {
        position: fixed;
        top: 20px;
        right: 20px;
        background: rgba(0,0,0,0.7);
        backdrop-filter: blur(20px);
        border-radius: 15px;
        padding: 15px 20px;
        color: white;
        font-weight: 600;
        border: 1px solid rgba(255,255,255,0.1);
        z-index: 1000;
        animation: fadeIn 1s ease-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Success/Error messages with better styling */
    .stSuccess {
        background: linear-gradient(135deg, rgba(76, 175, 80, 0.15) 0%, rgba(76, 175, 80, 0.05) 100%) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(76, 175, 80, 0.3) !important;
        border-radius: 15px !important;
        color: #81C784 !important;
    }
    
    .stError {
        background: linear-gradient(135deg, rgba(244, 67, 54, 0.15) 0%, rgba(244, 67, 54, 0.05) 100%) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(244, 67, 54, 0.3) !important;
        border-radius: 15px !important;
        color: #EF5350 !important;
    }
    
    /* Checkbox styling */
    .stCheckbox {
        color: white !important;
    }
    
    /* Selectbox styling */
    .stSelectbox > div > div {
        background: rgba(255,255,255,0.1) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 15px !important;
        color: white !important;
    }
    
    /* Divider styling */
    hr {
        border: none !important;
        height: 2px !important;
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%) !important;
        margin: 30px 0 !important;
    }
    
    /* Loading spinner enhancement */
    .stSpinner {
        background: rgba(255,255,255,0.1) !important;
        backdrop-filter: blur(20px) !important;
        border-radius: 20px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
    }
    
    /* Sidebar text color */
    .css-1d391kg .stMarkdown {
        color: white !important;
    }
    
    /* Main content text color */
    .main .stMarkdown {
        color: white !important;
    }
    
    /* JSON display styling */
    .stJson {
        background: rgba(0,0,0,0.3) !important;
        backdrop-filter: blur(10px) !important;
        border-radius: 15px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
    }
    
    .element-container:has(.floating-stats) {
        position: fixed !important;
        top: 20px !important;
        right: 20px !important;
        z-index: 1000 !important;
    }
</style>
""", unsafe_allow_html=True)

# 🎯 Floating Stats Counter
total_resumes = len(st.session_state.resume_ids)
st.markdown(f"""
<div class="floating-stats">
    📊 {total_resumes} Resumes Loaded
</div>
""", unsafe_allow_html=True)

# 🚀 Enhanced Header
st.markdown('''
<div class="header-container">
    <div class="header-emoji">⚡</div>
    <div class="header-text">ZappBot</div>
</div>
''', unsafe_allow_html=True)

# 🎨 Enhanced Sidebar
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    debug_mode = st.checkbox("🐛 Debug Mode", value=False)
    
    # Email settings section
    st.markdown("### 📧 Email Settings")
    default_recipient = st.text_input("Default Email Recipient", 
                                     placeholder="recipient@example.com",
                                     help="Default email to use when sending resume results")
    
    # Job matching tool section
    st.markdown("### 🎯 Job Matching")
    st.markdown("""
    💡 **Quick Tip**: Ask about specific candidates:
    ```
    How many jobs is [Candidate Name] matched to?
    ```
    """)
    
    if st.button("🗑️ Clear Chat History"):
        st.session_state.memory.clear()
        st.session_state.processed_responses = {}
        st.session_state.job_match_data = {}
        st.session_state.resume_ids = {}
        st.rerun()
    
    # Add some stats
    st.markdown("---")
    st.markdown("### 📈 Session Stats")
    st.metric("💼 Resumes Found", len(st.session_state.resume_ids))
    st.metric("🎯 Job Matches", len(st.session_state.job_match_data))
    st.metric("💬 Conversations", len(st.session_state.memory.chat_memory.messages) // 2)

# Main chat container
chat_container = st.container()

# Handle user input
user_input = st.chat_input("🔍 Ask me to find the perfect resumes...")
if user_input:
    # Process with agent
    with st.spinner("🧠 AI is thinking..."):
        try:
            # Invoke the agent
            response = st.session_state.agent_executor.invoke({"input": user_input})
            response_text = response["output"]
            
            # Extract and store resumeIds from the response
            resume_ids = extract_resume_ids_from_response(response_text)
            if resume_ids:
                st.session_state.resume_ids.update(resume_ids)
            
            # Process the response
            processed = process_response(response_text)
            
            # Check if this contains job match data
            if "jobsMatched" in response_text:
                try:
                    # Try to extract job match data
                    matches_pattern = r'"results":\s*(\[.*?\])'
                    matches_match = re.search(matches_pattern, response_text)
                    if matches_match:
                        match_data = json.loads(matches_match.group(1))
                        # Store job match data
                        for item in match_data:
                            resume_id = item.get("resumeId")
                            if resume_id:
                                st.session_state.job_match_data[resume_id] = item.get("jobsMatched", 0)
                except:
                    pass  # Silently fail if we can't parse the job match data
            
            # Generate a unique key for this message
            timestamp = datetime.now().isoformat()
            message_key = f"user_{timestamp}"
            st.session_state.processed_responses[message_key] = processed
            
            # Force a refresh to show the new messages
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            if debug_mode:
                st.exception(e)

# Display the complete chat history
with chat_container:
    # Create a list to store all resume responses for display in the order they appear
    resume_responses = []
    
    # Display all messages
    for i, msg in enumerate(st.session_state.memory.chat_memory.messages):
        if msg.type == "human":
            st.chat_message("user", avatar="👤").write(msg.content)
            
            # Store the user query for context if the next message is a resume response
            if i+1 < len(st.session_state.memory.chat_memory.messages):
                next_msg = st.session_state.memory.chat_memory.messages[i+1]
                if next_msg.type == "ai":
                    # Generate a key for the AI message
                    ai_msg_key = f"ai_{i+1}"
                    
                    # Ensure the message is processed
                    if ai_msg_key not in st.session_state.processed_responses:
                        st.session_state.processed_responses[ai_msg_key] = process_response(next_msg.content)
                    
                    # Get the processed message
                    processed_ai = st.session_state.processed_responses[ai_msg_key]
                    
                    # If this is a resume response, store it for later display
                    if processed_ai["is_resume_response"]:
                        resume_responses.append({
                            "query": msg.content,
                            "processed": processed_ai,
                            "index": i+1
                        })
                        
        else:  # AI message
            # Get or process the AI message
            msg_key = f"ai_{i}"
            if msg_key not in st.session_state.processed_responses:
                st.session_state.processed_responses[msg_key] = process_response(msg.content)
            
            processed = st.session_state.processed_responses[msg_key]
            
            # Display the message
            ai_message = st.chat_message("assistant", avatar="⚡")
            if processed["is_resume_response"]:
                # Extract and store resumeIds if they are in the message
                resume_ids = extract_resume_ids_from_response(processed["full_text"])
                if resume_ids:
                    st.session_state.resume_ids.update(resume_ids)
                
                hidden_meta = json.dumps([{"name": r.get("name"), "resumeId": r.get("resumeId", "")}for r in processed["resumes"]])
                # Just show the intro text in the chat message
                for item in json.loads(hidden_meta):
                    if item.get("name") and item.get("resumeId"):
                        st.session_state.resume_ids[item["name"]] = item["resumeId"]
                        
                ai_message.write(processed["intro_text"])
                
                # If there's a conclusion, add it 
                if processed.get("conclusion_text"):
                    ai_message.write(processed["conclusion_text"])
            else:
                # For non-resume responses, show the full text
                ai_message.write(processed["full_text"])
    
    # Display all resume grids after the chat
    if resume_responses:
        st.markdown('<div class="resume-results-header">🎯 Resume Search Results</div>', unsafe_allow_html=True)
        
        # Create an expander for each resume search
        for i, resp in enumerate(resume_responses):
            with st.expander(f"🔍 Search {i+1}: {resp['query']}", expanded=(i == len(resume_responses)-1)):
                st.markdown(f"**{resp['processed']['intro_text']}**")
                
                # Make sure resumes have resumeIds
                attach_hidden_resume_ids(resp['processed']['resumes'])
                
                # Store resumeIds in session state
                for resume in resp['processed']['resumes']:
                    if resume.get("resumeId") and resume.get("name"):
                        st.session_state.resume_ids[resume["name"]] = resume["resumeId"]
                
                # Add job match data to resumes if available
                if st.session_state.job_match_data:
                    for resume in resp['processed']['resumes']:
                        resume_id = resume.get("resumeId")
                        if resume_id and resume_id in st.session_state.job_match_data:
                            resume["jobsMatched"] = st.session_state.job_match_data[resume_id]
                
                # Display the resume grid
                display_resume_grid(resp['processed']['resumes'])
                
                # Add a row with enhanced buttons
                cols = st.columns([2, 1, 1])
                
                # Email button
                with cols[1]:
                    if resp['processed']['resumes']:
                        if st.button(f"📧 Email Results", key=f"email_btn_{i}"):
                            try:
                                # Format email body using reformat_email_body from utils.py
                                from utils import reformat_email_body
                                
                                plain_text_body = reformat_email_body(
                                    llm_output=resp['processed']['resumes'],
                                    intro=resp['processed']['intro_text'],
                                    conclusion=resp['processed'].get('conclusion_text', '')
                                )
                                
                                # Get recipient email
                                recipient = default_recipient
                                if not recipient:
                                    st.error("❌ Please set a default email recipient in the sidebar.")
                                else:
                                    # Send the email
                                    result = send_email(
                                        to=recipient,
                                        subject=f"ZappBot Results: {resp['query']}",
                                        body=plain_text_body
                                    )
                                    st.success(f"✅ Email sent to {recipient}")
                            except Exception as e:
                                st.error(f"❌ Failed to send email: {str(e)}")
                
                # Job Match button
                with cols[2]:
                    if resp['processed']['resumes']:
                        if st.button("🎯 Match Jobs", key=f"job_btn_{i}"):
                            try:
                                # Extract resume IDs
                                resume_ids = []
                                for resume in resp['processed']['resumes']:
                                    resume_id = resume.get("resumeId")
                                    if resume_id:
                                        resume_ids.append(resume_id)
                                
                                if resume_ids:
                                    # Call agent to get job match counts
                                    response = st.session_state.agent_executor.invoke({
                                        "input": f"Get job match counts for these resume IDs: {resume_ids}"
                                    })
                                    
                                    # Parse the job match data from the agent response
                                    response_text = response["output"]
                                    if "jobsMatched" in response_text:
                                        try:
                                            # Extract job match data from response text
                                            matches_pattern = r"'results':\s*(\[.*?\])"
                                            matches_match = re.search(matches_pattern, response_text, re.DOTALL)
                                            if matches_match:
                                                # Clean up the string and parse it
                                                results_str = matches_match.group(1)
                                                # Replace single quotes with double quotes for JSON parsing
                                                results_str = results_str.replace("'", '"')
                                                match_data = json.loads(results_str)
                                                
                                                # Store job match data
                                                for item in match_data:
                                                    resume_id = item.get("resumeId")
                                                    if resume_id:
                                                        st.session_state.job_match_data[resume_id] = item.get("jobsMatched", 0)
                                                
                                                st.success(f"🎯 Job match data updated for {len(match_data)} resumes")
                                                st.rerun()
                                            else:
                                                st.error("❌ Could not parse job match data from response")
                                        except Exception as parse_error:
                                            st.error(f"❌ Failed to parse job match data: {str(parse_error)}")
                                    else:
                                        st.error("❌ No job match data found in response")
                                else:
                                    st.warning("⚠️ No resume IDs found")
                            except Exception as e:
                                st.error(f"❌ Failed to get job matches: {str(e)}")
                
                # Display conclusion if available
                if resp['processed'].get('conclusion_text'):
                    st.write(resp['processed']['conclusion_text'])
    
    # Show debug info if enabled
    if debug_mode:
        with st.expander("🐛 Debug Information"):
            st.subheader("💾 Memory Contents")
            st.json({i: msg.content for i, msg in enumerate(st.session_state.memory.chat_memory.messages)})
            
            st.subheader("🆔 Stored Resume IDs")
            st.json(st.session_state.resume_ids)
            
            st.subheader("📝 Processed Responses")
            for key, value in st.session_state.processed_responses.items():
                if "full_text" in value:
                    # Create a shorter version for display
                    shorter_value = {k: v for k, v in value.items() if k != "full_text"}
                    shorter_value["full_text_length"] = len(value["full_text"])
                    st.json({key: shorter_value})
                else:
                    st.json({key: value})
            
            st.subheader("🎯 Job Match Data")
            st.json(st.session_state.job_match_data)
    
    # Display MongoDB Queries in a separate expander
    if debug_mode and "mongo_queries" in st.session_state and st.session_state.mongo_queries:
        with st.expander("🗄️ Recent MongoDB Queries"):
            for i, q in enumerate(st.session_state.mongo_queries):
                st.markdown(f"**Query {i+1} - {q['timestamp']}**")
                st.code(q["query"], language="json")
                st.write("Parameters:")
                st.json(q["parameters"])
                if i < len(st.session_state.mongo_queries) - 1:
                    st.markdown("---")  # Add separator between queries
