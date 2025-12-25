import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncpg # ใช้ asyncpg แทน aiosqlite
import datetime
from datetime import timedelta
import asyncio

# ส่วน Server และ Web Dashboard (คงเดิม)
from myserver import server_on
import threading
import web_dashboard
print("🌐 Starting Web Dashboard...")
web_thread = threading.Thread(target=web_dashboard.run)
web_thread.daemon = True 
web_thread.start()
print("✅ Web Dashboard Online at http://127.0.0.1:5000")

# ⚙️ CONFIGURATION 
#TOKEN = ""
DATABASE_URL = "postgresql://neondb_owner:npg_68PLfNBHGclV@ep-wispy-field-ahi0no35-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

GUILD_ID = 1450065189138599961
VERIFY_CHANNEL_ID = 1453767775771426850
#ADMIN_CHANNEL_ID = 
#DASHBOARD_CHANNEL_ID = 
#VERIFIED_ROLE_ID = 
New_Verification = 1453767810118582293

SERVICES_CONFIG = {
    "g":   {"name": " kuy ", "price": 100},
    "t": {"name": " kuy ", "price": 150},
    "s":  {"name": " kuy ",   "price": 80},
    "t":   {"name": " kuy ",   "price": 120},
    "v":    {"name": " kuy ",    "price": 200},
}

# ตั้งค่า Bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# 🗄️ DATABASE POOL (ตัวแปร Global สำหรับเชื่อมต่อฐานข้อมูล)
pool = None

async def init_db():
    global pool
    # สร้าง Connection Pool
    pool = await asyncpg.create_pool(dsn=DATABASE_URL)
    
    async with pool.acquire() as conn:
        # สร้างตาราง jobs (ใช้ SERIAL แทน AUTOINCREMENT)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id SERIAL PRIMARY KEY,
                customer_id BIGINT,
                customer_name TEXT,
                host_id BIGINT,
                host_name TEXT,
                service_name TEXT,
                room_name TEXT,   
                price INTEGER,
                status TEXT,
                start_datetime TEXT,
                end_datetime TEXT
            )
        """)
        # สร้างตาราง reviews
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id SERIAL PRIMARY KEY,
                job_id INTEGER,
                stars INTEGER,
                comment TEXT
            )
        """)
        print("✅ PostgreSQL Database Initialized!")


# 🖥️ UI VIEWS

# --- 1. ระบบยืนยันตัวตน ---
class VerifyModal(discord.ui.Modal, title="📝 แบบฟอร์มยืนยันตัวตน"):
    name = discord.ui.TextInput(label="Name")
    vrchat_id = discord.ui.TextInput(label="VR Name")
    age = discord.ui.TextInput(label="AGE (ไม่ระบุ = 0)",  max_length=2)
    sex_id = discord.ui.TextInput(label="Gender")
    con_id = discord.ui.TextInput(label="Comfirm I Am 18+ and Agree To Rules (Y/N)", max_length=1 )


    async def on_submit(self, interaction: discord.Interaction):
        # 1. เช็คเงื่อนไขก่อนเลย: ถ้าไม่ได้พิมพ์ Y หรือ y
        # .upper() แปลงเป็นตัวพิมพ์ใหญ่ เพื่อให้รองรับทั้ง y และ Y
        if self.con_id.value.upper() != 'Y':
            # แจ้งเตือนและจบการทำงานทันที (return)
            await interaction.response.send_message("❌ **ยืนยันตัวตนไม่สำเร็จ**ต้องยอมรับกฎและยืนยันอายุ", ephemeral=True)
            return 

        # --- ถ้าพิมพ์ Y ผ่านลงมาทำงานส่วนนี้ (เหมือนเดิม) ---
        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ ยืนยันตัวตนสำเร็จ! ", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Error: ไม่พบยศ Verified", ephemeral=True)

        # ส่ง Log (เหมือนเดิม)
        log_channel = interaction.guild.get_channel(New_Verification) 
        if log_channel:
            embed = discord.Embed(title="📝 ได้รับยศเรียบร้อย", color=discord.Color.green())
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            embed.add_field(name="╰┈➤User", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="╰┈➤Name", value=self.name.value, inline=True)
            embed.add_field(name="╰┈➤VR Name", value=self.vrchat_id.value, inline=False)
            embed.add_field(name="╰┈➤Age", value=self.age.value, inline=False)
            embed.add_field(name="╰┈➤Gender", value=self.sex_id.value, inline=False)
            embed.set_footer(text=f"User ID: {interaction.user.id}")
            embed.timestamp = datetime.datetime.now()
            await log_channel.send(content=f"{interaction.user.mention} 『 ✧  𝔀𝓮𝓵𝓬𝓸𝓶𝓮 ✧ 』" , embed=embed)

