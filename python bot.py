import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiosqlite
import datetime
from datetime import timedelta
import asyncio

from myserver import server_on


# ⚙️ CONFIGURATION 

GUILD_ID = 1450132671048056924          # ID เซิร์ฟเวอร์หลัก
VERIFY_CHANNEL_ID =1450132709354635346  # ห้องสำหรับกดปุ่ม Verify
ADMIN_CHANNEL_ID =1450134587991789680   # ห้อง Admin (สำหรับตรวจสลิป/แจ้งเตือน Security)
DASHBOARD_CHANNEL_ID =1450134627376168992  # ห้องแสดงตารางงาน Dashboard
VERIFIED_ROLE_ID =1450138205167816795  # ID ยศที่ได้หลังยืนยันตัวตน
New_Verification=1450432424734359593

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


# 🗄️ DATABASE MANAGER
async def init_db():
    async with aiosqlite.connect("service_bot.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                customer_name TEXT,
                host_id INTEGER,
                host_name TEXT,
                service_name TEXT,
                room_name TEXT,   
                price INTEGER,
                status TEXT,
                start_datetime TEXT,
                end_datetime TEXT
            )
        """)
        # (ตาราง reviews เหมือนเดิม)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                stars INTEGER,
                comment TEXT
            )
        """)
        await db.commit()
        print("✅ Database Initialized with Rooms!")


# 🖥️ UI VIEWS (ปุ่มและแบบฟอร์ม)

# --- 1. ระบบยืนยันตัวตน (Verification) ---
class VerifyModal(discord.ui.Modal, title="📝 แบบฟอร์มยืนยันตัวตน"):
    name = discord.ui.TextInput(label="Name")
    vrchat_id = discord.ui.TextInput(label="VR Name")
    age = discord.ui.TextInput(label="AGE",  max_length=2)
    sex_id = discord.ui.TextInput(label="Gender")
    con_id = discord.ui.TextInput(label="Comfirm I Am 18+ and Agree To Rules (Y/N)", max_length=1 )

    async def on_submit(self, interaction: discord.Interaction):
        # 1. ให้ยศ Verified (เหมือนเดิม)
        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if role:
            await interaction.user.add_roles(role)
            # ตอบกลับ user ว่าสำเร็จ
            await interaction.response.send_message(f"✅ ยืนยันตัวตนสำเร็จ! ", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Error: ไม่พบยศ Verified โปรดแจ้ง Admin", ephemeral=True)

        # 2. (ส่วนที่เพิ่ม) ส่งข้อมูลไปที่ห้อง Admin หรือห้อง Log
        # คุณสามารถเปลี่ยน ADMIN_CHANNEL_ID เป็น ID ห้องอื่นที่อยากให้เด้งได้
        log_channel = interaction.guild.get_channel(New_Verification) 
        
        if log_channel:
            # สร้างการ์ด
            embed = discord.Embed(title="📝 ได้รับยศเรียบร้อย ยินดีต้อนรับเข้าสู่เซิร์ฟเวอร์", color=discord.Color.green())
            embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None) # ใส่รูปโปรไฟล์คนกด
            embed.add_field(name="**User**", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="**Name**", value=self.name.value, inline=True)
            embed.add_field(name="**VR Name**", value=self.vrchat_id.value, inline=False)
            embed.add_field(name="**Age**", value=self.age.value, inline=False)
            embed.add_field(name="**Gender**", value=self.sex_id.value, inline=False)
            embed.set_footer(text=f"User ID: {interaction.user.id}")
            embed.timestamp = datetime.datetime.now()

            await log_channel.send(content=f"{interaction.user.mention} ได้รับยศเรียบร้อย", embed=embed)

