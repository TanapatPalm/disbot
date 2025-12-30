from flask import Flask, render_template_string
import psycopg2 
import datetime
import os

app = Flask(__name__)

DATABASE_URL = "postgresql://neondb_owner:npg_68PLfNBHGclV@ep-wispy-field-ahi0no35-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"


html_template = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <title>Room Schedule</title>
    <meta http-equiv="refresh" content="60">
    <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body { 
            font-family: 'Sarabun', sans-serif; 
            background-color: #2b2d31; 
            color: #dbdee1; 
            margin: 20px;
        }
        .container {
            max_width: 1800px;
            margin: 0 auto;
            background-color: #313338; 
            box-shadow: 0 6px 10px rgba(0,0,0,0.4);
            border-radius: 10px;
            overflow: hidden;
            border: 1px solid #1e1f22;
        }
        
        .header-title {
            padding: 25px;
            background-color: #313338;
            border-bottom: 2px solid #1e1f22;
            font-size: 32px;
            font-weight: bold;
            color: #f2f3f5;
            text-align: center;
        }

        .schedule-table { display: flex; flex-direction: column; width: 100%; }

        .time-header {
            display: flex;
            border-bottom: 1px solid #1e1f22;
            background-color: #2b2d31;
            height: 50px;
            line-height: 50px;
        }
        .room-label-header { 
            width: 200px;
            flex-shrink: 0; 
            border-right: 1px solid #1e1f22; 
            background-color: #2b2d31; 
        }
        .time-slots { flex-grow: 1; display: flex; position: relative; }
        .time-slot-label { 
            flex: 1; 
            text-align: center; 
            font-size: 18px;
            font-weight: bold;
            color: #949ba4; 
            border-right: 1px solid #1e1f22; 
        }

        .room-row {
            display: flex;
            height: 120px;
            border-bottom: 1px solid #1e1f22;
            position: relative;
        }
        .room-label {
            width: 200px;
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            font-weight: bold;
            color: #f2f3f5;
            border-right: 1px solid #1e1f22;
            background-color: #313338;
        }
        .room-timeline {
            flex-grow: 1;
            position: relative;
            background-color: #313338;
            background-image: linear-gradient(to right, transparent 99%, #3f4147 1%);
            background-size: 14.28% 100%; 
        }

        .event-block {
            position: absolute;
            top: 20px; bottom: 20px;
            background-color: #248046; 
            border: 1px solid #1a6334;
            border-radius: 8px;
            color: #ffffff; 
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            overflow: hidden;
            white-space: nowrap;
            box-shadow: 3px 3px 8px rgba(0,0,0,0.5);
            padding: 0 10px;
            z-index: 10;
            transition: all 0.2s;
        }
        .event-block:hover {
            z-index: 100;
            background-color: #2dc770; 
            cursor: pointer;
            transform: scale(1.02);
        }
        .event-title { 
            font-weight: bold; 
            font-size: 18px;
            margin-bottom: 4px;
        }
        .event-time { 
            font-size: 14px;
            color: #e0e0e0; 
        }
        
    </style>
</head>
<body>

<div class="container">
    <div class="header-title">ตารางห้อง</div>

    <div class="schedule-table">
        <div class="time-header">
            <div class="room-label-header"></div> 
            <div class="time-slots">
                {% for t in time_labels %}
                <div class="time-slot-label">{{ t }}</div>
                {% endfor %}
            </div>
        </div>

        {% for room_name in room_list %}
        <div class="room-row">
            <div class="room-label">{{ room_name }}</div>
            <div class="room-timeline">
                
                {% for job in jobs_data[room_name] %}
                <div class="event-block" 
                     style="left: {{ job.left }}%; width: {{ job.width }}%;"
                     title="Host: {{ job.host }} | ลูกค้า: {{ job.customer }}">
                    <div class="event-title">{{ job.service }}</div>
                    <div class="event-time">{{ job.start_str }}-{{ job.end_str }}</div>
                    <div class="event-time">👤 {{ job.host }}</div>
                </div>
                {% endfor %}

            </div>
        </div>
        {% endfor %}
    </div>
</div>

</body>
</html>
"""

@app.route('/')
def index():
    now = datetime.datetime.now()
    if now.hour < 12:
        base_time = (now - datetime.timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    else:
        base_time = now.replace(hour=20, minute=0, second=0, microsecond=0)

    total_minutes = 7 * 60 
    end_scope = base_time + datetime.timedelta(hours=7)

    time_labels = []
    for i in range(7):
        t = base_time + datetime.timedelta(hours=i)
        time_labels.append(t.strftime("%H:00"))

  
    all_jobs = []
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT room_name, host_name, customer_name, service_name, start_datetime, end_datetime FROM jobs WHERE status != 'Done'")
        all_jobs = cursor.fetchall()
        cursor.close()
        conn.close()
        print(f"✅ Dashboard loaded: {len(all_jobs)} jobs found.")
    except Exception as e:
        print(f"❌ DASHBOARD ERROR: {e}")
    
    room_list = [f"ห้อง {i}" for i in range(1, 7)]
    jobs_data = {r: [] for r in room_list}

    if all_jobs:
        for job in all_jobs:
            r_name, h_name, c_name, s_name, start_str, end_str = job
            
            if isinstance(start_str, str):
                start_dt = datetime.datetime.fromisoformat(start_str)
            else:
                start_dt = start_str

            if isinstance(end_str, str):
                end_dt = datetime.datetime.fromisoformat(end_str)
            else:
                end_dt = end_str

            if end_dt <= base_time or start_dt >= end_scope:
                continue

            start_offset = (start_dt - base_time).total_seconds() / 60
            if start_offset < 0: start_offset = 0
            end_offset = (end_dt - base_time).total_seconds() / 60
            if end_offset > total_minutes: end_offset = total_minutes
            
            duration = end_offset - start_offset
            if duration <= 0: continue

            left_percent = (start_offset / total_minutes) * 100
            width_percent = (duration / total_minutes) * 100

            if r_name in jobs_data:
                jobs_data[r_name].append({
                    "service": s_name,
                    "host": h_name,
                    "customer": c_name,
                    "start_str": start_dt.strftime("%H:%M"),
                    "end_str": end_dt.strftime("%H:%M"),
                    "left": left_percent,
                    "width": width_percent
                })

    return render_template_string(
        html_template,
        time_labels=time_labels,
        room_list=room_list,
        jobs_data=jobs_data
    )

def run():
    port = int(os.environ.get("PORT", 5000)) 
    app.run(host='0.0.0.0', port=port, debug=False)
