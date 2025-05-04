import requests
import json
import pandas as pd
import sqlite3
import streamlit as st
from datetime import datetime, timedelta
import time
import matplotlib.pyplot as plt
import seaborn as sns
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


st.set_page_config(
    page_title="NASA Near-Earth Object Tracker",
    page_icon="🚀",
    layout="wide"
)

def setup_database():
    """Create SQLite database and required tables, or update schema if needed"""
    conn = sqlite3.connect('nasa_neo_data.db')
    cursor = conn.cursor()
    

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS asteroids (
        id INTEGER PRIMARY KEY,
        neo_reference_id INTEGER,
        name TEXT,
        absolute_magnitude_h FLOAT,
        estimated_diameter_min_km FLOAT,
        estimated_diameter_max_km FLOAT,
        is_potentially_hazardous_asteroid BOOLEAN
    )
    ''')
    

    cursor.execute("PRAGMA table_info(asteroids)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'neo_reference_id' not in columns:
        logger.debug("Adding neo_reference_id column to asteroids table")
        cursor.execute('ALTER TABLE asteroids ADD COLUMN neo_reference_id INTEGER')

        cursor.execute('UPDATE asteroids SET neo_reference_id = id WHERE neo_reference_id IS NULL')

        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_neo_reference_id_unique ON asteroids(neo_reference_id)')
    

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS close_approach (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        neo_reference_id INTEGER,
        close_approach_date DATE,
        relative_velocity_kmph FLOAT,
        astronomical FLOAT,
        miss_distance_km FLOAT,
        miss_distance_lunar FLOAT,
        orbiting_body TEXT,
        FOREIGN KEY (neo_reference_id) REFERENCES asteroids(neo_reference_id)
    )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_neo_reference_id ON close_approach(neo_reference_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_close_approach_date ON close_approach(close_approach_date)')
    
    conn.commit()
    conn.close()


def fetch_nasa_neo_data(api_key, start_date, days_to_fetch=None, max_records=10000):
    """
    Fetch Near-Earth Object data from NASA API
    
    Parameters:
    - api_key: Your NASA API key
    - start_date: Initial date to start fetching from (YYYY-MM-DD)
    - days_to_fetch: Number of 7-day periods to fetch (None = until max_records)
    - max_records: Maximum number of asteroid records to collect
    
    Returns:
    - asteroid_data: List of dicts with asteroid information
    - approach_data: List of dicts with close approach information
    """
    asteroid_data = []
    approach_data = []
    record_count = 0
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    periods_fetched = 0
    
    if not days_to_fetch:
        progress_text = f"Fetching NASA NEO data (target: {max_records} records)"
    else:
        progress_text = f"Fetching NASA NEO data for {days_to_fetch} periods"
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while True:

        end_date = current_date + timedelta(days=6)
        
        start_str = current_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        status_text.text(f"{progress_text}: Processing {start_str} to {end_str}")
        
        url = f"https://api.nasa.gov/neo/rest/v1/feed?start_date={start_str}&end_date={end_str}&api_key={api_key}"
        
        try:
            response = requests.get(url)
            if response.status_code != 200:
                st.error(f"Error fetching data: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            
            for date_str, daily_asteroids in data["near_earth_objects"].items():
                for asteroid in daily_asteroids:
                    if not all([
                        asteroid.get("id"),
                        asteroid.get("neo_reference_id"),
                        asteroid.get("name"),
                        asteroid.get("close_approach_data")
                    ]):
                        continue
                    
                    asteroid_info = {
                        "id": int(asteroid.get("id")),
                        "neo_reference_id": int(asteroid.get("neo_reference_id")),
                        "name": asteroid.get("name"),
                        "absolute_magnitude_h": float(asteroid.get("absolute_magnitude_h")) if asteroid.get("absolute_magnitude_h") else None,
                        "estimated_diameter_min_km": float(asteroid.get("estimated_diameter", {}).get("kilometers", {}).get("estimated_diameter_min", 0)),
                        "estimated_diameter_max_km": float(asteroid.get("estimated_diameter", {}).get("kilometers", {}).get("estimated_diameter_max", 0)),
                        "is_potentially_hazardous_asteroid": asteroid.get("is_potentially_hazardous_asteroid", False)
                    }
                    
                    for approach in asteroid.get("close_approach_data", []):
                        if not approach.get("close_approach_date"):
                            continue
                        approach_info = {
                            "neo_reference_id": int(asteroid.get("neo_reference_id")),
                            "close_approach_date": approach.get("close_approach_date"),
                            "relative_velocity_kmph": float(approach.get("relative_velocity", {}).get("kilometers_per_hour", 0)),
                            "astronomical": float(approach.get("miss_distance", {}).get("astronomical", 0)),
                            "miss_distance_km": float(approach.get("miss_distance", {}).get("kilometers", 0)),
                            "miss_distance_lunar": float(approach.get("miss_distance", {}).get("lunar", 0)),
                            "orbiting_body": approach.get("orbiting_body", "Earth")
                        }
                        approach_data.append(approach_info)
                    
                    asteroid_data.append(asteroid_info)
                    record_count += 1
            
            if days_to_fetch:
                progress_bar.progress(min(1.0, (periods_fetched + 1) / days_to_fetch))
            else:
                progress_bar.progress(min(1.0, record_count / max_records))
            
            periods_fetched += 1
            if (days_to_fetch and periods_fetched >= days_to_fetch) or record_count >= max_records:
                break
            
            current_date = end_date + timedelta(days=1)
            
            time.sleep(0.1)
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            break
    
    progress_bar.empty()
    status_text.empty()
    
    return asteroid_data[:max_records], approach_data

def insert_data_to_database(asteroid_data, approach_data):
    """Insert the fetched data into SQLite database"""
    conn = sqlite3.connect('nasa_neo_data.db')
    cursor = conn.cursor()
    
    for asteroid in asteroid_data:
        cursor.execute('''
        INSERT OR IGNORE INTO asteroids (id, neo_reference_id, name, absolute_magnitude_h, 
                                        estimated_diameter_min_km, estimated_diameter_max_km, 
                                        is_potentially_hazardous_asteroid)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            asteroid["id"],
            asteroid["neo_reference_id"],
            asteroid["name"],
            asteroid["absolute_magnitude_h"],
            asteroid["estimated_diameter_min_km"],
            asteroid["estimated_diameter_max_km"],
            asteroid["is_potentially_hazardous_asteroid"]
        ))
    
    for approach in approach_data:
        cursor.execute('''
        INSERT INTO close_approach (neo_reference_id, close_approach_date, relative_velocity_kmph,
                                  astronomical, miss_distance_km, miss_distance_lunar, orbiting_body)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            approach["neo_reference_id"],
            approach["close_approach_date"],
            approach["relative_velocity_kmph"],
            approach["astronomical"],
            approach["miss_distance_km"],
            approach["miss_distance_lunar"],
            approach["orbiting_body"]
        ))
    
    conn.commit()
    conn.close()
    
    return len(asteroid_data), len(approach_data)

def delete_all_records():
    """Delete all records from asteroids and close_approach tables"""
    logger.debug("Attempting to delete all records from database")
    try:
        conn = sqlite3.connect('nasa_neo_data.db')
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM close_approach")
        cursor.execute("DELETE FROM asteroids")
        
        conn.commit()
        logger.debug("Successfully deleted all records")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Failed to delete records: {str(e)}")
        conn.close()
        raise Exception(f"Failed to delete records: {str(e)}")

def database_has_data():
    """Check if the database already has asteroid data"""
    try:
        conn = sqlite3.connect('nasa_neo_data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM asteroids")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False

def get_predefined_queries():
    return {
        "1. Count approaches per asteroid": """
            SELECT a.name, COUNT(c.id) as approach_count
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            GROUP BY a.id, a.name
            ORDER BY approach_count DESC
            LIMIT 20
        """,
        "2. Average velocity per asteroid": """
            SELECT a.name, AVG(c.relative_velocity_kmph) as avg_velocity
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            GROUP BY a.id, a.name
            ORDER BY avg_velocity DESC
            LIMIT 20
        """,
        "3. Top 10 fastest asteroids": """
            SELECT a.name, MAX(c.relative_velocity_kmph) as max_velocity
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            GROUP BY a.id, a.name
            ORDER BY max_velocity DESC
            LIMIT 10
        """,
        "4. Hazardous asteroids with 3+ approaches": """
            SELECT a.name, COUNT(c.id) as approach_count
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            WHERE a.is_potentially_hazardous_asteroid = 1
            GROUP BY a.id, a.name
            HAVING COUNT(c.id) > 3
            ORDER BY approach_count DESC
        """,
        "5. Month with most asteroid approaches": """
            SELECT strftime('%Y-%m', c.close_approach_date) as month, COUNT(*) as approach_count
            FROM close_approach c
            GROUP BY month
            ORDER BY approach_count DESC
            LIMIT 10
        """,
        "6. Asteroid with fastest approach speed": """
            SELECT a.name, c.close_approach_date, c.relative_velocity_kmph
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            ORDER BY c.relative_velocity_kmph DESC
            LIMIT 1
        """,
        "7. Asteroids by max diameter (desc)": """
            SELECT name, estimated_diameter_max_km
            FROM asteroids
            ORDER BY estimated_diameter_max_km DESC
            LIMIT 20
        """,
        "8. Asteroids getting closer over time": """
            SELECT a.name, c.close_approach_date, c.miss_distance_km
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            WHERE a.id IN (
                SELECT neo_reference_id 
                FROM close_approach 
                GROUP BY neo_reference_id 
                HAVING COUNT(*) > 1
            )
            ORDER BY a.id, c.close_approach_date
            LIMIT 50
        """,
        "9. Closest approach per asteroid": """
            SELECT a.name, c.close_approach_date, MIN(c.miss_distance_km) as closest_approach_km
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            GROUP BY a.id, a.name
            ORDER BY closest_approach_km
            LIMIT 20
        """,
        "10. Fast asteroids (>50,000 km/h)": """
            SELECT DISTINCT a.name, c.relative_velocity_kmph
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            WHERE c.relative_velocity_kmph > 50000
            ORDER BY c.relative_velocity_kmph DESC
            LIMIT 30
        """,
        "11. Approach count by month": """
            SELECT strftime('%Y-%m', c.close_approach_date) as month, COUNT(*) as approach_count
            FROM close_approach c
            GROUP BY month
            ORDER BY month
        """,
        "12. Brightest asteroids (lowest magnitude)": """
            SELECT name, absolute_magnitude_h
            FROM asteroids
            ORDER BY absolute_magnitude_h
            LIMIT 20
        """,
        "13. Hazardous vs non-hazardous count": """
            SELECT 
                CASE is_potentially_hazardous_asteroid 
                    WHEN 1 THEN 'Hazardous' 
                    ELSE 'Non-Hazardous' 
                END as status,
                COUNT(*) as asteroid_count,
                ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM asteroids), 2) as percentage
            FROM asteroids
            GROUP BY is_potentially_hazardous_asteroid
        """,
        "14. Closer than Moon (<1 LD)": """
            SELECT a.name, c.close_approach_date, c.miss_distance_lunar
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            WHERE c.miss_distance_lunar < 1
            ORDER BY c.miss_distance_lunar
            LIMIT 30
        """,
        "15. Within 0.05 AU": """
            SELECT a.name, c.close_approach_date, c.astronomical
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            WHERE c.astronomical < 0.05
            ORDER BY c.astronomical
            LIMIT 30
        """,
        "16. Largest potentially hazardous": """
            SELECT name, estimated_diameter_max_km, is_potentially_hazardous_asteroid
            FROM asteroids
            WHERE is_potentially_hazardous_asteroid = 1
            ORDER BY estimated_diameter_max_km DESC
            LIMIT 20
        """,
        "17. Asteroids approaching multiple bodies": """
            SELECT a.name, c.orbiting_body, COUNT(*) as approach_count
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            GROUP BY a.id, a.name, c.orbiting_body
            ORDER BY approach_count DESC
            LIMIT 20
        """,
        "18. Asteroids by approach frequency": """
            SELECT a.name, COUNT(c.id) as approach_count, a.estimated_diameter_max_km
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            GROUP BY a.id, a.name
            ORDER BY approach_count DESC, a.estimated_diameter_max_km DESC
            LIMIT 20
        """,
        "19. Recent close approaches": """
            SELECT a.name, c.close_approach_date, c.miss_distance_km
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            ORDER BY c.close_approach_date DESC
            LIMIT 30
        """,
        "20. Size-velocity correlation": """
            SELECT a.name, a.estimated_diameter_max_km, AVG(c.relative_velocity_kmph) as avg_velocity
            FROM asteroids a
            JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
            GROUP BY a.id, a.name
            ORDER BY a.estimated_diameter_max_km DESC
            LIMIT 30
        """
    }

def execute_query(query):
    """Execute a SQL query and return results as a DataFrame"""
    conn = sqlite3.connect('nasa_neo_data.db')
    try:
        results = pd.read_sql_query(query, conn)
        conn.close()
        return results
    except Exception as e:
        conn.close()
        st.error(f"Query execution failed: {str(e)}")
        return pd.DataFrame()

def visualize_results(df, query_name):
    """Create appropriate visualizations based on the query results"""
    if df.empty:
        st.warning("No data available for visualization")
        return
    
    try:
        if "count" in query_name.lower() or "vs" in query_name.lower():
            fig, ax = plt.subplots(figsize=(10, max(6, min(df.shape[0] * 0.3, 15))))
            sns.barplot(data=df.head(20), y=df.columns[0], x=df.columns[1], ax=ax)
            plt.xlabel(df.columns[1])
            plt.ylabel(df.columns[0])
            plt.title(query_name)
            plt.tight_layout()
            st.pyplot(fig)
        
        elif "month" in query_name.lower() and "by month" in query_name.lower():
            fig, ax = plt.subplots(figsize=(12, 6))
            sns.lineplot(data=df, x=df.columns[0], y=df.columns[1], marker='o', ax=ax)
            plt.xlabel('Month')
            plt.ylabel('Count')
            plt.title(query_name)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig)
        
        elif ("diameter" in query_name.lower() or "size" in query_name.lower()) and "correlation" in query_name.lower():
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.scatterplot(data=df, x=df.columns[1], y=df.columns[2], ax=ax)
            plt.xlabel('Diameter (km)')
            plt.ylabel('Average Velocity (km/h)')
            plt.title(query_name)
            plt.tight_layout()
            st.pyplot(fig)
        
        elif "velocity" in query_name.lower() and "fastest" not in query_name.lower():
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.histplot(data=df, x=df.columns[1], bins=30, ax=ax)
            plt.xlabel('Velocity (km/h)')
            plt.ylabel('Count')
            plt.title(query_name)
            plt.tight_layout()
            st.pyplot(fig)
        
        elif "diameter" in query_name.lower():
            fig, ax = plt.subplots(figsize=(10, 6))
            sns.boxplot(data=df, y=df.columns[1], ax=ax)
            plt.ylabel('Diameter (km)')
            plt.title(query_name)
            plt.tight_layout()
            st.pyplot(fig)
    except Exception as e:
        st.warning(f"Could not generate visualization: {str(e)}")

def filter_data(date_range, au_range, lunar_range, velocity_range, diameter_range, hazardous):
    """Apply filters to asteroid data and return filtered results"""
    conn = sqlite3.connect('nasa_neo_data.db')
    
    query = """
    SELECT a.id, a.neo_reference_id, a.name, a.absolute_magnitude_h, 
           a.estimated_diameter_min_km, a.estimated_diameter_max_km, 
           a.is_potentially_hazardous_asteroid, c.close_approach_date, 
           c.relative_velocity_kmph, c.astronomical, c.miss_distance_km, 
           c.miss_distance_lunar, c.orbiting_body
    FROM asteroids a
    JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id
    WHERE 1=1
    """
    
    params = []

    if date_range and len(date_range) == 2:
        start_date, end_date = date_range
        query += " AND c.close_approach_date BETWEEN ? AND ?"
        params.extend([start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")])
    if au_range:
        min_au, max_au = au_range
        query += " AND c.astronomical BETWEEN ? AND ?"
        params.extend([min_au, max_au])

    if lunar_range:
        min_lunar, max_lunar = lunar_range
        query += " AND c.miss_distance_lunar BETWEEN ? AND ?"
        params.extend([min_lunar, max_lunar])
    
    if velocity_range:
        min_velocity, max_velocity = velocity_range
        query += " AND c.relative_velocity_kmph BETWEEN ? AND ?"
        params.extend([min_velocity, max_velocity])
    
    if diameter_range:
        min_diameter, max_diameter = diameter_range
        query += " AND a.estimated_diameter_max_km BETWEEN ? AND ?"
        params.extend([min_diameter, max_diameter])
    
    if hazardous is not None:
        query += " AND a.is_potentially_hazardous_asteroid = ?"
        params.append(1 if hazardous else 0)
    
    query += " LIMIT 1000"
    
    try:
        results = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return results
    except Exception as e:
        conn.close()
        st.error(f"Filter query failed: {str(e)}")
        return pd.DataFrame()
    
def main():
    st.title("🚀 NASA Near-Earth Object (NEO) Tracker")
    st.markdown("Explore data about asteroids that have passed near Earth.")
    
    setup_database()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Select a page", ["Data Collection", "Predefined Queries", "Custom Filters"])
    
    if page == "Data Collection":
        st.header("🛰️ Collect NASA NEO Data")

        has_data = database_has_data()
        if has_data:
            st.info("Database already contains asteroid data. You can add more data, delete all records, or explore using the sidebar options.")
        
        
        st.subheader("Collect New Data")
        with st.form("data_collection_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                api_key = st.text_input("NASA API Key", placeholder="Enter your API key from api.nasa.gov", 
                                        help="Get your free API key from https://api.nasa.gov")
                start_date = st.date_input("Start Date", value=datetime(2024, 1, 1), 
                                           help="Date to start collecting data from")
            
            with col2:
                collection_option = st.radio("Collection Option", 
                                            ["Fetch specific number of periods", "Fetch up to 10,000 records"],
                                            index=1,
                                            help="Choose how to limit data collection")
                
                if collection_option == "Fetch specific number of periods":
                    num_periods = st.number_input("Number of 7-day periods", min_value=1, max_value=100, value=10,
                                                  help="Each period is 7 days of data")
                    max_records = None
                else:
                    num_periods = None
                    max_records = st.number_input("Maximum records to collect", min_value=100, max_value=10000, value=10000,
                                                  help="Limit the total number of asteroid records to collect")
            
            submit_button = st.form_submit_button("Collect Data")
        if submit_button:
            if not api_key:
                st.error("Please enter your NASA API key")
            else:
                start_time = time.time()
                asteroid_data, approach_data = fetch_nasa_neo_data(
                    api_key=api_key,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    days_to_fetch=num_periods,
                    max_records=max_records or 10000
                )
                
                if asteroid_data:
                    try:
                        a_count, c_count = insert_data_to_database(asteroid_data, approach_data)
                        end_time = time.time()
                        
                        st.success(f"✅ Successfully collected {a_count} asteroid records with {c_count} approach events " +
                                   f"in {end_time - start_time:.2f} seconds")
                        
                        if a_count > 0:
                            st.subheader("Sample of collected asteroid data")
                            conn = sqlite3.connect('nasa_neo_data.db')
                            sample_data = pd.read_sql_query(
                                "SELECT a.id, a.neo_reference_id, a.name, a.is_potentially_hazardous_asteroid, " +
                                "c.close_approach_date, c.miss_distance_km, c.relative_velocity_kmph, c.astronomical, " +
                                "c.miss_distance_lunar, c.orbiting_body " +
                                "FROM asteroids a JOIN close_approach c ON a.neo_reference_id = c.neo_reference_id LIMIT 10", 
                                conn
                            )
                            conn.close()
                            st.dataframe(sample_data)
                    except Exception as e:
                        st.error(f"Failed to insert data: {str(e)}")
                else:
                    st.error("Failed to collect data. Please check your API key and try again.")
        st.subheader("Clear Database")
        with st.form("delete_records_form"):
            st.warning("This will delete all records from the database. This action cannot be undone.")
            confirm_delete = st.checkbox("I confirm I want to delete all records")
            delete_button = st.form_submit_button("Delete All Records")
            
            if delete_button:
                if confirm_delete:
                    try:
                        delete_all_records()
                        st.success("✅ All records have been deleted from the database.")
                        logger.debug("Delete operation completed successfully")
                    except Exception as e:
                        st.error(f"Failed to delete records: {str(e)}")
                        logger.error(f"Delete operation failed: {str(e)}")
                else:
                    st.error("Please check the confirmation box to delete all records.")
        
        
    
    elif page == "Predefined Queries":
        st.header("📊 Predefined Analytical Queries")
        
        if not database_has_data():
            st.warning("No asteroid data found in database. Please collect data first.")
            return
        
        queries = get_predefined_queries()
        selected_query = st.selectbox("Select a query to analyze:", list(queries.keys()))
        
        query_descriptions = {
            "1. Count approaches per asteroid": "Shows how many times each asteroid has approached Earth.",
            "2. Average velocity per asteroid": "Calculates the average velocity of each asteroid over multiple approaches.",
            "3. Top 10 fastest asteroids": "Lists the top 10 asteroids with the highest velocity during approach.",
            "4. Hazardous asteroids with 3+ approaches": "Finds potentially hazardous asteroids that have approached Earth more than 3 times.",
            "5. Month with most asteroid approaches": "Identifies which month had the most asteroid approaches.",
            "6. Asteroid with fastest approach speed": "Shows the asteroid with the fastest ever approach speed.",
            "7. Asteroids by max diameter (desc)": "Sorts asteroids by their maximum estimated diameter in descending order.",
            "8. Asteroids getting closer over time": "Finds asteroids whose closest approach is getting nearer over time.",
            "9. Closest approach per asteroid": "Shows each asteroid with its closest approach distance.",
            "10. Fast asteroids (>50,000 km/h)": "Lists names of asteroids that approached Earth with velocity > 50,000 km/h.",
            "11. Approach count by month": "Counts how many approaches happened per month.",
            "12. Brightest asteroids (lowest magnitude)": "Finds asteroids with the highest brightness (lowest magnitude value).",
            "13. Hazardous vs non-hazardous count": "Shows the number of hazardous vs non-hazardous asteroids.",
            "14. Closer than Moon (<1 LD)": "Finds asteroids that passed closer than the Moon (< 1 lunar distance).",
            "15. Within 0.05 AU": "Finds asteroids that came within 0.05 astronomical units of Earth.",
            "16. Largest potentially hazardous": "Shows the largest asteroids that are classified as potentially hazardous.",
            "17. Asteroids approaching multiple bodies": "Shows which asteroids have approached different celestial bodies.",
            "18. Asteroids by approach frequency": "Ranks asteroids by how frequently they approach Earth.",
            "19. Recent close approaches": "Shows the most recent asteroid approaches in the dataset.",
            "20. Size-velocity correlation": "Explores the relationship between asteroid size and approach velocity."
        }
        
        st.markdown(f"**Description:** {query_descriptions.get(selected_query, '')}")
        
        if st.button("Run Query"):
            with st.spinner("Executing query..."):
                results = execute_query(queries[selected_query])
                
                if not results.empty:
                    st.subheader("Query Results")
                    st.dataframe(results)
                    
                    st.subheader("Visualization")
                    visualize_results(results, selected_query)
                    
                    csv = results.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "Download results as CSV",
                        csv,
                        f"{selected_query.replace(' ', '_').replace('.', '')}.csv",
                        "text/csv",
                        key=f"download_{selected_query}"
                    )
                else:
                    st.info("No results found for this query.")
    
    elif page == "Custom Filters":
        st.header("🔍 Filter Asteroid Data")
        
        if not database_has_data():
            st.warning("No asteroid data found in database. Please collect data first.")
            return
        
        conn = sqlite3.connect('nasa_neo_data.db')
        min_max_df = pd.read_sql_query("""
            SELECT 
                MIN(c.close_approach_date) as min_date,
                MAX(c.close_approach_date) as max_date,
                MIN(c.astronomical) as min_au,
                MAX(c.astronomical) as max_au,
                MIN(c.miss_distance_lunar) as min_lunar,
                MAX(c.miss_distance_lunar) as max_lunar,
                MIN(c.relative_velocity_kmph) as min_velocity,
                MAX(c.relative_velocity_kmph) as max_velocity,
                MIN(a.estimated_diameter_max_km) as min_diameter,
                MAX(a.estimated_diameter_max_km) as max_diameter
            FROM close_approach c
            JOIN asteroids a ON c.neo_reference_id = a.neo_reference_id
        """, conn)
        conn.close()
        
        if not min_max_df.empty:

            min_date = datetime.strptime(min_max_df['min_date'].iloc[0], "%Y-%m-%d")
            max_date = datetime.strptime(min_max_df['max_date'].iloc[0], "%Y-%m-%d")
            min_au = float(min_max_df['min_au'].iloc[0])
            max_au = min(float(min_max_df['max_au'].iloc[0]), 1.0)  
            min_lunar = float(min_max_df['min_lunar'].iloc[0])
            max_lunar = min(float(min_max_df['max_lunar'].iloc[0]), 100.0)  
            min_velocity = float(min_max_df['min_velocity'].iloc[0])
            max_velocity = min(float(min_max_df['max_velocity'].iloc[0]), 100000.0)  
            min_diameter = float(min_max_df['min_diameter'].iloc[0])
            max_diameter = min(float(min_max_df['max_diameter'].iloc[0]), 10.0)  
            
            st.sidebar.header("Filter Options")
            
            date_range = st.sidebar.date_input(
                "Approach Date Range",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                help="Select the range of dates for close approaches"
            )
            
            au_range = st.sidebar.slider(
                "Astronomical Units (AU)",
                min_value=min_au,
                max_value=max_au,
                value=(min_au, max_au),
                format="%.4f",
                help="Filter by distance in astronomical units (1 AU ≈ distance from Earth to Sun)"
            )
            
            lunar_range = st.sidebar.slider(
                "Lunar Distance (LD)",
                min_value=min_lunar,
                max_value=max_lunar,
                value=(min_lunar, max_lunar),
                format="%.2f",
                help="Filter by distance in lunar distances (1 LD ≈ distance from Earth to Moon)"
            )
            
            velocity_range = st.sidebar.slider(
                "Relative Velocity (km/h)",
                min_value=min_velocity,
                max_value=max_velocity,
                value=(min_velocity, max_velocity),
                format="%.0f",
                help="Filter by asteroid approach speed"
            )
            
            diameter_range = st.sidebar.slider(
                "Estimated Diameter (km)",
                min_value=min_diameter,
                max_value=max_diameter,
                value=(min_diameter, max_diameter),
                format="%.3f",
                help="Filter by maximum estimated asteroid diameter"
            )
            
            hazardous = st.sidebar.selectbox(
                "Hazardous Status",
                options=[None, True, False],
                format_func=lambda x: "All" if x is None else ("Hazardous" if x else "Non-Hazardous"),
                help="Filter by potentially hazardous asteroid status"
            )
            
            if st.sidebar.button("Apply Filters"):
                with st.spinner("Applying filters..."):
                    filtered_results = filter_data(
                        date_range=date_range,
                        au_range=au_range,
                        lunar_range=lunar_range,
                        velocity_range=velocity_range,
                        diameter_range=diameter_range,
                        hazardous=hazardous
                    )
                    
                    if not filtered_results.empty:
                        st.subheader("Filtered Results")
                        st.dataframe(filtered_results)
                        
                        st.subheader("Visualizations")
                        
                        fig, ax = plt.subplots(figsize=(10, 6))
                        sns.scatterplot(
                            data=filtered_results,
                            x="estimated_diameter_max_km",
                            y="relative_velocity_kmph",
                            hue="is_potentially_hazardous_asteroid",
                            size="miss_distance_lunar",
                            ax=ax
                        )
                        plt.xlabel("Max Diameter (km)")
                        plt.ylabel("Velocity (km/h)")
                        plt.title("Asteroid Size vs Velocity")
                        plt.tight_layout()
                        st.pyplot(fig)
                        
                        fig, ax = plt.subplots(figsize=(10, 6))
                        sns.histplot(
                            data=filtered_results,
                            x="miss_distance_km",
                            hue="is_potentially_hazardous_asteroid",
                            bins=30,
                            ax=ax
                        )
                        plt.xlabel("Miss Distance (km)")
                        plt.ylabel("Count")
                        plt.title("Distribution of Miss Distances")
                        plt.tight_layout()
                        st.pyplot(fig)
                        
                        csv = filtered_results.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "Download filtered results as CSV",
                            csv,
                            "filtered_asteroid_data.csv",
                            "text/csv",
                            key="download_filtered"
                        )
                    else:
                        st.info("No results found with the selected filters.")
        else:
            st.error("Unable to load filter ranges. Please ensure data is available in the database.")

if __name__ == "__main__":
    main()
