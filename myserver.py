from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "Hello, I am alive!"

def run():
    # รับ Port จาก Render (สำคัญมาก)
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def server_on():
    t = Thread(target=run)
    t.daemon = True # <-- สำคัญ! ตั้งเป็น Daemon เพื่อให้ปิดพร้อมบอทได้
    t.start()
