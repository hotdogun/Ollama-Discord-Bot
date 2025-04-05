import discord
from discord import app_commands
import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)

joined_channels = set()
server_histories = {}
server_settings_path = os.path.join(DATA_DIR, "server_setting.json")

# ---------------------------
# 설정 로딩 / 저장 함수
# ---------------------------
def load_server_settings():
    if os.path.exists(server_settings_path):
        with open(server_settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_server_settings(settings):
    with open(server_settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

server_settings = load_server_settings()

def get_history_path(guild_id):
    return os.path.join(DATA_DIR, f"{guild_id}.json")

def load_history(guild_id):
    path = get_history_path(guild_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(guild_id):
    path = get_history_path(guild_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(server_histories.get(guild_id, []), f, indent=2, ensure_ascii=False)

# ---------------------------
# 모델 정보 관련 함수
# ---------------------------
def fetch_available_models(base_url):
    try:
        res = requests.get(f"{base_url}/api/tags")
        res.raise_for_status()
        data = res.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print(f"모델 목록 불러오기 실패: {e}")
        return []

# ---------------------------
# 명령어
# ---------------------------
@tree.command(name="seturl", description="Ollama 서버 URL을 설정합니다")
@app_commands.describe(url="예: http://localhost:11434")
async def set_url(interaction: discord.Interaction, url: str):
    guild_id = str(interaction.guild_id)
    server_settings.setdefault(guild_id, {})["ollama_url"] = url
    available = fetch_available_models(url)
    server_settings[guild_id]["available_models"] = available
    save_server_settings(server_settings)
    await interaction.response.send_message(f"✅ URL 저장됨. 사용 가능한 모델: {', '.join(available)}", ephemeral=True)

@tree.command(name="setmodel", description="사용할 모델을 선택합니다")
@app_commands.describe(model_name="모델 이름")
async def set_model(interaction: discord.Interaction, model_name: str):
    guild_id = str(interaction.guild_id)
    setting = server_settings.get(guild_id)
    available = setting["available_models"]
    if not setting:
        await interaction.response.send_message("❌ 먼저 `/seturl`로 URL을 설정하세요.", ephemeral=True)
        return
    if model_name not in setting.get("available_models", []):
        return await interaction.response.send_message(f"❌ 해당 모델이 없습니다. 사용 가능한 모델: {', '.join(available)}", ephemeral=True)
    setting["model"] = model_name
    save_server_settings(server_settings)
    await interaction.response.send_message(f"✅ 모델이 `{model_name}`로 설정되었습니다.", ephemeral=True)

@tree.command(name="setprompt", description="시스템 프롬프트를 설정합니다")
@app_commands.describe(prompt="프롬프트 내용")
async def set_prompt(interaction: discord.Interaction, prompt: str):
    guild_id = str(interaction.guild_id)
    server_settings.setdefault(guild_id, {})["system_prompt"] = prompt
    save_server_settings(server_settings)
    await interaction.response.send_message("✅ 시스템 프롬프트가 설정되었습니다.", ephemeral=True)

@tree.command(name="getprompt", description="현재 시스템 프롬프트를 확인합니다")
async def get_prompt(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    prompt = server_settings.get(guild_id, {}).get("system_prompt")
    if prompt:
        await interaction.response.send_message(f"📋 현재 시스템 프롬프트:\n```\n{prompt}\n```", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ 시스템 프롬프트가 설정되어 있지 않습니다.", ephemeral=True)

@tree.command(name="join", description="이 채널의 메시지에 자동 응답합니다")
async def join(interaction: discord.Interaction):
    channel_id = interaction.channel.id
    joined_channels.add(channel_id)
    guild_id = str(interaction.guild_id)
    if guild_id not in server_histories:
        server_histories[guild_id] = load_history(guild_id)
    save_history(guild_id)
    await interaction.response.send_message("✅ 이 채널에 참여했습니다!", ephemeral=False)

@tree.command(name="leave", description="이 채널에서 응답을 중지합니다")
async def leave(interaction: discord.Interaction):
    joined_channels.discard(interaction.channel.id)
    await interaction.response.send_message("👋 채널에서 나갔습니다.", ephemeral=False)

@tree.command(name="reset", description="대화 기록을 초기화합니다")
async def reset(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    server_histories[guild_id] = []
    save_history(guild_id)
    await interaction.response.send_message("🧹 기록이 초기화되었습니다.", ephemeral=True)

@tree.command(name="ping", description="핑 테스트")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 퐁!", ephemeral=True)

# ---------------------------
# 이벤트 처리
# ---------------------------
@client.event
async def on_ready():
    print(f"✅ 봇 로그인됨: {client.user} (ID: {client.user.id})")
    await tree.sync()
    print(f"🌐 글로벌 명령어 {len(await tree.fetch_commands())}개 등록됨")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    guild_id = str(message.guild.id if message.guild else None)

    if channel_id not in joined_channels or not guild_id:
        return

    if guild_id not in server_histories:
        server_histories[guild_id] = load_history(guild_id)

    user_name = message.author.display_name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    server_histories[guild_id].append({
        "time": timestamp,
        "role": "user",
        "username": user_name,
        "content": message.content
    })
    save_history(guild_id)

    setting = server_settings.get(guild_id)
    if not setting or "ollama_url" not in setting or "model" not in setting:
        await message.channel.send("⚠️ 먼저 `/seturl` 및 `/setmodel` 명령어로 설정하세요.")
        return

    messages = []

    system_prompt = setting.get("system_prompt")
    if system_prompt:
        messages.append({
            "role": "system",
            "content": system_prompt
        })

    for msg in server_histories[guild_id]:
        messages.append({
            "role": msg["role"],
            "content": msg["content"]
        })
        
    payload = {
        "model": setting["model"],
        "messages":  messages,
        "stream": False
    }

    try:
        res = requests.post(f"{setting['ollama_url']}/api/chat", json=payload)
        res.raise_for_status()
        reply = res.json().get("message", {}).get("content", "⚠️ 응답 없음")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        server_histories[guild_id].append({
            "time": timestamp,
            "role": "assistant",
            "username": setting["model"],
            "content": reply
        })
        save_history(guild_id)
        await message.channel.send(reply)

    except Exception as e:
        await message.channel.send(f"❌ 오류 발생: {e}")

client.run(TOKEN)
