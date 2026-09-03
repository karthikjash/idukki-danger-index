"""
Interactive Map Generator for Idukki Monsoon Danger Index
Creates Folium map with color-coded zones and historical incident overlay
"""

import folium
from folium import plugins
import pandas as pd
import numpy as np
from typing import Dict, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Idukki district center
IDUKKI_CENTER = [9.65, 76.80]

# Locality coordinates and bounds
LOCALITY_COORDS = {
    'Kumily': {'lat': 9.655, 'lon': 76.775, 'radius': 8000},
    'Peermedu': {'lat': 9.545, 'lon': 76.615, 'radius': 6000},
    'Idukki': {'lat': 9.725, 'lon': 76.805, 'radius': 7000},
    'Adimali': {'lat': 9.575, 'lon': 76.895, 'radius': 7500},
    'Kattappana': {'lat': 9.650, 'lon': 76.925, 'radius': 6500},
    'Munnar': {'lat': 10.089, 'lon': 76.766, 'radius': 8000},
    'Nedumkandam': {'lat': 9.800, 'lon': 76.868, 'radius': 5500}
}


class IdukiMapGenerator:
    """Generate interactive Folium map for Danger Index"""
    
    def __init__(self, center=IDUKKI_CENTER, zoom_start=11):
        """Initialize map centered on Idukki"""
        self.map = folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles='OpenStreetMap',
            prefer_canvas=True
        )
        self.center = center
    
    def add_danger_zones(self, locality_indices: Dict[str, Dict]):
        """
        Add color-coded zones for each locality based on Danger Index
        
        Args:
            locality_indices: Dict of {locality_name: index_result}
        """
        
        for locality, index_result in locality_indices.items():
            if locality not in LOCALITY_COORDS:
                logger.warning(f"Locality {locality} not found in coordinates")
                continue
            
            coords = LOCALITY_COORDS[locality]
            tier = index_result['tier']
            color = index_result['color']
            score = index_result['composite_score']
            
            # Add circle marker for each zone
            folium.Circle(
                location=[coords['lat'], coords['lon']],
                radius=coords['radius'],
                popup=folium.Popup(
                    f"<b>{locality}</b><br>"
                    f"<b>Danger Index: {tier}</b><br>"
                    f"Score: {score}<br>"
                    f"<i>{index_result['description'][:100]}...</i>",
                    max_width=300
                ),
                tooltip=f"{locality}: {tier} ({score})",
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.5,
                weight=2
            ).add_to(self.map)
            
            # Add label marker
            folium.Marker(
                location=[coords['lat'], coords['lon']],
                popup=f"<b>{locality}</b><br>Risk: {tier}",
                icon=folium.Icon(
                    color=self._get_folium_color(color),
                    icon='info-sign'
                ),
                tooltip=f"{locality}"
            ).add_to(self.map)
            
            logger.info(f"Added zone: {locality} ({tier})")
    
    def add_historical_incidents(self, incidents_df: pd.DataFrame, toggleable: bool = True):
        """
        Add historical incident markers (landslides, floods, dam incidents)
        
        Args:
            incidents_df: DataFrame with columns [latitude, longitude, incident_type, year, severity, location, description]
            toggleable: If True, add to feature group for toggle control
        """
        
        if incidents_df.empty:
            logger.warning("No historical incidents to display")
            return
        
        # Create feature group for incidents
        incident_group = folium.FeatureGroup(name='📍 Historical Incidents (2004-Present)', show=True)
        
        # Icon mapping for incident types (use Folium-compatible colors)
        incident_icons = {
            'landslide': {'color': 'red', 'icon': 'warning'},
            'flood': {'color': 'blue', 'icon': 'tint'},
            'dam': {'color': 'purple', 'icon': 'exclamation'},
            'debris': {'color': 'orange', 'icon': 'arrow-down'}
        }
        
        for idx, incident in incidents_df.iterrows():
            incident_type = incident['incident_type'].lower()
            icon_config = incident_icons.get(incident_type, {'color': 'gray', 'icon': 'question'})
            
            popup_text = (
                f"<b>{incident['incident_type'].upper()}</b><br>"
                f"<b>Year:</b> {incident['year']}<br>"
                f"<b>Severity:</b> {incident['severity']}<br>"
                f"<b>Location:</b> {incident['location']}<br>"
                f"<b>Details:</b> {incident['description']}"
            )
            
            marker = folium.Marker(
                location=[incident['latitude'], incident['longitude']],
                popup=folium.Popup(popup_text, max_width=300),
                icon=folium.Icon(
                    color=icon_config['color'],
                    icon=icon_config['icon'],
                    prefix='fa'
                ),
                tooltip=f"{incident['incident_type']} ({incident['year']})"
            )
            
            marker.add_to(incident_group)
        
        incident_group.add_to(self.map)
        logger.info(f"Added {len(incidents_df)} historical incidents")
    
    def add_legend(self):
        """Add legend for Danger Index tiers"""
        
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 50px; right: 50px; width: 250px; height: auto;
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px; border-radius: 5px;">
            
            <b style="font-size: 16px;">🌧️ Monsoon Danger Index</b><br>
            <hr style="margin: 5px 0;">
            
            <div style="margin: 8px 0;">
                <span style="background-color: #2ecc71; padding: 3px 8px; border-radius: 3px; font-weight: bold;">█</span>
                <b>LOW</b> - Safe conditions
            </div>
            
            <div style="margin: 8px 0;">
                <span style="background-color: #f39c12; padding: 3px 8px; border-radius: 3px; font-weight: bold;">█</span>
                <b>MODERATE</b> - Caution advised
            </div>
            
            <div style="margin: 8px 0;">
                <span style="background-color: #e74c3c; padding: 3px 8px; border-radius: 3px; font-weight: bold;">█</span>
                <b>HIGH</b> - Stay indoors
            </div>
            
            <div style="margin: 8px 0;">
                <span style="background-color: #8b0000; padding: 3px 8px; border-radius: 3px; font-weight: bold;">█</span>
                <b>EXTREME</b> - Evacuate!
            </div>
            
            <hr style="margin: 5px 0;">
            <div style="margin: 8px 0; font-size: 12px;">
                <b>📍 Markers:</b> Past incidents (2004-2024)
            </div>
        </div>
        '''
        
        self.map.get_root().html.add_child(folium.Element(legend_html))
        logger.info("Added legend")
    
    def add_controls(self):
        """Add layer control and other interactive controls"""
        folium.LayerControl().add_to(self.map)
    
    def save_map(self, filepath: str):
        """Save map to HTML file"""
        self.map.save(filepath)
        logger.info(f"Map saved to {filepath}")
        return filepath
    
    @staticmethod
    def _get_folium_color(hex_color: str) -> str:
        """Convert hex color to Folium color name"""
        color_map = {
            '#2ecc71': 'green',
            '#f39c12': 'orange',
            '#e74c3c': 'red',
            '#8b0000': 'darkred'
        }
        return color_map.get(hex_color, 'gray')


def generate_danger_map(locality_indices: Dict[str, Dict], 
                       historical_incidents: pd.DataFrame,
                       output_file: str = 'idukki_danger_map.html') -> str:
    """
    Generate complete interactive danger map
    
    Args:
        locality_indices: {locality: index_result}
        historical_incidents: DataFrame of past incidents
        output_file: Path to save HTML map
    
    Returns:
        Path to saved map file
    """
    
    # Create map
    map_gen = IdukiMapGenerator()
    
    # Add danger zones
    map_gen.add_danger_zones(locality_indices)
    
    # Add historical incidents
    map_gen.add_historical_incidents(historical_incidents, toggleable=True)
    
    # Add legend and controls
    map_gen.add_legend()
    map_gen.add_controls()
    
    # Save
    return map_gen.save_map(output_file)


if __name__ == '__main__':
    # Test with sample data
    sample_indices = {
        'Kumily': {
            'tier': 'High',
            'composite_score': 0.72,
            'color': '#e74c3c',
            'description': 'Current risk is HIGH.'
        },
        'Peermedu': {
            'tier': 'Extreme',
            'composite_score': 0.85,
            'color': '#8b0000',
            'description': 'Current risk is EXTREME.'
        },
        'Idukki': {
            'tier': 'Moderate',
            'composite_score': 0.48,
            'color': '#f39c12',
            'description': 'Current risk is MODERATE.'
        }
    }
    
    sample_incidents = pd.DataFrame({
        'latitude': [9.655, 9.545, 9.575],
        'longitude': [76.775, 76.615, 76.895],
        'incident_type': ['landslide', 'flood', 'landslide'],
        'year': [2018, 2019, 2018],
        'severity': ['high', 'extreme', 'moderate'],
        'location': ['Near Kumily', 'Peermedu Region', 'Adimali'],
        'description': ['Heavy monsoon landslide', 'Flash flood event', 'Debris flow']
    })
    
    map_file = generate_danger_map(sample_indices, sample_incidents, 'test_map.html')
    print(f"Test map generated: {map_file}")