# --- เหนแค่ตัวเอง ---
class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="ยืนยันตัวตน", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_btn")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        # ค้นหายศ
        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        
        # เช็คว่าตัวคนกดมียศนี้อยู่แล้วหรือยัง?
        if role in interaction.user.roles:
            # ถ้ามีแล้ว ให้แจ้งเตือนและจบการทำงานทันที 
            await interaction.response.send_message("❌ **คุณยืนยันตัวตนไปแล้ว** ไม่สามารถทำรายการซ้ำได้", ephemeral=True)
            return

        # ถ้ายังไม่มี ให้เปิดฟอร์มกรอกข้อมูลตามปกติ
        await interaction.response.send_modal(VerifyModal())

# --- 2. ระบบ Host รับงาน ---
class HostJobView(discord.ui.View):
    def __init__(self, job_id):
        super().__init__(timeout=None)
        self.job_id = job_id

    @discord.ui.button(label="รับงาน (Accept)", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect("service_bot.db") as db:
            await db.execute("UPDATE jobs SET status = 'WaitPayment' WHERE job_id = ?", (self.job_id,))
            await db.commit()
            
            async with db.execute("SELECT customer_id, service_name, price FROM jobs WHERE job_id = ?", (self.job_id,)) as cursor:
                row = await cursor.fetchone()
                customer_id, service, price = row

        await interaction.response.send_message("✅ รับงานแล้ว! ระบบกำลังส่งบิลให้ลูกค้า...", ephemeral=True)
        self.stop()

        # ส่งบิลหาลูกค้า
        try:
            customer = await interaction.client.fetch_user(customer_id)
        except:
            customer = None
        if customer:
            embed = discord.Embed(title="🧾 แจ้งชำระเงิน (Invoice)", color=discord.Color.blue())
            embed.add_field(name="Job ID", value=str(self.job_id))
            embed.add_field(name="บริการ", value=service)
            embed.add_field(name="ยอดชำระ", value=f"{price} บาท")
            embed.set_footer(text="📸 กรุณาส่งรูปสลิปโอนเงินเข้ามาในแชทนี้ได้เลยครับ")
            try:
                await customer.send(embed=embed)
            except:
                pass # ส่งไม่ได้ (DM ปิด)

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
        async with aiosqlite.connect("service_bot.db") as db:
            await db.execute("UPDATE jobs SET status = 'Active' WHERE job_id = ?", (self.job_id,))
            await db.commit()
            async with db.execute("SELECT host_id FROM jobs WHERE job_id = ?", (self.job_id,)) as cursor:
                row = await cursor.fetchone()
                host_id = row[0]

        await interaction.response.send_message(f"✅ อนุมัติ Job #{self.job_id} แล้ว!", ephemeral=True)
        self.stop()

        # แจ้งเตือน
        guild = interaction.guild
        customer = guild.get_member(self.customer_id)
        host = guild.get_member(host_id)
        if customer: await customer.send(f"✅ **Payment Confirmed!** เริ่มงานได้เลยครับ (Job #{self.job_id})")
        if host: await host.send(f"💰 **Money Received!** ลูกค้าจ่ายเงินแล้ว เริ่มงานได้เลย (Job #{self.job_id})")

    @discord.ui.button(label="ไม่อนุมัติ (Reject)", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        customer = interaction.guild.get_member(self.customer_id)
        if customer: await customer.send(f"❌ **Slip Rejected:** สลิปไม่ผ่านการตรวจสอบ กรุณาติดต่อ Admin (Job #{self.job_id})")
        await interaction.response.send_message("❌ กดไม่อนุมัติเรียบร้อย", ephemeral=True)
        self.stop()

# --- 4. ระบบ Feedback (รีวิว) ---
class FeedbackView(discord.ui.View):
    def __init__(self, job_id):
        super().__init__(timeout=None)
        self.job_id = job_id

    async def save_review(self, interaction, score):
        async with aiosqlite.connect("service_bot.db") as db:
            await db.execute("INSERT INTO reviews (job_id, stars) VALUES (?, ?)", (self.job_id, score))
            await db.commit()
            
        await interaction.response.send_message(f"ขอบคุณสำหรับ {score} ดาวครับ! ⭐", ephemeral=True)
        
        # แจ้ง Admin เพื่อเก็บสถิติ
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


# 🤖 BOT EVENTS & LOGIC

@bot.event
async def on_ready():
    await init_db()
    bot.add_view(VerifyButton())
    await bot.tree.sync()
    
    # เริ่ม Loop ทำงานอัตโนมัติ
    if not update_dashboard.is_running():
        update_dashboard.start()
    if not check_schedule.is_running():
        check_schedule.start()
        
    print(f"✅ Bot Online: {bot.user} (ID: {bot.user.id})")
    print("Dashboard Loop & Schedule Loop Started.")

# 1. Security Check (เช็คอายุบัญชีตอนเข้า)
@bot.event
async def on_member_join(member):
    now = datetime.datetime.now(datetime.timezone.utc)
    created_at = member.created_at
    age_days = (now - created_at).days
    
    if age_days < 3: # ถ้าบัญชีใหม่อายุน้อยกว่า 3 วัน
        channel = bot.get_channel(ADMIN_CHANNEL_ID)
        if channel:
            await channel.send(f"⚠️ **Security Alert:** {member.mention} เข้ามาใหม่ (อายุบัญชี {age_days} วัน) ระวังสแปม")

# 2. ระบบรับสลิปใน DM
@bot.event
async def on_message(message):
    if message.author.bot: return

    # ถ้าส่งรูปใน DM
    if isinstance(message.channel, discord.DMChannel) and message.attachments:
        async with aiosqlite.connect("service_bot.db") as db:
            # ค้นหางานที่รอจ่ายเงิน (WaitPayment)
            async with db.execute("SELECT job_id, price FROM jobs WHERE customer_id = ? AND status = 'WaitPayment'", (message.author.id,)) as cursor:
                job = await cursor.fetchone()
        
        if job:
            job_id, price = job
            admin_channel = bot.get_channel(ADMIN_CHANNEL_ID)
            
            embed = discord.Embed(title=f"💸 ตรวจสอบสลิป Job #{job_id}", description=f"จาก: {message.author.mention}\nยอด: {price} บาท")
            embed.set_image(url=message.attachments[0].url)
            
            await admin_channel.send(embed=embed, view=AdminSlipView(job_id, message.author.id))
            await message.channel.send("✅ ได้รับหลักฐานแล้ว! กรุณารอเจ้าหน้าที่ตรวจสอบสักครู่...")
        else:
            await message.channel.send("❓ คุณไม่มีรายการที่รอชำระเงิน หรือสถานะไม่ถูกต้อง")


# 🔄 TASKS (LOOPS)

# 1. Update Dashboard (แสดงงานปัจจุบัน)
@tasks.loop(seconds=10)
async def update_dashboard():
    channel = bot.get_channel(DASHBOARD_CHANNEL_ID)
    if not channel: return

    # --- ตั้งค่าเวลา (Fixed 20:00 - 03:00) ---
    now = datetime.datetime.now()
    if now.hour < 12:
        start_display = (now - datetime.timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
    else:
        start_display = now.replace(hour=20, minute=0, second=0, microsecond=0)
    
    hours_to_show = 8 

    # 1. ดึงงานทั้งหมด (เพิ่ม job_id เข้ามาใน Query ตัวแรกสุด)
    async with aiosqlite.connect("service_bot.db") as db:
        query = """
            SELECT job_id, room_name, host_name, customer_name, service_name, start_datetime, end_datetime 
            FROM jobs 
            WHERE status != 'Done'
        """
        async with db.execute(query) as cursor:
            all_jobs = await cursor.fetchall()

    # จัดกลุ่มงานใส่ห้อง
    rooms_data = {f"ห้อง {i}": [] for i in range(1, 7)}

    for job in all_jobs:
        # รับค่า job_id เพิ่มเข้ามา
        j_id, r_name, h_name, c_name, s_name, start_str, end_str = job
        
        if r_name in rooms_data:
            start_dt = datetime.datetime.fromisoformat(start_str)
            end_dt = datetime.datetime.fromisoformat(end_str)
            # เก็บข้อมูลลง List (รวม job_id ด้วย)
            rooms_data[r_name].append((start_dt, end_dt, h_name, c_name, s_name, j_id))

    # สร้าง Embed
    start_label = start_display.strftime("%H:00")
    end_label = (start_display + datetime.timedelta(hours=hours_to_show)).strftime("%H:00")
    
    embed = discord.Embed(
        title=f"🏩 ตารางห้อง VIP ({start_label} - {end_label})", 
        color=0xe91e63
    )
    embed.timestamp = now
    embed.set_footer(text=f"🟥 = ไม่ว่าง | 🟩 = ว่าง | อัปเดตล่าสุด")

    # วนลูปทีละห้อง
    for room_name in ROOM_OPTIONS:
        timeline_emojis = ["🟩"] * hours_to_show
        details = []
        current_status_text = "" 

        jobs_in_room = rooms_data.get(room_name, [])
        
        for i in range(hours_to_show):
            slot_start = start_display + datetime.timedelta(hours=i)
            slot_end = slot_start + datetime.timedelta(hours=1)

            # ดึง job_id (j_id) ออกมาใช้
            for j_start, j_end, h_name, c_name, s_name, j_id in jobs_in_room:
                # เช็คเวลาชน
                if j_start < slot_end and j_end > slot_start:
                    timeline_emojis[i] = "🟥"
                    
                    # ถ้ากำลังใช้งานอยู่ ให้ขึ้นชื่อคู่ Host-Customer
                    if j_start <= now <= j_end:
                        current_status_text = f" (Host **{h_name}** ↔️ Customer **{c_name}**)"

                    # รายละเอียดงานด้านล่าง (ใส่ [#Job ID] ไว้หน้าสุด)
                    txt = f"• **[ID{j_id}]** `{j_start.strftime('%H:%M')}-{j_end.strftime('%H:%M')}` : {s_name}\n   └ Host **{h_name}**  Customer **{c_name}**"
                    if txt not in details: details.append(txt)

        bar_str = "".join(timeline_emojis)
        detail_str = "\n".join(details) if details else ""

        field_name = f"🔑 {room_name}{current_status_text}"

        embed.add_field(
            name=field_name,
            value=f"`{start_label}` {bar_str} `{end_label}`\n{detail_str}",
            inline=False
        )

    # ส่ง/แก้ไขข้อความ
    history = [msg async for msg in channel.history(limit=10) if msg.author == bot.user]
    if history:
        await history[0].edit(embed=embed)
    else:
        await channel.send(embed=embed)

# 2. Notification Loop (แจ้งเตือนเวลา)
@tasks.loop(minutes=1)
async def check_schedule():
    now = datetime.datetime.now()
    
    async with aiosqlite.connect("service_bot.db") as db:
        # ดึงงานที่ยังไม่จบ (WaitPayment หรือ Active)
        async with db.execute("SELECT job_id, customer_id, host_id, service_name, start_datetime, end_datetime, status FROM jobs WHERE status IN ('WaitPayment', 'Active')") as cursor:
            jobs = await cursor.fetchall()

    for job in jobs:
        job_id, cust_id, host_id, service, start_str, end_str, status = job
        start_dt = datetime.datetime.fromisoformat(start_str)
        end_dt = datetime.datetime.fromisoformat(end_str)
        
        customer = bot.get_user(cust_id)
        host = bot.get_user(host_id)

        # -- Logic แจ้งเตือนก่อนเริ่ม 15 นาที --
        # เช็คว่าเวลาปัจจุบัน อยู่ในช่วง (Start - 16นาที) ถึง (Start - 14นาที) เพื่อแจ้งครั้งเดียว
        time_until_start = (start_dt - now).total_seconds() / 60
        if 14 <= time_until_start <= 16:
            msg = f"⏰ **แจ้งเตือน:** บริการ **{service}** จะเริ่มในอีก 15 นาที (Job #{job_id})"
            if customer: await customer.send(msg)
            if host: await host.send(msg)

        # -- Logic แจ้งเตือนก่อนจบ 5 นาที --
        if status == 'Active':
            time_until_end = (end_dt - now).total_seconds() / 60
            if 4 <= time_until_end <= 6:
                msg = f"⌛ **แจ้งเตือน:** เหลือเวลาอีก 5 นาที สำหรับ **{service}** (Job #{job_id})"
                if customer: await customer.send(msg)
                if host: await host.send(msg)


# ⌨️ SLASH COMMANDS (ADMIN)

@bot.tree.command(name="setup_verify")
async def setup_verify(interaction: discord.Interaction):
    # เช็คสิทธิ์ Admin
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin Only", ephemeral=True)
        
    # 1. สร้าง Embed (กรอบข้อความ)
    embed = discord.Embed(
        title="🏦 𝘼𝘽𝙊𝙐𝙏 𝙊𝙇𝙔𝙈𝙋𝙐𝙎 🏦  ",
        description=(
            "\t𝙊𝙇𝙔𝙈𝙋𝙐𝙎 คือดินแดนแห่งรัตติกาลที่ซึ่งเหล่าโฮสต์สวมบทเทพ เพื่อมอบการสนทนา เสน่ห์ และประสบการณ์ภายใต้กรอบของ ความเคารพและขอบเขต\n"
            "\n"
            "เราเชื่อว่า ความลุ่มลึกเกิดจากบทสนทนาเสน่ห์เกิดจากการวางตัว และความพิเศษเกิดจากการคู่ควร\n"
            "\n"
            "𝙊𝙇𝙔𝙈𝙋𝙐𝙎 ไม่ใช่พื้นที่ของความวุ่นวาย ไม่ใช่สถานที่ไร้ขอบเขตและไม่ใช่ที่สำหรับผู้ที่ไม่เคารพผู้อื่น"
        ),
        color=0x2b2d31 # สีเทาเข้ม (แบบ Dark Mode)
    )

    # 2. ใส่รูปภาพขนาดใหญ่ (Image)
    # *สำคัญ* คุณต้องเปลี่ยน URL ในบรรทัดด้านล่างนี้ เป็นลิ้งค์รูปของคุณเอง
    # วิธีเอารูป: อัปโหลดรูปใน Discord -> คลิกขวาที่รูป -> Copy Link -> เอามาวางแทนที่
    embed.set_image(url="https://scontent.fbkk28-1.fna.fbcdn.net/v/t39.30808-6/599862497_2501801976888185_2332999292421552415_n.jpg?_nc_cat=104&_nc_cb=99be929b-ad57045b&ccb=1-7&_nc_sid=127cfc&_nc_ohc=KjJjTBnuP0MQ7kNvwHpvzsQ&_nc_oc=AdkiS-xOya4NFDawgH2FnAkuGkcXAN8y4P4pBCxWWN_brbfOED9uUvmpcrx-JESf2dM&_nc_zt=23&_nc_ht=scontent.fbkk28-1.fna&_nc_gid=WDuiKpqGgT-nqY-HEcJsuw&oh=00_AflSukuwgVOK0hMupYK027DdqLMGWwCtoEpJuyrlGZKYKQ&oe=694C973B")

    # 3. ส่งข้อความพร้อมปุ่ม
    await interaction.channel.send(embed=embed, view=VerifyButton())
    await interaction.response.send_message("ติดตั้งปุ่มเรียบร้อย!", ephemeral=True)




# ==========================================
# 2. คำสั่ง create_job แบบใหม่ (มี Dropdown + Auto Price)
# ==========================================
# --- Config ห้องและบริการ ---
ROOM_OPTIONS = [f"ห้อง {i}" for i in range(1, 7)] # สร้างรายชื่อ ห้อง 1 - ห้อง 6

@bot.tree.command(name="create_job")
@app_commands.describe(
    customer="ลูกค้า", host="โฮสต์", 
    service_select="เลือกบริการ", room_select="เลือกห้อง",
    start_time="เวลาเริ่ม (เช่น 20:30)", duration="ระยะเวลา (นาที)"
)
# 1. Dropdown เลือกบริการ (ราคา Auto)
@app_commands.choices(service_select=[
    app_commands.Choice(name=f"{info['name']} ({info['price']}บ.)", value=key)
    for key, info in SERVICES_CONFIG.items()
])
# 2. Dropdown เลือกห้อง (ห้อง 1-6)
@app_commands.choices(room_select=[
    app_commands.Choice(name=r, value=r) for r in ROOM_OPTIONS
])
async def create_job(
    interaction: discord.Interaction, 
    customer: discord.Member, host: discord.Member, 
    service_select: app_commands.Choice[str], 
    room_select: app_commands.Choice[str], # รับค่าห้อง
    start_time: str, duration: int
):
    # ดึงข้อมูลบริการ
    selected_key = service_select.value
    service_info = SERVICES_CONFIG.get(selected_key)
    service_name = service_info["name"]
    price = service_info["price"]
    room_name = room_select.value # ชื่อห้องที่เลือก

    # คำนวณเวลา
    now = datetime.datetime.now()
    try:
        h, m = map(int, start_time.split(":"))
        start_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # ปรับเวลาข้ามวันอัตโนมัติ (เช่น จองตี 1 ตอน 4 ทุ่ม)
        if start_dt < now - datetime.timedelta(hours=12): 
             start_dt += datetime.timedelta(days=1)
        end_dt = start_dt + timedelta(minutes=duration)
    except ValueError:
        return await interaction.response.send_message("❌ เวลาผิดรูปแบบ", ephemeral=True)

    # บันทึก Database (เพิ่ม room_name)
    async with aiosqlite.connect("service_bot.db") as db:
        cursor = await db.execute("""
            INSERT INTO jobs (
                customer_id, customer_name, host_id, host_name, 
                service_name, room_name, price, status, start_datetime, end_datetime
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
        """, (
            customer.id, customer.name, host.id, host.name, 
            service_name, room_name, price, start_dt.isoformat(), end_dt.isoformat()
        ))
        job_id = cursor.lastrowid
        await db.commit()

    # แจ้งเตือน Host
    embed = discord.Embed(title="🔔 มีงานเข้าใหม่ (New Job)", color=discord.Color.gold())
    embed.add_field(name="📍 สถานที่", value=f"**{room_name}**", inline=False)
    embed.add_field(name="บริการ", value=service_name, inline=True)
    embed.add_field(name="ลูกค้า", value=customer.name, inline=True)
    embed.add_field(name="เวลา", value=f"{start_time} - {end_dt.strftime('%H:%M')}", inline=False)

    try:
        await host.send(embed=embed, view=HostJobView(job_id))
        await interaction.response.send_message(f"✅ จอง **{room_name}** ให้ {host.mention} แล้ว!", ephemeral=True)
    except:
        await interaction.response.send_message(f"✅ จองสำเร็จ (แต่ DM Host ไม่ไป)", ephemeral=True)

@bot.tree.command(name="finish_job")
async def finish_job(interaction: discord.Interaction, job_id: int):
    async with aiosqlite.connect("service_bot.db") as db:
        # อัปเดตสถานะ
        await db.execute("UPDATE jobs SET status = 'Done' WHERE job_id = ?", (job_id,))
        await db.commit()
        
        # หา ID ลูกค้า
        async with db.execute("SELECT customer_id, service_name FROM jobs WHERE job_id = ?", (job_id,)) as cursor:
            row = await cursor.fetchone()
    
    if row:
        cust_id, service = row
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

# รันบอท
server_on()
bot.run(os.getenv('TOKEN'))