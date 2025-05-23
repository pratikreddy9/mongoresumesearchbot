import streamlit as st
from typing import List, Dict, Any

def display_resume_grid(resumes, container=None):
    """
    Display resumes in a 4x4 grid layout with stunning glassmorphism cards.
    
    Args:
        resumes: List of resume dictionaries to display
        container: Optional Streamlit container to render into (defaults to st)
    """
    target = container if container else st
    
    if not resumes:
        target.warning("🔍 No resumes found matching the criteria.")
        return
    
    # 🎨 Ultra-modern CSS with glassmorphism and animations
    target.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    .resume-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 20px;
        padding: 20px 0;
    }
    
    .resume-card {
        background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%);
        backdrop-filter: blur(20px);
        border-radius: 20px;
        padding: 24px;
        border: 1px solid rgba(255,255,255,0.2);
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
        height: auto;
        min-height: 380px;
        box-shadow: 0 15px 35px rgba(0,0,0,0.1);
        font-family: 'Inter', sans-serif;
    }
    
    .resume-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, #FF6B6B, #4ECDC4, #45B7D1, #96CEB4, #FFEAA7);
        background-size: 200% 100%;
        animation: gradient-flow 3s linear infinite;
    }
    
    @keyframes gradient-flow {
        0% { background-position: 0% 0%; }
        100% { background-position: 200% 0%; }
    }
    
    .resume-card:hover {
        transform: translateY(-8px) scale(1.02);
        box-shadow: 0 25px 50px rgba(0,0,0,0.2);
        border: 1px solid rgba(255,255,255,0.3);
        background: linear-gradient(135deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.08) 100%);
    }
    
    .resume-card:hover::before {
        height: 4px;
        box-shadow: 0 0 20px rgba(255,107,107,0.5);
    }
    
    .resume-name {
        font-weight: 700;
        font-size: 22px;
        margin-bottom: 12px;
        color: #FFFFFF;
        text-shadow: 0 2px 10px rgba(0,0,0,0.3);
        background: linear-gradient(135deg, #FFD700, #FF6B6B);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: text-shimmer 2s ease-in-out infinite alternate;
    }
    
    @keyframes text-shimmer {
        0% { filter: brightness(1) hue-rotate(0deg); }
        100% { filter: brightness(1.2) hue-rotate(10deg); }
    }
    
    .resume-location {
        color: #B0BEC5;
        font-size: 14px;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        font-weight: 500;
    }
    
    .resume-contact {
        margin-bottom: 8px;
        font-size: 13px;
        color: #CFD8DC;
        display: flex;
        align-items: center;
        font-weight: 400;
        opacity: 0.9;
    }
    
    .resume-section-title {
        font-weight: 700;
        margin-top: 20px;
        margin-bottom: 12px;
        font-size: 16px;
        color: #FFFFFF;
        text-transform: uppercase;
        letter-spacing: 1px;
        position: relative;
        padding-left: 20px;
    }
    
    .resume-section-title::before {
        content: '';
        position: absolute;
        left: 0;
        top: 50%;
        transform: translateY(-50%);
        width: 12px;
        height: 12px;
        background: linear-gradient(135deg, #FF6B6B, #4ECDC4);
        border-radius: 50%;
        box-shadow: 0 0 10px rgba(255,107,107,0.5);
    }
    
    .resume-experience {
        font-size: 13px;
        color: #E0E0E0;
        margin-bottom: 6px;
        padding-left: 12px;
        position: relative;
        font-weight: 400;
        line-height: 1.4;
    }
    
    .resume-experience::before {
        content: '▸';
        position: absolute;
        left: 0;
        color: #4ECDC4;
        font-weight: bold;
    }
    
    .skill-tag {
        display: inline-block;
        background: linear-gradient(135deg, rgba(76, 175, 80, 0.2) 0%, rgba(76, 175, 80, 0.1) 100%);
        color: #81C784;
        border-radius: 20px;
        padding: 6px 14px;
        margin: 4px 6px 4px 0;
        font-size: 11px;
        font-weight: 600;
        border: 1px solid rgba(76, 175, 80, 0.3);
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .skill-tag:hover {
        transform: translateY(-2px);
        background: linear-gradient(135deg, rgba(76, 175, 80, 0.3) 0%, rgba(76, 175, 80, 0.2) 100%);
        box-shadow: 0 5px 15px rgba(76, 175, 80, 0.2);
        border: 1px solid rgba(76, 175, 80, 0.5);
    }
    
    .skill-tag.highlight {
        background: linear-gradient(135deg, #FF6B6B 0%, #FF8E8E 100%);
        color: white;
        border: 1px solid rgba(255, 107, 107, 0.5);
        box-shadow: 0 0 15px rgba(255, 107, 107, 0.3);
        animation: pulse-glow 2s ease-in-out infinite;
    }
    
    @keyframes pulse-glow {
        0%, 100% { box-shadow: 0 0 15px rgba(255, 107, 107, 0.3); }
        50% { box-shadow: 0 0 25px rgba(255, 107, 107, 0.5); }
    }
    
    .keyword-tag {
        display: inline-block;
        background: linear-gradient(135deg, rgba(255, 193, 7, 0.2) 0%, rgba(255, 193, 7, 0.1) 100%);
        color: #FFD54F;
        border-radius: 20px;
        padding: 6px 14px;
        margin: 4px 6px 4px 0;
        font-size: 11px;
        font-weight: 600;
        border: 1px solid rgba(255, 193, 7, 0.3);
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .keyword-tag:hover {
        transform: translateY(-2px);
        background: linear-gradient(135deg, rgba(255, 193, 7, 0.3) 0%, rgba(255, 193, 7, 0.2) 100%);
        box-shadow: 0 5px 15px rgba(255, 193, 7, 0.2);
        border: 1px solid rgba(255, 193, 7, 0.5);
    }
    
    .keyword-tag.highlight {
        background: linear-gradient(135deg, #FFC107 0%, #FFD54F 100%);
        color: #333;
        border: 1px solid rgba(255, 193, 7, 0.5);
        box-shadow: 0 0 15px rgba(255, 193, 7, 0.3);
        animation: pulse-glow-yellow 2s ease-in-out infinite;
    }
    
    @keyframes pulse-glow-yellow {
        0%, 100% { box-shadow: 0 0 15px rgba(255, 193, 7, 0.3); }
        50% { box-shadow: 0 0 25px rgba(255, 193, 7, 0.5); }
    }
    
    .job-matches {
        margin-top: 16px;
        padding: 10px 16px;
        background: linear-gradient(135deg, rgba(69, 183, 209, 0.2) 0%, rgba(69, 183, 209, 0.1) 100%);
        border-radius: 25px;
        display: inline-flex;
        align-items: center;
        font-size: 13px;
        color: #4FC3F7;
        font-weight: 700;
        border: 1px solid rgba(69, 183, 209, 0.3);
        backdrop-filter: blur(10px);
        animation: float 3s ease-in-out infinite;
    }
    
    @keyframes float {
        0%, 100% { transform: translateY(0px); }
        50% { transform: translateY(-3px); }
    }
    
    .job-matches::before {
        content: '🎯';
        margin-right: 8px;
        font-size: 16px;
    }
    
    .resume-id {
        font-size: 9px;
        color: rgba(255,255,255,0.4);
        margin-top: 16px;
        word-break: break-all;
        font-family: 'Courier New', monospace;
        background: rgba(0,0,0,0.2);
        padding: 4px 8px;
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .more-items {
        font-size: 11px;
        color: rgba(255,255,255,0.6);
        font-style: italic;
        margin-left: 8px;
        background: rgba(255,255,255,0.1);
        padding: 4px 10px;
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.2);
        backdrop-filter: blur(10px);
    }
    
    .stats-badge {
        position: absolute;
        top: 15px;
        right: 15px;
        background: linear-gradient(135deg, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0.4) 100%);
        color: white;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 10px;
        font-weight: 700;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255,255,255,0.2);
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    
    /* Mobile responsiveness */
    @media (max-width: 768px) {
        .resume-grid {
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }
        
        .resume-card {
            padding: 20px;
            min-height: 350px;
        }
        
        .resume-name {
            font-size: 20px;
        }
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Create a 4-column grid
    num_resumes = len(resumes)
    rows = (num_resumes + 3) // 4  # Ceiling division for number of rows
    
    # Highlighted terms for matching (you can make this configurable)
    highlight_terms = ['python', 'sql', 'mysql', 'postgresql', 'py', 'java', 'javascript', 'react', 'node']
    
    for row in range(rows):
        cols = target.columns(4)
        for col in range(4):
            idx = row * 4 + col
            if idx < num_resumes:
                resume = resumes[idx]
                
                # Extract resume data
                name = resume.get("name", "Unknown")
                email = resume.get("email", "")
                phone = resume.get("contactNo", "")
                location = resume.get("location", "")
                resume_id = resume.get("resumeId", "")
                
                # Get experience and skills
                experience = resume.get("experience", [])
                skills = resume.get("skills", [])
                keywords = resume.get("keywords", [])
                
                # Get job matches if available
                job_matches = resume.get("jobsMatched")
                
                with cols[col]:
                    # Calculate stats for badge
                    total_skills = len(skills) + len(keywords)
                    
                    html = f"""
                    <div class="resume-card" data-resume-id="{resume_id}">
                        <div class="stats-badge">{total_skills} Skills</div>
                        <div class="resume-name">{name}</div>
                        <div class="resume-location">📍 {location}</div>
                        <div class="resume-contact">📧 {email}</div>
                        <div class="resume-contact">📱 {phone}</div>
                    """
                    
                    # Add job matches if available
                    if job_matches is not None:
                        html += f'<div class="job-matches">Matched to {job_matches} jobs</div>'
                    
                    # Add experience section
                    if experience:
                        html += f'<div class="resume-section-title">💼 Experience</div>'
                        for exp in experience[:3]:  # Limit to 3 experiences
                            html += f'<div class="resume-experience">{exp}</div>'
                    
                    # Add skills section - Show MORE skills and highlight matches
                    if skills:
                        html += f'<div class="resume-section-title">🚀 Skills</div><div>'
                        
                        # Show first 12 skills instead of 7, with highlighting
                        skills_to_show = skills[:12]
                        for skill in skills_to_show:
                            skill_name = skill if isinstance(skill, str) else skill.get('skillName', '')
                            # Check if this skill should be highlighted
                            is_highlight = any(term.lower() in skill_name.lower() for term in highlight_terms)
                            highlight_class = ' highlight' if is_highlight else ''
                            html += f'<span class="skill-tag{highlight_class}">{skill_name}</span>'
                        
                        # Show count of remaining skills
                        if len(skills) > 12:
                            html += f'<span class="more-items">+{len(skills) - 12} more</span>'
                        
                        html += '</div>'
                    
                    # Add keywords section - Show MORE keywords and highlight matches
                    if keywords:
                        html += f'<div class="resume-section-title">🏷️ Keywords</div><div>'
                        
                        # Show first 10 keywords instead of 5, with highlighting
                        keywords_to_show = keywords[:10]
                        for keyword in keywords_to_show:
                            # Check if this keyword should be highlighted
                            is_highlight = any(term.lower() in keyword.lower() for term in highlight_terms)
                            highlight_class = ' highlight' if is_highlight else ''
                            html += f'<span class="keyword-tag{highlight_class}">{keyword}</span>'
                        
                        # Show count of remaining keywords
                        if len(keywords) > 10:
                            html += f'<span class="more-items">+{len(keywords) - 10} more</span>'
                        
                        html += '</div>'
                    
                    # Show resume ID in debug mode
                    debug_mode = getattr(st.session_state, 'debug_mode', False)
                    if debug_mode and resume_id:
                        html += f'<div class="resume-id">🆔 {resume_id}</div>'
                    
                    html += '</div>'
                    st.markdown(html, unsafe_allow_html=True)
