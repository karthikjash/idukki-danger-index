#!/usr/bin/env python3
"""
Idukki Monsoon Danger Index — End-to-End Demo
Tests all components and generates sample output
"""

import sys
import os

# Ensure the project root is importable no matter where this script is run from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetcher import (fetch_all_data_for_locality, extract_current_weather,
                          LOCALITIES)
from index.calculator import compute_index_for_locality
from index.map_generator import generate_danger_map
import pandas as pd

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def demo():
    """Run end-to-end demo"""
    
    print_section("IDUKKI MONSOON DANGER INDEX — SYSTEM DEMO")
    
    # 1. Fetch data for all localities
    print_section("1. DATA FETCHING")
    print("Fetching weather, wind, humidity, and historical incident data...")
    
    all_indices = {}
    all_incidents = pd.DataFrame()
    fetched_data = {}
    
    for i, locality in enumerate(sorted(LOCALITIES.keys()), 1):
        try:
            data = fetch_all_data_for_locality(locality)
            fetched_data[locality] = data
            
            # Extract current conditions (nearest forecast day, not the last one)
            weather = extract_current_weather(data)
            
            print(f"{i}. {locality:15} → Rainfall: {weather['rainfall_mm']:6.1f} mm, "
                  f"Wind: {weather['wind_mps']:5.1f} m/s, Humidity: {weather['humidity_pct']:.0f}%")
            
            if all_incidents.empty and not data['historical_incidents'].empty:
                all_incidents = data['historical_incidents']
        
        except Exception as e:
            print(f"   {locality}: ERROR - {e}")
    
    # 2. Calculate Danger Indices
    print_section("2. COMPOSITE DANGER INDEX CALCULATION")
    print("Computing 4-tier Danger Index for each locality...")
    print()
    
    for locality in sorted(fetched_data.keys()):
        try:
            result = compute_index_for_locality(
                locality, extract_current_weather(fetched_data[locality]))
            all_indices[locality] = result
            
            # Display with tier icon
            tier_icons = {
                'Low': '🟢',
                'Moderate': '🟠',
                'High': '🔴',
                'Extreme': '🔴'
            }
            icon = tier_icons.get(result['tier'], '⚪')
            
            print(f"{icon} {result['locality']:15} | Tier: {result['tier']:10} | "
                  f"Score: {result['composite_score']:.2f} | "
                  f"E:{result['environmental_severity']:.2f} "
                  f"S:{result['structural_risk']:.2f} "
                  f"H:{result['human_threat']:.2f}")
        
        except Exception as e:
            print(f"   {locality}: ERROR - {e}")
    
    # 3. Generate statistics
    print_section("3. SUMMARY STATISTICS")
    
    tier_counts = {}
    for locality, data in all_indices.items():
        tier = data['tier']
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    
    print(f"Total Localities: {len(all_indices)}")
    print(f"Tier Breakdown:")
    for tier in ['Low', 'Moderate', 'High', 'Extreme']:
        count = tier_counts.get(tier, 0)
        icon = {
            'Low': '🟢',
            'Moderate': '🟠',
            'High': '🔴',
            'Extreme': '🔴'
        }.get(tier, '⚪')
        print(f"  {icon} {tier:10}: {count:2} localities")
    
    avg_score = sum(d['composite_score'] for d in all_indices.values()) / len(all_indices)
    print(f"\nAverage Danger Score: {avg_score:.2f}")
    
    # 4. Generate map
    print_section("4. INTERACTIVE MAP GENERATION")
    
    print("Generating interactive Folium map...")
    map_file = generate_danger_map(all_indices, all_incidents, 
                                   '/tmp/idukki_demo_map.html')
    
    import os
    file_size_kb = os.path.getsize(map_file) / 1024
    print(f"✓ Map generated: {map_file}")
    print(f"  File size: {file_size_kb:.1f} KB")
    
    # 5. Display sample locality detail
    print_section("5. SAMPLE RESIDENT VIEW (KUMILY)")
    
    kumily_data = all_indices.get('Kumily')
    if kumily_data:
        print(f"Locality: {kumily_data['locality']}")
        print(f"Current Danger Level: {kumily_data['tier']} (Score: {kumily_data['composite_score']})")
        print(f"\nSub-Scores:")
        print(f"  • Environmental Severity: {kumily_data['environmental_severity']:.2f}")
        print(f"  • Structural Risk: {kumily_data['structural_risk']:.2f}")
        print(f"  • Human Threat Level: {kumily_data['human_threat']:.2f}")
        print(f"\nPlain-Language Guidance:")
        print(f"  {kumily_data['description']}")
    
    # 6. Historical incidents
    print_section("6. HISTORICAL INCIDENTS (2004-PRESENT)")
    
    if not all_incidents.empty:
        print(f"Total Incidents Loaded: {len(all_incidents)}")
        print("\nRecent Incidents:")
        for idx, incident in all_incidents.sort_values('year', ascending=False).head(3).iterrows():
            print(f"  • {incident['year']} - {incident['location']} ({incident['incident_type']})")
            print(f"    Severity: {incident['severity']}")
            print(f"    {incident['description']}")
    else:
        print("No historical incidents data available")
    
    # Final summary
    print_section("DEMO COMPLETE ✓")
    
    print("Next Steps:")
    print("  1. Run the dashboard + API: python3 api/server.py (open http://localhost:8000)")
    print("  2. Run API Server: python3 api/server.py")
    print("  3. View Demo Map: open /tmp/idukki_demo_map.html")
    print("\nData Sources Used:")
    print("  ✓ IMD (Indian Meteorological Department)")
    print("  ✓ NASA EarthData (MODIS, GPM IMERG)")
    print("  ✓ KSDMA (Historical Incidents)")
    print("  ✓ Census India (Population)")
    print("\nDocumentation:")
    print("  ✓ README.md — Quick start guide")
    print("  ✓ docs/METHODOLOGY.md — Complete formula and rationale")
    print("  ✓ api/server.py — REST API reference")

if __name__ == '__main__':
    demo()
