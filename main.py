import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncpg 
import datetime
from datetime import timedelta
import asyncio
from myserver import server_on # เรียกใช้ myserver ตัวใหม่

# ⚙️ CONFIGURATION 
DATABASE_URL = "postgresql://neondb_owner:npg_68PLfNBHGclV@ep-wispy-field-ahi0no35-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

GUILD_ID = 1450065189138599961 
VERIFY_CHANNEL_ID = 1453767775771426850
ADMIN_CHANNEL_ID = 1455208675000979647
DASHBOARD_CHANNEL_ID = 1455208675000979647 
VERIFIED_ROLE_ID = 1451068283691470970
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

# 🗄️ DATABASE POOL
pool = None

async def init_db():
    global pool
    try:
        pool = await asyncpg.create_pool(dsn=DATABASE_URL)
        async with pool.acquire() as conn:
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
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    review_id SERIAL PRIMARY KEY,
                    job_id INTEGER,
                    stars INTEGER,
                    comment TEXT
                )
            """)
            print("✅ PostgreSQL Database Initialized!")
    except Exception as e:
        print(f"❌ Database Error: {e}")

# 🖥️ UI VIEWS

class VerifyModal(discord.ui.Modal, title="📝 แบบฟอร์มยืนยันตัวตน"):
    name = discord.ui.TextInput(label="Name")
    vrchat_id = discord.ui.TextInput(label="VR Name")
    age = discord.ui.TextInput(label="AGE (ไม่ระบุ = 0)",  max_length=2)
    sex_id = discord.ui.TextInput(label="Gender")
    con_id = discord.ui.TextInput(label="Confirm I Am 18+ and Agree To Rules (Y/N)", max_length=1)

    async def on_submit(self, interaction: discord.Interaction):
        if self.con_id.value.upper() != 'Y':
            await interaction.response.send_message("❌ **ยืนยันตัวตนไม่สำเร็จ** ต้องยอมรับกฎและยืนยันอายุ", ephemeral=True)
            return 

        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ ยืนยันตัวตนสำเร็จ! ", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Error: ไม่พบยศ Verified", ephemeral=True)

        log_channel = interaction.guild.get_channel(New_Verification) 
        if log_channel:
            embed = discord.Embed(title="📝『 ✧  𝔀𝓮𝓵𝓬𝓸𝓶𝓮 ✧ 』", color=discord.Color.green())
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
            embed.add_field(name="╰┈➤User", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="╰┈➤Name", value=self.name.value, inline=True)
            embed.add_field(name="╰┈➤VR Name", value=self.vrchat_id.value, inline=False)
            embed.add_field(name="╰┈➤Age", value=self.age.value, inline=False)
            embed.add_field(name="╰┈➤Gender", value=self.sex_id.value, inline=False)
            embed.set_footer(text=f"User ID: {interaction.user.id}")
            embed.timestamp = datetime.datetime.now()
            await log_channel.send(content=f"{interaction.user.mention} ได้รับยศเรียบร้อย" , embed=embed)

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

class HostJobView(discord.ui.View):
    def __init__(self, job_id):
        super().__init__(timeout=None)
        self.job_id = job_id 

    @discord.ui.button(label="รับงาน (Accept)", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        global pool
        async with pool.acquire() as conn:
            await conn.execute("UPDATE jobs SET status = 'WaitPayment' WHERE job_id = $1", self.job_id)
            row = await conn.fetchrow("SELECT customer_id, service_name, price FROM jobs WHERE job_id = $1", self.job_id)
            
        if row:
            customer_id = row['customer_id']
            service = row['service_name']
            price = row['price']
            await interaction.response.send_message("✅ รับงานแล้ว! ระบบกำลังส่งบิลให้ลูกค้า...", ephemeral=True)
            self.stop() 
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
    await init_db()
    bot.add_view(VerifyButton())
    await bot.tree.sync()
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
    if isinstance(message.channel, discord.DMChannel) and message.attachments:
        global pool
        async with pool.acquire() as conn:
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
@tasks.loop(minutes=1)
async def check_schedule():
    now = datetime.datetime.now()
    global pool
    try:
        if pool is None: return
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

            time_until_start = (start_dt - now).total_seconds() / 60
            if 14 <= time_until_start <= 16:
                msg = f"⏰ **แจ้งเตือน:** บริการ **{service}** จะเริ่มในอีก 15 นาที (Job #{job_id})"
                if customer: await customer.send(msg)
                if host: await host.send(msg)

            if status == 'Active':
                time_until_end = (end_dt - now).total_seconds() / 60
                if 4 <= time_until_end <= 6:
                    msg = f"⌛ **แจ้งเตือน:** เหลือเวลาอีก 5 นาที สำหรับ **{service}** (Job #{job_id})"
                    if customer: await customer.send(msg)
                    if host: await host.send(msg)
    except Exception as e:
        print(f"Loop Error: {e}")

# ⌨️ SLASH COMMANDS

@bot.tree.command(name="setup_verify")
async def setup_verify(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        
    embed = discord.Embed(
        title="🏦 𝘼𝘽𝙊𝙐𝙏 𝙊𝙇𝙔𝙈𝙋𝙐𝙎 🏦  ",
        description=(
            "\t𝙊𝙇𝙔𝙈𝙋𝙐𝙎 คือดินแดนแห่งรัตติกาลที่ซึ่งเหล่าโฮสต์สวมบทเทพ เพื่อมอบการสนทนา เสน่ห์ และประสบการณ์ภายใต้กรอบของ ความเคารพและขอบเขต\n"
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

ROOM_OPTIONS = [f"ห้อง {i}" for i in range(1, 7)]

@bot.tree.command(name="create_job")
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
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin Only", ephemeral=True)

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
async def finish_job(interaction: discord.Interaction, job_id: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin Only", ephemeral=True)

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

# 🚀 RUN BOT (เริ่มทำงาน)
server_on() # เปิดเว็บ (myserver.py ที่รวม dashboard แล้ว)
bot.run(os.getenv('TOKEN'))

