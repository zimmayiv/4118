from flask import Flask, render_template, request, jsonify
import csv, math, json
import pandas as pd

app = Flask(__name__)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees).
    Returns distance in meters.
    """
    R = 6371000  # Earth's radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def point_to_line_distance(px, py, x1, y1, x2, y2):
    """
    Calculate the distance from a point (px, py) to a line segment 
    defined by points (x1, y1) and (x2, y2).
    Returns distance in meters using haversine for lat/lon coordinates.
    """
    # Calculate the line segment length
    line_length = haversine_distance(y1, x1, y2, x2)
    
    if line_length == 0:
        return haversine_distance(py, px, y1, x1)
    
    # Calculate the parameter t for the projection of point onto line
    # Using approximate cartesian coordinates (works for short distances)
    lat_scale = 111000  # meters per degree latitude
    lon_scale = 111000 * math.cos(math.radians(py))  # meters per degree longitude
    
    dx = (x2 - x1) * lon_scale
    dy = (y2 - y1) * lat_scale
    
    t = max(0, min(1, (((px - x1) * lon_scale) * dx + ((py - y1) * lat_scale) * dy) / (dx*dx + dy*dy)))
    
    # Find the closest point on the line segment
    closest_lon = x1 + t * (x2 - x1)
    closest_lat = y1 + t * (y2 - y1)
    
    return haversine_distance(py, px, closest_lat, closest_lon)

def filter_by_point(df, lat, lng, distance_m=100):
    """Filter dataframe for rows within distance_m of the given point."""
    def is_within_distance(row):
        if pd.isna(row['LAT']) or pd.isna(row['LON']):
            return False
        return haversine_distance(lat, lng, row['LAT'], row['LON']) <= distance_m
    
    return df[df.apply(is_within_distance, axis=1)]

def filter_by_linestring(df, points, distance_m=100):
    """Filter dataframe for rows within distance_m of the linestring."""
    def is_within_distance(row):
        if pd.isna(row['LAT']) or pd.isna(row['LON']):
            return False
        
        min_dist = float('inf')
        # Check distance to each segment of the linestring
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            dist = point_to_line_distance(
                row['LON'], row['LAT'],
                p1['lng'], p1['lat'],
                p2['lng'], p2['lat']
            )
            min_dist = min(min_dist, dist)
        
        return min_dist <= distance_m
    
    return df[df.apply(is_within_distance, axis=1)]

@app.route('/arrests', methods=['GET'])
def get_arrests():
    try:
        # Load the CSV file
        df = pd.read_csv('./static/202024arrests4118.csv')
        
        # Replace all NaN values with None for valid JSON serialization
        df = df.replace({pd.NA: None, float('nan'): None})
        df = df.where(pd.notnull(df), None)

        # Get the 'geo' parameter from query string
        geo_param = request.args.get('geo')
        
        if geo_param is None:
            # Return all rows, replacing NaN with None for valid JSON
            result = df.where(pd.notnull(df), None).to_dict(orient='records')
            try:
                return jsonify(result)
            except Exception as e:
                return jsonify({'error': str(e)})
        # Parse the geo parameter (expecting JSON format)
        try:
            geo = json.loads(geo_param)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid geo parameter format. Expected JSON list of dicts.'}), 400
        
        if not isinstance(geo, list) or len(geo) == 0:
            return jsonify({'error': 'geo parameter must be a non-empty list'}), 400
        
        # Validate the structure
        for point in geo:
            if not isinstance(point, dict) or 'lat' not in point or 'lng' not in point:
                return jsonify({'error': 'Each geo point must be a dict with "lat" and "lng" keys'}), 400
        
        # Filter based on number of points
        if len(geo) == 1:
            # Single point - return rows within 100m
            filtered_df = filter_by_point(df, geo[0]['lat'], geo[0]['lng'])
        else:
            # Multiple points - return rows within 100m of the linestring
            filtered_df = filter_by_linestring(df, geo)
        
        result = filtered_df.where(pd.notnull(filtered_df), None).to_dict(orient='records')
        return jsonify(result)
    except FileNotFoundError:
        return jsonify({'error': 'CSV file not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def home():
    return render_template('main.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
