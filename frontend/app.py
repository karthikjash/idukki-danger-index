"""
Streamlit Frontend for Idukki Monsoon Danger Index
Resident-facing interface with plain-language risk communication
"""

import streamlit as st
import pandas as pd
import sys
import os
from datetime import datetime

# Add project paths
sys.path.insert(0, '/home/homie/Projects/SSR_system')

from data.fetcher import fetch_all_data_for_locality, LOCALITIES
from index.calculator import compute_index_for_locality, DangerIndexCalculator
from index.map_generator import generate_danger_map

# Streamlit page config
st.set_page_config(
    page_title="Idukki Monsoon Danger Index",
    page_icon="🌧️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .header-section {
        text-align: center;
        padding: 20px 0;
        border-bottom: 3px solid #f39c12;
    }
    .danger-low {
        background-color: #d5f4e6;
        color: #1e8449;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #2ecc71;
    }
    .danger-moderate {
        background-color: #fef5e7;
        color: #9a3d00;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #f39c12;
    }
    .danger-high {
        background-color: #fadbd8;
        color: #922b20;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #e74c3c;
    }
    .danger-extreme {
        background-color: #f1948a;
        color: #4a0000;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #8b0000;
        font-weight: bold;
    }
    .metric-card {
        background-color: #ecf0f1;
        padding: 10px;
        border-radius: 5px;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
    <div class="header-section">
        <h1>🌧️ Idukki Monsoon Danger Index</h1>
        <p><i>Hyperlocal monsoon risk forecast for inner Idukki district, Kerala</i></p>
    </div>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("📍 Select Your Area")
selected_locality = st.sidebar.selectbox(
    "Choose your locality:",
    options=sorted(LOCALITIES.keys()),
    index=0
)

# Additional sidebar info
st.sidebar.markdown("---")
st.sidebar.markdown("### ℹ️ About This Tool")
st.sidebar.info("""
This tool provides **hyperlocal monsoon risk forecasts** for inner Idukki to help residents make informed decisions.

**Data sources:**
- Rainfall & weather: IMD (mausam.imd.gov.in)
- Cloud & precipitation: NASA MODIS/GPM
- Historical incidents: KSDMA (2004-present)
- Population & terrain: Census India, OSM/ISRO

**Updated:** Daily at 6 AM and 6 PM
""")

st.sidebar.markdown("---")
emergency_info = st.sidebar.expander("🆘 Emergency Contacts")
emergency_info.markdown("""
**When to call for help:**
- Any emergency: **112** (National Emergency)
- Kerala Disaster Helpline: **1077**
- Local Admin: Check your panchayat notice board

**Evacuation:** If told to evacuate, leave immediately. Go to your panchayat-designated shelter.
""")

# Main content
st.markdown(f"### 📌 {selected_locality}")

try:
    # Fetch data
    locality_data = fetch_all_data_for_locality(selected_locality)
    
    # Extract weather
    rainfall_df = locality_data['rainfall_forecast']
    current_rainfall = rainfall_df['rainfall_mm'].iloc[-1] if not rainfall_df.empty else 100
    
    weather_data = {
        'rainfall_mm': current_rainfall,
        'wind_mps': locality_data['wind_data']['wind_speed_mps'],
        'humidity_pct': locality_data['humidity_data']['relative_humidity_pct'],
        'cloud_cover_pct': locality_data['cloud_cover']['cloud_cover_pct']
    }
    
    # Compute index
    index_result = compute_index_for_locality(selected_locality, weather_data)
    
    # Display current danger index
    tier = index_result['tier']
    score = index_result['composite_score']
    color = index_result['color']
    description = index_result['description']
    
    # Tier-specific styling
    tier_class_map = {
        'Low': 'danger-low',
        'Moderate': 'danger-moderate',
        'High': 'danger-high',
        'Extreme': 'danger-extreme'
    }
    
    st.markdown(f"""
        <div class="{tier_class_map.get(tier, 'danger-moderate')}">
            <h2>⚠️ Current Danger Level: {tier}</h2>
            <p><b>Risk Score:</b> {score}/1.0</p>
            <p>{description}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Metrics row
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="🌦️ Environmental Severity",
            value=f"{index_result['environmental_severity']:.2f}",
            help="Rainfall intensity, wind speed, humidity, cloud cover"
        )
    
    with col2:
        st.metric(
            label="🏢 Structural Risk",
            value=f"{index_result['structural_risk']:.2f}",
            help="Terrain steepness, soil saturation, building vulnerability"
        )
    
    with col3:
        st.metric(
            label="👥 Human Threat",
            value=f"{index_result['human_threat']:.2f}",
            help="Population exposure, evacuation difficulty, accessibility"
        )
    
    # Detailed metrics
    st.markdown("---")
    st.markdown("### 📊 Current Weather Conditions")
    
    weather_col1, weather_col2, weather_col3, weather_col4 = st.columns(4)
    
    with weather_col1:
        st.metric("🌧️ Rainfall", f"{weather_data['rainfall_mm']:.1f} mm/day")
    with weather_col2:
        st.metric("💨 Wind Speed", f"{weather_data['wind_mps']:.1f} m/s")
    with weather_col3:
        st.metric("💧 Humidity", f"{weather_data['humidity_pct']:.0f}%")
    with weather_col4:
        st.metric("☁️ Cloud Cover", f"{weather_data['cloud_cover_pct']:.0f}%")
    
    # 7-day rainfall forecast
    st.markdown("---")
    st.markdown("### 📅 7-Day Rainfall Forecast")
    
    if not rainfall_df.empty:
        # Create chart data
        forecast_data = rainfall_df[['date', 'rainfall_mm']].copy()
        forecast_data['date'] = pd.to_datetime(forecast_data['date']).dt.strftime('%b %d')
        
        st.bar_chart(
            data=forecast_data.set_index('date'),
            use_container_width=True,
            height=300
        )
    else:
        st.info("Rainfall forecast data not available")
    
    # What to do / What not to do
    st.markdown("---")
    
    if tier == 'Low':
        st.markdown("""
        ✅ **What to do:**
        - Normal activities are safe
        - Continue regular work and movement
        - Stay alert during monsoon season
        
        ⚠️ **Stay prepared:**
        - Keep emergency numbers handy
        - Avoid non-essential travel to remote areas
        - Monitor updates daily
        """)
    
    elif tier == 'Moderate':
        st.markdown("""
        ⚠️ **What to do:**
        - Avoid unnecessary travel
        - Stay indoors during heavy downpours
        - Keep children and elderly indoors
        - Avoid crossing flooded areas
        
        ❌ **Don't do:**
        - Don't travel to hilly areas
        - Don't venture near streams/rivers
        - Don't ignore rainfall warnings
        """)
    
    elif tier == 'High':
        st.markdown("""
        🚨 **What to do:**
        - STAY INDOORS as much as possible
        - Avoid all non-essential travel
        - Keep go-bags packed (documents, valuables, water, medicines)
        - Monitor weather closely
        
        ❌ **Don't do:**
        - Don't travel on hilly roads
        - Don't venture outdoors alone
        - Don't approach landslide-prone areas
        - Don't ignore evacuation orders
        """)
    
    else:  # Extreme
        st.markdown("""
        🚨 **EXTREME RISK - FOLLOW EVACUATION ORDERS**
        
        **What to do:**
        - **EVACUATE immediately** if ordered by authorities
        - Go to your panchayat-designated shelter
        - Take essential documents, valuables, medicines
        - Keep away from rivers, streams, and dams
        
        ❌ **Don't do:**
        - Don't stay at home in at-risk areas
        - Don't travel to high-risk zones
        - Don't wait for reminders - leave early
        
        **Call for help:** 112 (Emergency) or 1077 (Kerala Disaster)
        """)
    
    # Historical incidents nearby
    st.markdown("---")
    st.markdown("### 📍 Past Incidents in This Region (2004-Present)")
    
    incidents = locality_data['historical_incidents']
    
    if not incidents.empty:
        # Filter incidents near this locality (within ~20km)
        lat, lon = LOCALITIES[selected_locality]['lat'], LOCALITIES[selected_locality]['lon']
        
        # Simple distance filter (rough approximation)
        incidents['distance'] = abs(incidents['latitude'] - lat) + abs(incidents['longitude'] - lon)
        nearby_incidents = incidents[incidents['distance'] < 0.2].sort_values('year', ascending=False)
        
        if not nearby_incidents.empty:
            for idx, incident in nearby_incidents.iterrows():
                severity_color = {
                    'low': '🟢',
                    'moderate': '🟡',
                    'high': '🔴',
                    'extreme': '🔴'
                }
                
                st.markdown(f"""
                {severity_color.get(incident['severity'].lower(), '⚪')} **{incident['year']}** — {incident['location']}
                
                **Type:** {incident['incident_type'].title() if isinstance(incident['incident_type'], str) else 'Unknown'}  
                **Severity:** {incident['severity'].title() if isinstance(incident['severity'], str) else 'Unknown'}
                
                _{incident['description']}_
                """)
        else:
            st.info("No major past incidents recorded very close to this locality in KSDMA records")
    
    # Footer with timestamp
    st.markdown("---")
    st.caption(f"Last computed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data sources: IMD, NASA, KSDMA, Census India")

except Exception as e:
    st.error(f"Error loading data for {selected_locality}: {e}")
    st.info("Please try refreshing the page or selecting a different locality")

# Show map toggle
st.markdown("---")
if st.button("🗺️ View Interactive Map"):
    st.markdown("### Interactive Danger Map")
    st.info("Generating map... This may take a moment.")
    
    try:
        # Compute all indices for map
        all_indices = {}
        all_incidents = None
        
        for locality in LOCALITIES.keys():
            try:
                loc_data = fetch_all_data_for_locality(locality)
                rainfall_df = loc_data['rainfall_forecast']
                current_rainfall = rainfall_df['rainfall_mm'].iloc[-1] if not rainfall_df.empty else 100
                
                weather = {
                    'rainfall_mm': current_rainfall,
                    'wind_mps': loc_data['wind_data']['wind_speed_mps'],
                    'humidity_pct': loc_data['humidity_data']['relative_humidity_pct'],
                    'cloud_cover_pct': loc_data['cloud_cover']['cloud_cover_pct']
                }
                
                result = compute_index_for_locality(locality, weather)
                all_indices[locality] = result
                
                if all_incidents is None:
                    all_incidents = loc_data['historical_incidents']
            
            except Exception as e:
                st.warning(f"Could not compute index for {locality}")
        
        # Generate and display map
        map_file = "/tmp/idukki_danger_map_streamlit.html"
        generate_danger_map(all_indices, all_incidents, map_file)
        
        with open(map_file, 'r') as f:
            map_html = f.read()
        
        st.components.v1.html(map_html, height=700)
    
    except Exception as e:
        st.error(f"Error generating map: {e}")