class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.success, custom_id="verify_btn")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if role in interaction.user.roles:
            await interaction.response.send_message("❌ **คุณยืนยันตัวตนไปแล้ว**", ephemeral=True)
            return
        await interaction.response.send_modal(VerifyModal())

# --- 2. ระบบ Host รับงาน ---
class HostJobView(discord.ui.View):
    def __init__(self, job_id):
        super().__init__(timeout=None)
        self.job_id = job_id # รับ ID งานมาเก็บไว้

    @discord.ui.button(label="รับงาน (Accept)", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        global pool
        async with pool.acquire() as conn:
            # ใช้ $1 แทน ?
            await conn.execute("UPDATE jobs SET status = 'WaitPayment' WHERE job_id = $1", self.job_id)
            
            # ดึงข้อมูลมาส่งบิล
            row = await conn.fetchrow("SELECT customer_id, service_name, price FROM jobs WHERE job_id = $1", self.job_id)
            
        if row:
            customer_id = row['customer_id']
            service = row['service_name']
            price = row['price']

            await interaction.response.send_message("✅ รับงานแล้ว! ระบบกำลังส่งบิลให้ลูกค้า...", ephemeral=True)
            self.stop() # ปิดปุ่ม

            # ส่งบิลหาลูกค้า
            try:
                customer = await interaction.client.fetch_user(customer_id)
                if customer:
                    embed = discord.Embed(title="🧾 แจ้งชำระเงิน (Invoice)", color=discord.Color.blue())
                    embed.add_field(name="Job ID", value=str(self.job_id))
                    embed.add_field(name="บริการ", value=service)
                    embed.add_field(name="ยอดชำระ", value=f"{price} บาท")
                    embed.set_footer(text="📸 กรุณาส่งรูปสลิปโอนเงินเข้ามาในแชทนี้ได้เลยครับ")
                    await customer.send(embed=embed)
            except:
                pass 
        else:
             await interaction.response.send_message("⚠️ Error: ไม่พบข้อมูลงาน", ephemeral=True)

    @discord.ui.button(label="ไม่สะดวก (Decline)", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ ปฏิเสธงานเรียบร้อย", ephemeral=True)
        self.stop()

# --- 3. ระบบ Admin ตรวจสลิป ---
class AdminSlipView(discord.ui.View):
    def __init__(self, job_id, customer_id):
        super().__init__(timeout=None)
        self.job_id = job_id
        self.customer_id = customer_id

    @discord.ui.button(label="อนุมัติ (Approve)", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        global pool
        async with pool.acquire() as conn:
            await conn.execute("UPDATE jobs SET status = 'Active' WHERE job_id = $1", self.job_id)
            host_id = await conn.fetchval("SELECT host_id FROM jobs WHERE job_id = $1", self.job_id)

        await interaction.response.send_message(f"✅ อนุมัติ Job #{self.job_id} แล้ว!", ephemeral=True)
        self.stop()

        # แจ้งเตือน
        guild = interaction.guild
        customer = guild.get_member(self.customer_id)
        host = guild.get_member(host_id) if host_id else None
        
        if customer: await customer.send(f"✅ **Payment Confirmed!** เริ่มงานได้เลยครับ (Job #{self.job_id})")
        if host: await host.send(f"💰 **Money Received!** ลูกค้าจ่ายเงินแล้ว เริ่มงานได้เลย (Job #{self.job_id})")

    @discord.ui.button(label="ไม่อนุมัติ (Reject)", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        customer = interaction.guild.get_member(self.customer_id)
        if customer: await customer.send(f"❌ **Slip Rejected:** สลิปไม่ผ่านการตรวจสอบ (Job #{self.job_id})")
        await interaction.response.send_message("❌ กดไม่อนุมัติเรียบร้อย", ephemeral=True)
        self.stop()

# --- 4. ระบบ Feedback ---
class FeedbackView(discord.ui.View):
    def __init__(self, job_id):
        super().__init__(timeout=None)
        self.job_id = job_id

    async def save_review(self, interaction, score):
        global pool
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO reviews (job_id, stars) VALUES ($1, $2)", self.job_id, score)
            
        await interaction.response.send_message(f"ขอบคุณสำหรับ {score} ดาวครับ! ⭐", ephemeral=True)
        
        admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if admin_channel:
            await admin_channel.send(f"⭐ **Review Job #{self.job_id}**: ได้รับ {score} ดาว จาก {interaction.user.name}")
        self.stop()

    @discord.ui.button(label="5 ⭐", style=discord.ButtonStyle.primary)
    async def s5(self, i, b): await self.save_review(i, 5)
    @discord.ui.button(label="4 ⭐", style=discord.ButtonStyle.secondary)
    async def s4(self, i, b): await self.save_review(i, 4)
    @discord.ui.button(label="3 ⭐", style=discord.ButtonStyle.secondary)
    async def s3(self, i, b): await self.save_review(i, 3)
    @discord.ui.button(label="2 ⭐", style=discord.ButtonStyle.secondary)
    async def s2(self, i, b): await self.save_review(i, 2)
    @discord.ui.button(label="1 ⭐", style=discord.ButtonStyle.danger)
    async def s1(self, i, b): await self.save_review(i, 1)


# 🤖 BOT EVENTS

@bot.event
async def on_ready():
    await init_db() # เริ่มเชื่อมต่อ DB
    bot.add_view(VerifyButton())
    await bot.tree.sync()
    
    if not update_dashboard.is_running():
        update_dashboard.start()
    if not check_schedule.is_running():
        check_schedule.start()
        
    print(f"✅ Bot Online: {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_member_join(member):
    now = datetime.datetime.now(datetime.timezone.utc)
    age_days = (now - member.created_at).days
    if age_days < 3:
        channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if channel:
            await channel.send(f"⚠️ **Security Alert:** {member.mention} เข้ามาใหม่ (อายุบัญชี {age_days} วัน)")

@bot.event
async def on_message(message):
    if message.author.bot: return

    # เช็คสลิปใน DM
    if isinstance(message.channel, discord.DMChannel) and message.attachments:
        global pool
        async with pool.acquire() as conn:
            # ค้นหางานที่สถานะ WaitPayment ของ User นี้
            row = await conn.fetchrow("SELECT job_id, price FROM jobs WHERE customer_id = $1 AND status = 'WaitPayment'", message.author.id)
        
        if row:
            job_id = row['job_id']
            price = row['price']
            admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
            
            embed = discord.Embed(title=f"💸 ตรวจสอบสลิป Job #{job_id}", description=f"จาก: {message.author.mention}\nยอด: {price} บาท")
            embed.set_image(url=message.attachments[0].url)
            
            await admin_channel.send(embed=embed, view=AdminSlipView(job_id, message.author.id))
            await message.channel.send("✅ ได้รับหลักฐานแล้ว! กรุณารอเจ้าหน้าที่ตรวจสอบสักครู่...")
        else:
            await message.channel.send("❓ คุณไม่มีรายการที่รอชำระเงิน")


# 🔄 TASKS

@tasks.loop(seconds=10)
async def update_dashboard():
    channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
    if not channel: return

    now = datetime.datetime.now()
    if now.hour < 12:
        start_display = (now - datetime.timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    else:
        start_display = now.replace(hour=20, minute=0, second=0, microsecond=0)
    
    hours_to_show = 8 

    global pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT job_id, room_name, host_name, customer_name, service_name, start_datetime, end_datetime 
            FROM jobs 
            WHERE status != 'Done'
        """)

    # จัดกลุ่มงานใส่ห้อง
    # ใช้ dictionary comprehension สร้างห้อง 1-6
    rooms_data = {f"ห้อง {i}": [] for i in range(1, 7)}
    ROOM_OPTIONS_LIST = [f"ห้อง {i}" for i in range(1, 7)]

    for row in rows:
        r_name = row['room_name']
        if r_name in rooms_data:
            start_dt = datetime.datetime.fromisoformat(row['start_datetime'])
            end_dt = datetime.datetime.fromisoformat(row['end_datetime'])
            rooms_data[r_name].append({
                "start": start_dt, "end": end_dt,
                "host": row['host_name'], "cust": row['customer_name'],
                "service": row['service_name'], "id": row['job_id']
            })

    # สร้าง Embed
    start_label = start_display.strftime("%H:00")
    end_label = (start_display + datetime.timedelta(hours=hours_to_show)).strftime("%H:00")
    
    embed = discord.Embed(
        title=f"🏩 ตารางห้อง VIP ({start_label} - {end_label})", 
        color=0xe91e63
    )
    embed.timestamp = now
    embed.set_footer(text=f"🟥 = ไม่ว่าง | 🟩 = ว่าง | อัปเดตล่าสุด")

    for room_name in ROOM_OPTIONS_LIST:
        timeline_emojis = ["🟩"] * hours_to_show
        details = []
        current_status_text = "" 
        
        for i in range(hours_to_show):
            slot_start = start_display + datetime.timedelta(hours=i)
            slot_end = slot_start + datetime.timedelta(hours=1)

            for job in rooms_data[room_name]:
                if job["start"] < slot_end and job["end"] > slot_start:
                    timeline_emojis[i] = "🟥"
                    
                    if job["start"] <= now <= job["end"]:
                        current_status_text = f" (Host **{job['host']}** ↔️ Customer **{job['cust']}**)"

                    txt = f"• **[ID{job['id']}]** `{job['start'].strftime('%H:%M')}-{job['end'].strftime('%H:%M')}` : {job['service']}\n   └ Host **{job['host']}** Customer **{job['cust']}**"
                    if txt not in details: details.append(txt)

        bar_str = "".join(timeline_emojis)
        detail_str = "\n".join(details) if details else ""
        
        embed.add_field(
            name=f"🔑 {room_name}{current_status_text}",
            value=f"`{start_label}` {bar_str} `{end_label}`\n{detail_str}",
            inline=False
        )

    history = [msg async for msg in channel.history(limit=10) if msg.author == bot.user]
    if history:
        await history[0].edit(embed=embed)
    else:
        await channel.send(embed=embed)


@tasks.loop(minutes=1)
async def check_schedule():
    now = datetime.datetime.now()
    global pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT job_id, customer_id, host_id, service_name, start_datetime, end_datetime, status FROM jobs WHERE status IN ('WaitPayment', 'Active')")

    for row in rows:
        job_id = row['job_id']
        start_dt = datetime.datetime.fromisoformat(row['start_datetime'])
        end_dt = datetime.datetime.fromisoformat(row['end_datetime'])
        service = row['service_name']
        status = row['status']
        
        customer = bot.get_user(row['customer_id'])
        host = bot.get_user(row['host_id'])

        # แจ้งเตือนเริ่มงาน
        time_until_start = (start_dt - now).total_seconds() / 60
        if 14 <= time_until_start <= 16:
            msg = f"⏰ **แจ้งเตือน:** บริการ **{service}** จะเริ่มในอีก 15 นาที (Job #{job_id})"
            if customer: await customer.send(msg)
            if host: await host.send(msg)

        # แจ้งเตือนจบงาน
        if status == 'Active':
            time_until_end = (end_dt - now).total_seconds() / 60
            if 4 <= time_until_end <= 6:
                msg = f"⌛ **แจ้งเตือน:** เหลือเวลาอีก 5 นาที สำหรับ **{service}** (Job #{job_id})"
                if customer: await customer.send(msg)
                if host: await host.send(msg)


# ⌨️ SLASH COMMANDS

@bot.tree.command(name="setup_verify")
async def setup_verify(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        
    embed = discord.Embed(
        title="🏦 𝘼𝘽𝙊𝙐𝙏 𝙊𝙇𝙔𝙈𝙋𝙐𝙎 🏦  ",
        description=(
            "**\t𝙊𝙇𝙔𝙈𝙋𝙐𝙎 คือดินแดนแห่งรัตติกาลที่ซึ่งเหล่าโฮสต์สวมบทเทพ เพื่อมอบการสนทนา เสน่ห์ และประสบการณ์ภายใต้กรอบของ ความเคารพและขอบเขต\n"
            "\n"
            "เราเชื่อว่า ความลุ่มลึกเกิดจากบทสนทนาเสน่ห์เกิดจากการวางตัว และความพิเศษเกิดจากการคู่ควร\n"
            "\n"
            "𝙊𝙇𝙔𝙈𝙋𝙐𝙎 ไม่ใช่พื้นที่ของความวุ่นวาย ไม่ใช่สถานที่ไร้ขอบเขตและไม่ใช่ที่สำหรับผู้ที่ไม่เคารพผู้อื่น"
        ),
        color=0x2b2d31
    )
    embed.set_image(url="https://i.pinimg.com/736x/c7/e2/00/c7e2008335cb032f9a5f89b6148881b9.jpg")
    
    await interaction.channel.send(embed=embed, view=VerifyButton())
    await interaction.response.send_message("ติดตั้งปุ่มเรียบร้อย!", ephemeral=True)


# --- CREATE JOB (แก้ไขให้ Insert ทันทีเพื่อเอา job_id) ---
ROOM_OPTIONS = [f"ห้อง {i}" for i in range(1, 7)]

@bot.tree.command(name="create_job")
async def create_job(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin Only", ephemeral=True)
@app_commands.describe(
    customer="ลูกค้า", host="โฮสต์", 
    service_select="เลือกบริการ", room_select="เลือกห้อง",
    start_time="เวลาเริ่ม (เช่น 20:30)", duration="ระยะเวลา (นาที)"
)
@app_commands.choices(service_select=[
    app_commands.Choice(name=f"{info['name']} ({info['price']}บ.)", value=key)
    for key, info in SERVICES_CONFIG.items()
])
@app_commands.choices(room_select=[
    app_commands.Choice(name=r, value=r) for r in ROOM_OPTIONS
])
async def create_job(
    interaction: discord.Interaction, 
    customer: discord.Member, host: discord.Member, 
    service_select: app_commands.Choice[str], 
    room_select: app_commands.Choice[str],
    start_time: str, duration: int
):
    selected_key = service_select.value
    service_info = SERVICES_CONFIG.get(selected_key)
    service_name = service_info["name"]
    price = service_info["price"]
    room_name = room_select.value

    now = datetime.datetime.now()
    try:
        h, m = map(int, start_time.split(":"))
        start_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if start_dt < now - datetime.timedelta(hours=12): 
             start_dt += datetime.timedelta(days=1)
        end_dt = start_dt + timedelta(minutes=duration)
    except ValueError:
        return await interaction.response.send_message("❌ เวลาผิดรูปแบบ", ephemeral=True)

    # ✅ INSERT ทันทีเพื่อเอา Job ID และป้องกันข้อมูลหาย
    global pool
    async with pool.acquire() as conn:
        job_id = await conn.fetchval("""
            INSERT INTO jobs (
                customer_id, customer_name, host_id, host_name, 
                service_name, room_name, price, status, start_datetime, end_datetime
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'Pending', $8, $9)
            RETURNING job_id
        """, customer.id, customer.name, host.id, host.name, 
           service_name, room_name, price, start_dt.isoformat(), end_dt.isoformat())

    # แจ้งเตือน Host พร้อมปุ่มที่มี job_id
    embed = discord.Embed(title="🔔 มีงานเข้าใหม่ (New Job)", color=discord.Color.gold())
    embed.add_field(name="📍 สถานที่", value=f"**{room_name}**", inline=False)
    embed.add_field(name="บริการ", value=service_name, inline=True)
    embed.add_field(name="ลูกค้า", value=customer.name, inline=True)
    embed.add_field(name="เวลา", value=f"{start_time} - {end_dt.strftime('%H:%M')}", inline=False)

    try:
        await host.send(embed=embed, view=HostJobView(job_id))
        await interaction.response.send_message(f"✅ สร้างงาน #{job_id} และแจ้ง {host.mention} แล้ว!", ephemeral=True)
    except:
        await interaction.response.send_message(f"✅ สร้างงาน #{job_id} สำเร็จ (แต่ DM Host ไม่ได้)", ephemeral=True)


@bot.tree.command(name="finish_job")
async def finish_job(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin Only", ephemeral=True)

async def finish_job(interaction: discord.Interaction, job_id: int):
    global pool
    async with pool.acquire() as conn:
        await conn.execute("UPDATE jobs SET status = 'Done' WHERE job_id = $1", job_id)
        row = await conn.fetchrow("SELECT customer_id, service_name FROM jobs WHERE job_id = $1", job_id)
    
    if row:
        cust_id = row['customer_id']
        service = row['service_name']
        customer = interaction.guild.get_member(cust_id)
        
        if customer:
            embed = discord.Embed(title="🙏 ขอบคุณที่ใช้บริการครับ", description=f"บริการ: {service}\nกรุณาให้คะแนนความพึงพอใจ", color=discord.Color.purple())
            try:
                await customer.send(embed=embed, view=FeedbackView(job_id))
                await interaction.response.send_message(f"✅ ปิดงาน #{job_id} เรียบร้อย ส่งแบบประเมินแล้ว", ephemeral=True)
            except:
                await interaction.response.send_message(f"✅ ปิดงานแล้ว (แต่ส่ง DM หาลูกค้าไม่ได้)", ephemeral=True)
    else:
        await interaction.response.send_message("❌ ไม่พบ Job ID นี้", ephemeral=True)

server_on()
#bot.run(TOKEN)

bot.run(os.getenv('TOKEN'))
