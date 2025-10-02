import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import json
from pathlib import Path
from datetime import datetime
import time
from checkpoint import CheckpointManager, STAGES
import subprocess
import pandas as pd

# Configure the page
st.set_page_config(
    page_title="AI News Alert System",
    page_icon="🤖",
    layout="wide",
)

# Custom CSS
st.markdown("""
    <style>
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #4CAF50, #2196F3);
    }
    .big-font {
        font-size: 24px !important;
    }
    .stat-card {
        padding: 20px;
        border-radius: 10px;
        background-color: #1E1E1E;
        margin: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# Auto-refresh every 3 seconds
st_autorefresh(interval=3000)

def create_gauge(value, title, max_value=100):
    return go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        title={'text': title},
        gauge={
            'axis': {'range': [0, max_value]},
            'bar': {'color': "#2196F3"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, max_value*0.33], 'color': '#EF9A9A'},
                {'range': [max_value*0.33, max_value*0.67], 'color': '#81C784'},
                {'range': [max_value*0.67, max_value], 'color': '#64B5F6'}
            ],
        }
    ))

def format_duration(start_time):
    duration = time.time() - start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    return f"{minutes:02d}:{seconds:02d}"

# Initialize session state
if 'start_time' not in st.session_state:
    st.session_state.start_time = time.time()
if 'process_running' not in st.session_state:
    st.session_state.process_running = False
if 'process' not in st.session_state:
    st.session_state.process = None

# Header
st.title("🤖 AI News Alert System")
st.markdown("### Real-time News Processing and Analysis")

# Main control buttons
col1, col2, col3 = st.columns([1,1,2])
with col1:
    if not st.session_state.process_running:
        if st.button("🚀 Start Processing", use_container_width=True):
            st.session_state.process = subprocess.Popen(["python", "main.py"])
            st.session_state.process_running = True
            st.session_state.start_time = time.time()
with col2:
    if st.session_state.process_running:
        if st.button("⏹️ Stop Processing", use_container_width=True):
            if st.session_state.process:
                st.session_state.process.terminate()
            st.session_state.process_running = False

# Initialize checkpoint manager
checkpoint_mgr = CheckpointManager()
stats = checkpoint_mgr.load_latest_checkpoint()

if stats:
    # Progress Section
    st.markdown("### 📊 Processing Progress")
    col1, col2 = st.columns(2)
    
    with col1:
        # Main progress bar
        stage_progress = stats.get('stage_progress', 0) * 100
        st.progress(stage_progress / 100, f"Stage Progress: {stage_progress:.1f}%")
        
        # Current stage info
        st.info(f"🔄 Current Stage: {stats.get('current_stage', 'Unknown')}")
        if stats.get('stage_details'):
            st.caption(f"Details: {stats['stage_details']}")
    
    with col2:
        # Time tracking
        duration = format_duration(st.session_state.start_time)
        st.metric("⏱️ Processing Time", duration)
        
        # Current feed being processed
        if stats.get('current_feed'):
            st.metric("📰 Processing Feed", stats['current_feed'])
    
    # Stats Cards
    st.markdown("### 📈 Processing Statistics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
            <div class="stat-card">
                <h3>Total Alerts</h3>
                <p class="big-font">%d</p>
            </div>
        """ % stats.get('total_alerts', 0), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
            <div class="stat-card">
                <h3>Filtered Alerts</h3>
                <p class="big-font">%d</p>
            </div>
        """ % stats.get('filtered_count', 0), unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
            <div class="stat-card">
                <h3>Avg Tokens/Item</h3>
                <p class="big-font">%.1f</p>
            </div>
        """ % stats.get('avg_tokens_per_item', 0), unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
            <div class="stat-card">
                <h3>Error Count</h3>
                <p class="big-font">%d</p>
            </div>
        """ % stats.get('error_count', 0), unsafe_allow_html=True)
    
    # Gauges
    st.markdown("### 🎯 Performance Metrics")
    col1, col2 = st.columns(2)
    
    with col1:
        fig = create_gauge(
            stats.get('filtered_count', 0) / max(stats.get('total_alerts', 1), 1) * 100,
            "Filter Rate (%)"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = create_gauge(
            min(stats.get('tokens_processed', 0) / 1000, 100),
            "Tokens Processed (K)",
            max_value=100
        )
        st.plotly_chart(fig, use_container_width=True)

    # Show final results if available
    final_folder = Path("final")
    if final_folder.exists():
        latest_final = max(final_folder.glob("*.json"), key=lambda x: x.stat().st_mtime, default=None)
        if latest_final:
            st.markdown("### 🎉 Latest Results")
            try:
                results = json.loads(latest_final.read_text())
                df = pd.DataFrame(results)
                st.dataframe(
                    df[['title', 'published', 'summary', 'link']],
                    column_config={
                        "link": st.column_config.LinkColumn("Link"),
                        "title": "Title",
                        "published": "Published",
                        "summary": "Summary"
                    },
                    hide_index=True,
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Error loading results: {e}")
else:
    st.info("👆 Click 'Start Processing' to begin news analysis")
