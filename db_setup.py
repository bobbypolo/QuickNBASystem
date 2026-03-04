import os
import psycopg2
from dotenv import load_dotenv

def setup_database():
    load_dotenv()
    
    # Get direct connection string
    direct_url = os.getenv("SUPABASE_DIRECT")
    password = os.getenv("SUPABASE_PASSWORD")
    
    if not direct_url or not password:
        print("Missing SUPABASE_DIRECT or SUPABASE_PASSWORD in .env")
        return
        
    if "[YOUR-PASSWORD]" in direct_url:
        direct_url = direct_url.replace("[YOUR-PASSWORD]", password)
        
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    if not os.path.exists(schema_path):
        print(f"Schema file not found at {schema_path}")
        return
        
    with open(schema_path, "r") as f:
        schema_sql = f.read()
        
    print("Connecting to Supabase (direct)...")
    try:
        conn = psycopg2.connect(direct_url)
        conn.autocommit = True
        cur = conn.cursor()
        
        print("Executing schema.sql...")
        cur.execute(schema_sql)
        print("Schema successfully applied! Tables created.")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database setup failed: {e}")

if __name__ == "__main__":
    setup_database()
